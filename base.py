"""Shared helpers for the tests."""

import itertools
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from shop.models import Category, Coupon, Order, OrderItem, Product

TEST_SHOP = {
    "name": "Test Shop",
    "tagline": "Everything you need",
    "currency": "$",
    "shipping_fee": 800,
    "free_shipping_over": 10000,
    "tax_rate": 0,
    "per_page": 12,
    "contact_email": "shop@example.com",
    "order_prefix": "DS",
    "payment_methods": {"cod": "Cash on delivery", "bank": "Bank transfer"},
}

NO_GATEWAYS = {
    "stripe": {"secret": "", "webhook_secret": "", "currency": "usd"},
    "paypal": {"client_id": "", "secret": "", "sandbox": True, "currency": "USD"},
    "mercadopago": {"access_token": "", "currency": "BRL"},
}

ALL_GATEWAYS = {
    "stripe": {"secret": "sk_test_x", "webhook_secret": "whsec_test", "currency": "usd"},
    "paypal": {"client_id": "id", "secret": "secret", "sandbox": True, "currency": "USD"},
    "mercadopago": {"access_token": "APP_USR-x", "currency": "BRL"},
}

# A fast hasher keeps the tests quick. Real passwords still use Django's strong default.
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

isolated = override_settings(
    SHOP=TEST_SHOP,
    PAYMENTS=NO_GATEWAYS,
    PASSWORD_HASHERS=FAST_HASHERS,
    SITE_URL="http://testserver",
)


@isolated
class ShopTestCase(TestCase):
    """Every test starts with the default shop settings and no payment gateway switched on."""


_numbers = itertools.count(1)


def make_category(**extra) -> Category:
    n = next(_numbers)

    return Category.objects.create(**{"name": f"Category {n}", **extra})


def make_product(**extra) -> Product:
    n = next(_numbers)
    defaults = {"name": f"Product {n}", "sku": f"SKU-T{n}", "price": 2500, "stock": 10}

    return Product.objects.create(**{**defaults, **extra})


def make_coupon(**extra) -> Coupon:
    defaults = {"code": f"CODE{next(_numbers)}", "type": Coupon.PERCENT, "value": 10}

    return Coupon.objects.create(**{**defaults, **extra})


def make_user(email="user@example.com", password="password", **extra):
    return get_user_model().objects.create_user(username=email, email=email, password=password, **extra)


def make_staff(email="boss@example.com", password="password"):
    return make_user(email, password, is_staff=True, is_superuser=True)


def make_order(with_item=True, **extra) -> Order:
    n = next(_numbers)
    defaults = {
        "number": f"T-{n:06d}",
        "payment_method": "cod",
        "customer_name": "Test Buyer",
        "customer_email": "buyer@example.com",
        "address": "1 Main Street",
        "city": "Springfield",
        "postcode": "12345",
        "country": "United States",
        "subtotal": 5000,
        "total": 5000,
    }
    order = Order.objects.create(**{**defaults, **extra})

    if with_item:
        OrderItem.objects.create(order=order, name="Thing", sku="T-1", price=5000, quantity=1, total=5000)

    return order


def yesterday():
    return timezone.now() - timedelta(days=1)


class FakeResponse:
    """Just enough of requests.Response for the gateways."""

    def __init__(self, data=None, status=200):
        self._data = data if data is not None else {}
        self.status_code = status
        self.ok = status < 400

    def json(self):
        return self._data


class FakeHttp:
    """
    Replaces requests.get and requests.post. `routes` is a list of (method, url fragment, response);
    the first match wins. Any request without a route fails the test, so nothing reaches the network.
    """

    def __init__(self, routes=()):
        self.routes = list(routes)
        self.calls = []

    def _handle(self, method):
        def handler(url, **kwargs):
            self.calls.append((method, url, kwargs))

            for route_method, fragment, response in self.routes:
                if route_method == method and fragment in url:
                    return response

            raise AssertionError(f"Unexpected HTTP request: {method} {url}")

        return handler

    def __enter__(self):
        self._patches = [
            mock.patch("requests.get", side_effect=self._handle("GET")),
            mock.patch("requests.post", side_effect=self._handle("POST")),
        ]
        for patch in self._patches:
            patch.start()

        return self

    def __exit__(self, *exc):
        for patch in self._patches:
            patch.stop()

        return False
