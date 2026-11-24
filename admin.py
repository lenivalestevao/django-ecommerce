import csv

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from .models import Category, Coupon, Order, OrderItem, Product
from .money import format_money, to_cents, to_input
from .services import restock

admin.site.site_header = "Shop admin"
admin.site.site_title = "Shop admin"


# --- Categories and products -------------------------------------------------


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class ProductAdminForm(forms.ModelForm):
    """Prices are typed in normal units (19.90) and stored as cents."""

    price = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    sale_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        help_text="Optional. Must be lower than the price.",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.initial["price"] = to_input(self.instance.price)
            if self.instance.sale_price is not None:
                self.initial["sale_price"] = to_input(self.instance.sale_price)

    def clean_price(self):
        return to_cents(self.cleaned_data["price"])

    def clean_sale_price(self):
        value = self.cleaned_data.get("sale_price")

        return None if value is None else to_cents(value)

    def clean(self):
        cleaned = super().clean()
        price, sale_price = cleaned.get("price"), cleaned.get("sale_price")

        if price is not None and sale_price is not None and sale_price >= price:
            self.add_error("sale_price", "The sale price must be lower than the price.")

        return cleaned


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "sku", "category", "price_display", "stock", "is_active", "is_featured")
    list_editable = ("stock", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "category")
    search_fields = ("name", "sku")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Price", ordering="price")
    def price_display(self, obj):
        if obj.on_sale:
            return f"{format_money(obj.sale_price)} (was {format_money(obj.price)})"

        return format_money(obj.price)


# --- Coupons ----------------------------------------------------------------


class CouponAdminForm(forms.ModelForm):
    """A percent coupon takes a number like 10. A fixed coupon takes an amount like 5.00."""

    value = forms.DecimalField(
        min_value=0, max_digits=10, decimal_places=2, help_text="Percent (10 = 10%) or an amount, depending on the type."
    )
    min_subtotal = forms.DecimalField(
        required=False, min_value=0, max_digits=10, decimal_places=2, label="Minimum cart amount"
    )

    class Meta:
        model = Coupon
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if self.instance.type == Coupon.FIXED:
                self.initial["value"] = to_input(self.instance.value)
            else:
                self.initial["value"] = self.instance.value
            self.initial["min_subtotal"] = to_input(self.instance.min_subtotal)

    def clean_min_subtotal(self):
        return to_cents(self.cleaned_data.get("min_subtotal"))

    def clean(self):
        cleaned = super().clean()
        kind, value = cleaned.get("type"), cleaned.get("value")

        if kind is None or value is None:
            return cleaned

        if kind == Coupon.PERCENT:
            if value != value.to_integral_value() or value > 100:
                self.add_error("value", "A percent coupon needs a whole number from 0 to 100.")
            else:
                cleaned["value"] = int(value)
        else:
            cleaned["value"] = to_cents(value)

        return cleaned


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    form = CouponAdminForm
    list_display = ("code", "type", "value_display", "used_count", "max_uses", "expires_at", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("code",)

    @admin.display(description="Value")
    def value_display(self, obj):
        return f"{obj.value}%" if obj.type == Coupon.PERCENT else format_money(obj.value)


# --- Orders -----------------------------------------------------------------


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("name", "sku", "price_display", "quantity", "total_display")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Price")
    def price_display(self, obj):
        return format_money(obj.price)

    @admin.display(description="Total")
    def total_display(self, obj):
        return format_money(obj.total)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer_name", "status", "payment_status", "payment_method", "total_display", "created_at")
    list_filter = ("status", "payment_status", "payment_method")
    search_fields = ("number", "customer_name", "customer_email")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    actions = ["mark_paid", "mark_processing", "mark_shipped", "mark_completed", "mark_cancelled", "export_csv"]

    fields = (
        "number",
        "status",
        "payment_method",
        "payment_status",
        "payment_reference",
        "paid_at",
        "customer_name",
        "customer_email",
        "customer_phone",
        "address",
        "city",
        "state",
        "postcode",
        "country",
        "notes",
        "subtotal_display",
        "discount_display",
        "shipping_display",
        "tax_display",
        "total_display",
        "coupon",
        "user",
        "created_at",
    )
    # Only the status can be edited. Everything else is a record of what the customer ordered.
    readonly_fields = tuple(name for name in fields if name != "status")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Total", ordering="total")
    def total_display(self, obj):
        return format_money(obj.total)

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return format_money(obj.subtotal)

    @admin.display(description="Discount")
    def discount_display(self, obj):
        return format_money(obj.discount)

    @admin.display(description="Shipping")
    def shipping_display(self, obj):
        return format_money(obj.shipping)

    @admin.display(description="Tax")
    def tax_display(self, obj):
        return format_money(obj.tax)

    def save_model(self, request, obj, form, change):
        previous = form.initial.get("status")
        super().save_model(request, obj, form, change)

        # Cancelling gives the stock back once.
        if change and "status" in form.changed_data and previous != "cancelled" and obj.status == "cancelled":
            restock(obj)

    def _set_status(self, request, queryset, status):
        changed = 0

        for order in queryset:
            if order.status == status:
                continue

            was_cancelled = order.status == "cancelled"
            order.status = status
            order.save(update_fields=["status", "updated_at"])
            changed += 1

            if status == "cancelled" and not was_cancelled:
                restock(order)

        self.message_user(request, f"{changed} order(s) set to {status}.", messages.SUCCESS)

    @admin.action(description="Mark selected orders as paid")
    def mark_paid(self, request, queryset):
        count = sum(1 for order in queryset if order.mark_paid())
        self.message_user(request, f"{count} order(s) marked as paid.", messages.SUCCESS)

    @admin.action(description="Set status: processing")
    def mark_processing(self, request, queryset):
        self._set_status(request, queryset, "processing")

    @admin.action(description="Set status: shipped")
    def mark_shipped(self, request, queryset):
        self._set_status(request, queryset, "shipped")

    @admin.action(description="Set status: completed")
    def mark_completed(self, request, queryset):
        self._set_status(request, queryset, "completed")

    @admin.action(description="Set status: cancelled (puts the stock back)")
    def mark_cancelled(self, request, queryset):
        self._set_status(request, queryset, "cancelled")

    @admin.action(description="Export selected orders as CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="orders-{timezone.now():%Y-%m-%d}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Number", "Date", "Customer", "Email", "Status", "Payment", "Paid", "Subtotal", "Discount", "Shipping", "Tax", "Total"]
        )

        for order in queryset:
            writer.writerow(
                [
                    order.number,
                    order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    order.customer_name,
                    order.customer_email,
                    order.status,
                    order.payment_method,
                    order.payment_status,
                    to_input(order.subtotal),
                    to_input(order.discount),
                    to_input(order.shipping),
                    to_input(order.tax),
                    to_input(order.total),
                ]
            )

        return response
