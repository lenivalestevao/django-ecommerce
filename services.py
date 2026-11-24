from django.db import transaction
from django.db.models import F

from .cart import Cart
from .models import Coupon, Order, OrderItem, Product


class CheckoutError(Exception):
    """The order could not be placed. The message is safe to show to the customer."""


def place_order(cart: Cart, data: dict, user=None) -> Order:
    """
    Turns the cart into an order inside a transaction, locking the products so stock
    cannot go negative when two customers buy the last unit at the same time.
    `data` is the validated checkout form.
    """
    with transaction.atomic():
        lines = cart.lines()

        if not lines:
            raise CheckoutError("Your cart is empty.")

        locked = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=[line.product.pk for line in lines])
        }

        for line in lines:
            product = locked.get(line.product.pk)

            if product is None or product.stock < line.quantity:
                left = product.stock if product else 0
                raise CheckoutError(f'Sorry, only {left} of "{line.product.name}" left in stock.')

        coupon = cart.coupon()
        totals = cart.totals()

        order = Order.objects.create(
            number=Order.temporary_number(),
            user=user,
            coupon=coupon,
            status="pending",
            payment_method=data["payment_method"],
            payment_status="unpaid",
            customer_name=data["customer_name"],
            customer_email=data["customer_email"],
            customer_phone=data.get("customer_phone", ""),
            address=data["address"],
            city=data["city"],
            state=data.get("state", ""),
            postcode=data["postcode"],
            country=data["country"],
            notes=data.get("notes", ""),
            subtotal=totals.subtotal,
            discount=totals.discount,
            shipping=totals.shipping,
            tax=totals.tax,
            total=totals.total,
        )
        order.number = Order.make_number(order.pk)
        order.save(update_fields=["number"])

        for line in lines:
            product = locked[line.product.pk]

            OrderItem.objects.create(
                order=order,
                product=product,
                name=product.name,
                sku=product.sku,
                price=product.current_price,
                quantity=line.quantity,
                total=product.current_price * line.quantity,
            )
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - line.quantity)

        if coupon is not None:
            Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)

        return order


def restock(order: Order) -> None:
    """Puts stock and the coupon use back when an order is cancelled."""
    with transaction.atomic():
        for item in order.items.select_related("product"):
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)

        if order.coupon_id:
            Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
