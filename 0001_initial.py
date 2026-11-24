import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name_plural": "categories",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40, unique=True)),
                (
                    "type",
                    models.CharField(
                        choices=[("percent", "Percent"), ("fixed", "Fixed amount")], default="percent", max_length=10
                    ),
                ),
                ("value", models.PositiveIntegerField()),
                ("min_subtotal", models.PositiveIntegerField(default=0)),
                ("max_uses", models.PositiveIntegerField(blank=True, null=True)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["code"],
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("sku", models.CharField(max_length=60, unique=True)),
                ("short_description", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField(blank=True)),
                ("price", models.PositiveIntegerField()),
                ("sale_price", models.PositiveIntegerField(blank=True, null=True)),
                ("stock", models.PositiveIntegerField(default=0)),
                ("image", models.ImageField(blank=True, upload_to="products/")),
                ("is_active", models.BooleanField(default=True)),
                ("is_featured", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="shop.category",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=40, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("shipped", "Shipped"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("payment_method", models.CharField(max_length=30)),
                ("payment_status", models.CharField(default="unpaid", max_length=20)),
                ("payment_reference", models.CharField(blank=True, max_length=190)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("customer_name", models.CharField(max_length=120)),
                ("customer_email", models.EmailField(max_length=190)),
                ("customer_phone", models.CharField(blank=True, max_length=40)),
                ("address", models.CharField(max_length=190)),
                ("city", models.CharField(max_length=100)),
                ("state", models.CharField(blank=True, max_length=100)),
                ("postcode", models.CharField(max_length=20)),
                ("country", models.CharField(max_length=100)),
                ("notes", models.TextField(blank=True)),
                ("subtotal", models.PositiveIntegerField(default=0)),
                ("discount", models.PositiveIntegerField(default=0)),
                ("shipping", models.PositiveIntegerField(default=0)),
                ("tax", models.PositiveIntegerField(default=0)),
                ("total", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "coupon",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="shop.coupon",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("sku", models.CharField(max_length=60)),
                ("price", models.PositiveIntegerField()),
                ("quantity", models.PositiveIntegerField()),
                ("total", models.PositiveIntegerField()),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shop.order"
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_items",
                        to="shop.product",
                    ),
                ),
            ],
        ),
    ]
