import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .money import round_half_up


def unique_slug(model, value: str, instance=None, max_length: int = 140) -> str:
    """Builds a slug from `value` that no other row of `model` uses yet."""
    base = (slugify(value) or "item")[:max_length]
    slug, number = base, 2
    others = model.objects.all()

    if instance is not None and instance.pk:
        others = others.exclude(pk=instance.pk)

    while others.filter(slug=slug).exists():
        suffix = f"-{number}"
        slug = base[: max_length - len(suffix)] + suffix
        number += 1

    return slug


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_product_counts(self):
        return self.annotate(products_count=Count("products", filter=Q(products__is_active=True)))


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Category, self.name, self, 140)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("category", args=[self.slug])


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def featured(self):
        return self.filter(is_featured=True)

    def search(self, term: str | None):
        term = (term or "").strip()

        if not term:
            return self

        return self.filter(
            Q(name__icontains=term) | Q(sku__icontains=term) | Q(short_description__icontains=term)
        )


class Product(models.Model):
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField(max_length=60, unique=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    # Prices are integer cents: 1990 means 19.90.
    price = models.PositiveIntegerField()
    sale_price = models.PositiveIntegerField(null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to="products/", blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Product, self.name, self, 220)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("product", args=[self.slug])

    @property
    def on_sale(self) -> bool:
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def current_price(self) -> int:
        """The price a customer actually pays, in cents."""
        return self.sale_price if self.on_sale else self.price

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def image_url(self) -> str | None:
        return self.image.url if self.image else None


class Coupon(models.Model):
    PERCENT = "percent"
    FIXED = "fixed"
    TYPE_CHOICES = [(PERCENT, "Percent"), (FIXED, "Fixed amount")]

    code = models.CharField(max_length=40, unique=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=PERCENT)
    # A percentage (10 means 10%) or an amount in cents, depending on `type`.
    value = models.PositiveIntegerField()
    min_subtotal = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def problem_for(self, subtotal: int) -> str | None:
        """An error message when the coupon cannot be used, or None when it is valid."""
        if not self.is_active:
            return "This coupon is not active."
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return "This coupon has expired."
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return "This coupon has reached its usage limit."
        if subtotal < self.min_subtotal:
            return "Your cart does not reach the minimum amount for this coupon."
        return None

    def discount_for(self, subtotal: int) -> int:
        """Discount in cents for the given subtotal (never more than the subtotal)."""
        if self.type == self.PERCENT:
            discount = round_half_up(Decimal(subtotal) * self.value / 100)
        else:
            discount = self.value

        return min(discount, subtotal)


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    number = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_method = models.CharField(max_length=30)
    payment_status = models.CharField(max_length=20, default="unpaid")
    payment_reference = models.CharField(max_length=190, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    customer_name = models.CharField(max_length=120)
    customer_email = models.EmailField(max_length=190)
    customer_phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=190)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    notes = models.TextField(blank=True)

    # All amounts are integer cents.
    subtotal = models.PositiveIntegerField(default=0)
    discount = models.PositiveIntegerField(default=0)
    shipping = models.PositiveIntegerField(default=0)
    tax = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.number

    @staticmethod
    def make_number(pk: int) -> str:
        """A readable unique order number such as DS-2026-000042."""
        return f"{settings.SHOP['order_prefix']}-{timezone.now().year}-{pk:06d}"

    @staticmethod
    def temporary_number() -> str:
        return uuid.uuid4().hex[:30]

    @property
    def status_label(self) -> str:
        return dict(self.STATUS_CHOICES).get(self.status, self.status.title())

    @property
    def payment_label(self) -> str:
        from .payments import PaymentManager

        return PaymentManager().label_for(self.payment_method)

    @property
    def is_paid(self) -> bool:
        return self.payment_status == "paid"

    def mark_paid(self, reference: str | None = None) -> bool:
        """Marks the order as paid once. Safe to call again from repeated webhooks."""
        if self.is_paid:
            return False

        self.payment_status = "paid"
        if reference:
            self.payment_reference = str(reference)[:190]
        self.paid_at = timezone.now()
        if self.status == "pending":
            self.status = "processing"
        self.save(update_fields=["payment_status", "payment_reference", "paid_at", "status", "updated_at"])

        return True


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items"
    )
    # The name, SKU and price are copied so old orders never change when a product does.
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=60)
    price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    total = models.PositiveIntegerField()

    def __str__(self) -> str:
        return f"{self.quantity} x {self.name}"
