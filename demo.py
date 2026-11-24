"""
Demo data. Every product, price and account here is fictional.
"""

from django.contrib.auth import get_user_model

from .models import Category, Coupon, Product

CATALOG = {
    "Electronics": [
        ("Wireless Headphones", 8990, 6990, "Over-ear, 30 hour battery"),
        ("Smart Watch", 14990, None, "Heart rate, GPS and sleep tracking"),
        ("Portable Speaker", 5990, None, "Waterproof Bluetooth speaker"),
        ("USB-C Charger 65W", 3490, 2990, "Fast charging for laptop and phone"),
    ],
    "Home & Kitchen": [
        ("Ceramic Coffee Mug Set", 2490, None, "Set of four, dishwasher safe"),
        ("Cast Iron Skillet", 3990, None, "Pre-seasoned 12 inch skillet"),
        ("Linen Throw Blanket", 4590, 3690, "Soft and breathable"),
        ("Desk Lamp", 2990, None, "Dimmable LED with USB port"),
    ],
    "Clothing": [
        ("Cotton T-Shirt", 1990, None, "Classic fit, 100% cotton"),
        ("Denim Jacket", 7990, 5990, "Medium wash, relaxed fit"),
        ("Running Shoes", 9990, None, "Lightweight with extra cushioning"),
        ("Wool Beanie", 1790, None, "Warm knit hat"),
    ],
    "Sports & Outdoors": [
        ("Yoga Mat", 2790, None, "Non-slip, 6mm thick"),
        ("Insulated Water Bottle", 2290, None, "Keeps drinks cold for 24 hours"),
        ("Camping Backpack 40L", 8490, 7490, "Water resistant with rain cover"),
        ("Resistance Bands", 1590, None, "Set of five levels"),
    ],
}

DEMO_PASSWORD = "password"


def seed_demo() -> None:
    """Creates the demo admin, a demo customer, categories, products and two coupons."""
    User = get_user_model()

    User.objects.create_user(
        username="admin@example.com",
        email="admin@example.com",
        password=DEMO_PASSWORD,
        first_name="Store Admin",
        is_staff=True,
        is_superuser=True,
    )
    User.objects.create_user(
        username="customer@example.com",
        email="customer@example.com",
        password=DEMO_PASSWORD,
        first_name="Demo Customer",
    )

    sku = 1000

    for order, (name, products) in enumerate(CATALOG.items(), start=1):
        category = Category.objects.create(
            name=name, sort_order=order, description=f"Browse our {name} selection."
        )

        for index, (title, price, sale, short) in enumerate(products):
            sku += 1
            Product.objects.create(
                category=category,
                name=title,
                sku=f"SKU-{sku}",
                short_description=short,
                description=f"{short}.\n\nThis is a demo product. Replace it with your own from the admin panel.",
                price=price,
                sale_price=sale,
                stock=25,
                is_featured=index < 2,
            )

    Coupon.objects.create(code="WELCOME10", type=Coupon.PERCENT, value=10)
    Coupon.objects.create(code="SAVE5", type=Coupon.FIXED, value=500, min_subtotal=2000)
