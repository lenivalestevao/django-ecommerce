from django.core import mail
from django.test import Client
from django.urls import reverse

from shop.models import Order, Product

from .base import ShopTestCase, make_coupon, make_product, make_user


def details(**overrides):
    return {
        "customer_name": "Jane Buyer",
        "customer_email": "jane@example.com",
        "customer_phone": "555-0100",
        "address": "1 Main Street",
        "city": "Springfield",
        "state": "IL",
        "postcode": "62701",
        "country": "United States",
        "payment_method": "cod",
        **overrides,
    }


class CheckoutTests(ShopTestCase):
    def add(self, product, quantity=1):
        self.client.post(reverse("cart_add", args=[product.slug]), {"quantity": quantity})

    def test_an_empty_cart_redirects_to_the_cart_page(self):
        self.assertRedirects(self.client.get(reverse("checkout")), reverse("cart"))

    def test_a_guest_can_place_a_cash_on_delivery_order(self):
        product = make_product(price=5000, stock=10)
        self.add(product, 2)

        response = self.client.post(reverse("checkout"), details())

        order = Order.objects.get()
        self.assertRedirects(response, reverse("order", args=[order.number]))
        self.assertRegex(order.number, r"^DS-\d{4}-\d{6}$")
        self.assertEqual(order.total, 10000)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "unpaid")
        self.assertEqual(Product.objects.get(pk=product.pk).stock, 8)

        item = order.items.get()
        self.assertEqual((item.product_id, item.quantity, item.total), (product.pk, 2, 10000))

        # The cart is empty again and both emails went out.
        self.assertTrue(self.client.get(reverse("cart")).context["cart_count"] == 0)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])
        self.assertEqual(mail.outbox[1].to, ["shop@example.com"])
        self.assertIn(order.number, mail.outbox[0].body)

        # The buyer's session may open the order page; another visitor may not.
        self.assertContains(self.client.get(reverse("order", args=[order.number])), order.number)
        self.assertEqual(Client().get(reverse("order", args=[order.number])).status_code, 403)

    def test_the_order_keeps_the_price_paid_even_if_the_product_changes_later(self):
        product = make_product(price=3000, stock=5, name="Original Name")
        self.add(product)
        self.client.post(reverse("checkout"), details())

        product.price = 9999
        product.name = "Renamed"
        product.save()

        item = Order.objects.get().items.get()
        self.assertEqual(item.price, 3000)
        self.assertEqual(item.name, "Original Name")

    def test_the_coupon_is_recorded_and_counted(self):
        product = make_product(price=20000)
        coupon = make_coupon(code="TEN", value=10)
        self.add(product)
        self.client.post(reverse("coupon_apply"), {"code": "TEN"})

        self.client.post(reverse("checkout"), details())

        order = Order.objects.get()
        coupon.refresh_from_db()
        self.assertEqual(order.discount, 2000)
        self.assertEqual(order.coupon_id, coupon.pk)
        self.assertEqual(coupon.used_count, 1)

    def test_checkout_requires_valid_details(self):
        self.add(make_product())

        response = self.client.post(reverse("checkout"), {})
        errors = response.context["form"].errors
        for field in ("customer_name", "customer_email", "address", "payment_method"):
            self.assertIn(field, errors)

        # Stripe is off without keys, so it cannot be chosen.
        response = self.client.post(reverse("checkout"), details(payment_method="stripe"))
        self.assertIn("payment_method", response.context["form"].errors)

        self.assertEqual(Order.objects.count(), 0)

    def test_nobody_can_buy_more_than_the_stock_left(self):
        product = make_product(stock=5)
        self.add(product, 3)

        Product.objects.filter(pk=product.pk).update(stock=1)  # someone else bought most of it

        response = self.client.post(reverse("checkout"), details())

        self.assertContains(response, "only 1 of")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Product.objects.get(pk=product.pk).stock, 1)

    def test_a_logged_in_customer_sees_the_order_in_their_account(self):
        user = make_user()
        self.client.force_login(user)
        self.add(make_product())

        self.client.post(reverse("checkout"), details())

        order = Order.objects.get()
        self.assertEqual(order.user_id, user.pk)
        self.assertContains(self.client.get(reverse("account")), order.number)

    def test_an_owner_can_open_their_order_in_a_new_session(self):
        user = make_user()
        order = Order.objects.create(**{**details(), "number": "X-1", "user": user})

        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("order", args=[order.number])).status_code, 200)

    def test_a_guest_can_track_an_order_with_number_and_email(self):
        order = Order.objects.create(**{**details(), "number": "DS-2026-000009"})

        response = self.client.post(reverse("track"), {"number": order.number, "email": "wrong@example.com"})
        self.assertIn("number", response.context["form"].errors)

        response = self.client.post(reverse("track"), {"number": order.number.lower(), "email": "JANE@example.com"})
        self.assertRedirects(response, reverse("order", args=[order.number]))

    def test_the_bank_transfer_instructions_are_shown(self):
        self.add(make_product())

        response = self.client.post(reverse("checkout"), details(payment_method="bank"), follow=True)

        self.assertContains(response, "Bank transfer")
        self.assertContains(response, "as the reference")
