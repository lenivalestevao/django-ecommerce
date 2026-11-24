import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .cart import Cart
from .forms import AccountForm, CheckoutForm, EmailLoginForm, RegisterForm, TrackForm
from .models import Category, Coupon, Order, Product
from .payments import PaymentManager, WebhookError
from .services import CheckoutError, place_order

logger = logging.getLogger(__name__)

SORTS = {
    "newest": ("-created_at", "-id"),
    "price_asc": ("price", "id"),
    "price_desc": ("-price", "-id"),
    "name": ("name", "id"),
}


# --- Helpers ----------------------------------------------------------------


def remember_order(request, order: Order) -> None:
    """Lets this browser session open the order page, even without an account."""
    numbers = list(request.session.get("my_orders", []))
    if order.number not in numbers:
        numbers.append(order.number)
    request.session["my_orders"] = numbers


def check_order_access(request, order: Order) -> None:
    """Staff, the order's owner, or the browser session that placed (or tracked) the order."""
    user = request.user
    allowed = (
        user.is_authenticated and (user.is_staff or order.user_id == user.pk)
    ) or order.number in request.session.get("my_orders", [])

    if not allowed:
        raise PermissionDenied


def staff_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def back(request, fallback: str = "cart"):
    """Redirect to the page the visitor came from, but only if it is on this site."""
    target = request.META.get("HTTP_REFERER", "")
    host = request.get_host()

    if target and (target.startswith(f"http://{host}/") or target.startswith(f"https://{host}/")):
        return redirect(target)

    return redirect(fallback)


# --- Storefront -------------------------------------------------------------


def home(request):
    products = Product.objects.active().select_related("category")

    return render(
        request,
        "shop/home.html",
        {
            "featured": products.featured()[:8],
            "latest": products[:8],
            "categories": Category.objects.active().with_product_counts(),
        },
    )


def shop_index(request, slug=None):
    category = get_object_or_404(Category.objects.active(), slug=slug) if slug else None

    sort = request.GET.get("sort", "newest")
    if sort not in SORTS:
        sort = "newest"

    term = request.GET.get("q", "").strip()[:100]

    products = Product.objects.active().select_related("category").search(term)
    if category:
        products = products.filter(category=category)

    page = Paginator(products.order_by(*SORTS[sort]), settings.SHOP["per_page"]).get_page(request.GET.get("page"))

    return render(
        request,
        "shop/shop_index.html",
        {
            "page_obj": page,
            "products": page.object_list,
            "category": category,
            "categories": Category.objects.active(),
            "sort": sort,
            "sorts": [("newest", "Newest"), ("price_asc", "Price: low to high"), ("price_desc", "Price: high to low"), ("name", "Name")],
            "term": term,
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.active().select_related("category"), slug=slug)
    related = Product.objects.active().filter(category=product.category).exclude(pk=product.pk) if product.category else []

    return render(request, "shop/product_detail.html", {"product": product, "related": related[:4]})


# --- Cart -------------------------------------------------------------------


def cart_detail(request):
    cart = Cart(request.session)

    return render(
        request,
        "shop/cart.html",
        {"lines": cart.lines(), "totals": cart.totals(), "coupon": cart.coupon()},
    )


def _quantity(request, default=None, minimum=1):
    """Reads a whole number from the posted form, or returns `default` when it is missing or invalid."""
    try:
        value = int(request.POST.get("quantity", ""))
    except ValueError:
        return default

    return value if minimum <= value <= 99 else default


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product.objects.active(), slug=slug)
    quantity = _quantity(request, default=1)

    if not product.in_stock:
        messages.error(request, f'"{product.name}" is out of stock.')
    else:
        Cart(request.session).add(product, quantity)
        messages.success(request, f'"{product.name}" was added to your cart.')

    return back(request)


@require_POST
def cart_update(request, slug):
    product = get_object_or_404(Product.objects.active(), slug=slug)
    quantity = _quantity(request, default=None, minimum=0)

    if quantity is None:
        messages.error(request, "Please enter a quantity between 0 and 99.")
    else:
        Cart(request.session).set(product, quantity)

    return redirect("cart")


@require_POST
def cart_remove(request, slug):
    product = get_object_or_404(Product, slug=slug)
    Cart(request.session).remove(product)
    messages.success(request, "Item removed.")

    return redirect("cart")


@require_POST
def coupon_apply(request):
    cart = Cart(request.session)
    code = request.POST.get("code", "").strip().upper()[:40]
    coupon = Coupon.objects.filter(code=code).first() if code else None

    if coupon is None:
        messages.error(request, "This coupon code does not exist.")
    elif problem := coupon.problem_for(cart.subtotal()):
        messages.error(request, problem)
    else:
        cart.apply_coupon(coupon)
        messages.success(request, f"Coupon {coupon.code} applied.")

    return redirect("cart")


@require_POST
def coupon_remove(request):
    Cart(request.session).remove_coupon()

    return redirect("cart")


# --- Checkout and orders ----------------------------------------------------


def checkout(request):
    cart = Cart(request.session)

    if cart.is_empty():
        return redirect("cart")

    manager = PaymentManager()
    methods = manager.methods()

    if request.method == "POST":
        form = CheckoutForm(request.POST, methods=methods)

        if form.is_valid():
            user = request.user if request.user.is_authenticated else None

            try:
                order = place_order(cart, form.cleaned_data, user)
            except CheckoutError as error:
                messages.error(request, str(error))
            else:
                cart.clear()
                remember_order(request, order)
                notify(order)

                gateway = manager.gateway(order.payment_method)
                if gateway is not None:
                    try:
                        return redirect(gateway.create_payment(order))
                    except Exception:
                        logger.exception("Could not create the %s payment for %s", gateway.key, order.number)
                        messages.error(
                            request,
                            "We could not reach the payment provider. Your order was saved, you can try paying again.",
                        )
                        return redirect("order", number=order.number)

                messages.success(request, "Thank you! Your order was placed.")
                return redirect("order", number=order.number)
    else:
        initial = {"payment_method": next(iter(methods))}
        if request.user.is_authenticated:
            initial.update(customer_name=request.user.first_name, customer_email=request.user.email)
        form = CheckoutForm(initial=initial, methods=methods)

    return render(request, "shop/checkout.html", {"form": form, "lines": cart.lines(), "totals": cart.totals()})


def notify(order: Order) -> None:
    """Emails the customer and the shop owner. A mail problem must never lose a sale."""
    try:
        context = {"order": order, "items": order.items.all(), "SHOP": settings.SHOP}
        link = settings.SITE_URL + reverse("order", args=[order.number])

        send_mail(
            f"Your order {order.number}",
            render_to_string("shop/emails/order_placed.txt", {**context, "link": link}),
            None,
            [order.customer_email],
        )
        send_mail(
            f"New order {order.number}",
            render_to_string("shop/emails/new_order.txt", {**context, "link": settings.SITE_URL + reverse("admin:shop_order_change", args=[order.pk])}),
            None,
            [settings.SHOP["contact_email"]],
        )
    except Exception:
        logger.exception("Could not send the emails for order %s", order.number)


def order_detail(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    check_order_access(request, order)

    manager = PaymentManager()

    return render(
        request,
        "shop/order.html",
        {
            "order": order,
            "can_pay": manager.is_online(order.payment_method) and not order.is_paid and order.status != "cancelled",
            "bank_transfer": order.payment_method == "bank" and not order.is_paid and order.status != "cancelled",
        },
    )


@require_POST
def order_pay(request, number):
    order = get_object_or_404(Order, number=number)
    check_order_access(request, order)

    gateway = PaymentManager().gateway(order.payment_method)

    if gateway is None or order.is_paid or order.status == "cancelled":
        raise Http404

    try:
        return redirect(gateway.create_payment(order))
    except Exception:
        logger.exception("Could not create the %s payment for %s", gateway.key, order.number)
        messages.error(request, "The payment provider is not available right now. Please try again later.")

        return redirect("order", number=order.number)


def track(request):
    form = TrackForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        order = Order.objects.filter(
            number=form.cleaned_data["number"].strip().upper(),
            customer_email__iexact=form.cleaned_data["email"],
        ).first()

        if order is None:
            form.add_error("number", "We could not find an order with these details.")
        else:
            # Proving the number and email unlocks the order page for this session.
            remember_order(request, order)
            return redirect("order", number=order.number)

    return render(request, "shop/track.html", {"form": form})


# --- Payments ---------------------------------------------------------------


def payment_return(request, number):
    """The customer comes back from Stripe, PayPal or Mercado Pago."""
    order = get_object_or_404(Order, number=number)
    check_order_access(request, order)

    gateway = PaymentManager().gateway(order.payment_method)

    if gateway is not None and request.GET.get("gateway") == gateway.key:
        try:
            paid = gateway.confirm(order, request)
        except Exception:
            logger.exception("Could not confirm the %s payment for %s", gateway.key, order.number)
            paid = False

        if paid:
            messages.success(request, "Payment received. Thank you!")
        else:
            messages.error(
                request,
                "We have not received the payment yet. If you paid, it will be confirmed shortly.",
            )

    return redirect("order", number=order.number)


def payment_cancel(request, number):
    order = get_object_or_404(Order, number=number)
    check_order_access(request, order)
    messages.error(request, "The payment was cancelled. You can try again below.")

    return redirect("order", number=order.number)


@csrf_exempt
@require_POST
def payment_webhook(request, gateway):
    """Server-to-server notification. Each gateway verifies it on its own."""
    handler = PaymentManager().gateway(gateway)

    if handler is None:
        raise Http404

    try:
        handler.webhook(request)
    except WebhookError as error:
        return HttpResponseBadRequest(str(error))

    return HttpResponse(status=204)


# --- Accounts ---------------------------------------------------------------


class ShopLoginView(LoginView):
    template_name = "shop/auth/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse("dashboard" if self.request.user.is_staff else "account")


def register(request):
    if request.user.is_authenticated:
        return redirect("account")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="shop.backends.EmailBackend")
        messages.success(request, "Welcome! Your account was created.")

        return redirect("account")

    return render(request, "shop/auth/register.html", {"form": form})


@login_required
def account(request):
    if request.method == "POST":
        form = AccountForm(request.POST, user=request.user)

        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your details were saved.")

            return redirect("account")
    else:
        form = AccountForm(user=request.user)

    orders = Paginator(request.user.orders.all(), 10).get_page(request.GET.get("page"))

    return render(request, "shop/account.html", {"form": form, "orders": orders, "page_obj": orders})


# --- Staff dashboard --------------------------------------------------------


@staff_required
def dashboard(request):
    counted = Order.objects.exclude(status="cancelled")
    by_status = dict(Order.objects.order_by().values_list("status").annotate(total=Count("id")))

    return render(
        request,
        "shop/dashboard.html",
        {
            "revenue": counted.filter(payment_status="paid").aggregate(total=Sum("total"))["total"] or 0,
            "orders_count": counted.count(),
            "pending_count": by_status.get("pending", 0),
            "customers_count": get_user_model().objects.filter(is_staff=False).count(),
            "low_stock": Product.objects.filter(stock__lte=5).order_by("stock", "name")[:8],
            "recent": Order.objects.all()[:8],
            "by_status": [(label, by_status.get(key, 0)) for key, label in Order.STATUS_CHOICES],
        },
    )
