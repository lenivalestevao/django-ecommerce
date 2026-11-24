import hashlib
import hmac
import json
import time
from unittest import mock

import requests
from django.test import override_settings
from django.urls import reverse

from shop.models import Order

from .base import ALL_GATEWAYS, NO_GATEWAYS, FakeHttp, FakeResponse, ShopTestCase, make_coupon, make_order, make_product

# The gateways are tested with faked HTTP answers. Before going live, also run a real payment
# in each provider's sandbox: these tests cannot prove the live APIs still match.


def only(**gateways):
    """PAYMENTS with just the named gateways switched on."""
    return {name: (ALL_GATEWAYS[name] if name in gateways else NO_GATEWAYS[name]) for name in NO_GATEWAYS}


def details(method):
    return {
        "customer_name": "Jane",
        "customer_email": "jane@example.com",
        "address": "1 Main St",
        "city": "Town",
        "postcode": "12345",
        "country": "US",
        "payment_method": method,
    }


class PaymentTests(ShopTestCase):
    def checkout_with(self, method, product=None):
        product = product or make_product(price=5000)
        self.client.post(reverse("cart_add", args=[product.slug]))

        return self.client.post(reverse("checkout"), details(method))

    def open_session_for(self, order):
        session = self.client.session
        session["my_orders"] = [order.number]
        session.save()

    def return_url(self, order, query):
        return reverse("payment_return", args=[order.number]) + "?" + query

    def test_gateways_are_hidden_until_configured(self):
        self.client.post(reverse("cart_add", args=[make_product().slug]))

        response = self.client.get(reverse("checkout"))
        for name in ("Stripe", "PayPal", "Mercado Pago"):
            self.assertNotContains(response, name)
        self.assertContains(response, "Cash on delivery")

        with override_settings(PAYMENTS=ALL_GATEWAYS):
            response = self.client.get(reverse("checkout"))
            for name in ("Stripe", "PayPal", "Mercado Pago"):
                self.assertContains(response, name)

    # --- Stripe ---------------------------------------------------------------

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_redirects_to_the_hosted_page_and_confirms_the_payment(self):
        create = FakeResponse({"id": "cs_1", "url": "https://checkout.stripe.test/pay"})

        with FakeHttp([("POST", "/v1/checkout/sessions", create)]) as http:
            response = self.checkout_with("stripe")

        self.assertRedirects(response, "https://checkout.stripe.test/pay", fetch_redirect_response=False)

        sent = http.calls[0][2]["data"]
        self.assertEqual(sent["line_items[0][price_data][unit_amount]"], 5000)
        self.assertEqual(sent["line_items[1][price_data][unit_amount]"], 800)  # shipping
        self.assertIn("{CHECKOUT_SESSION_ID}", sent["success_url"])
        self.assertEqual(http.calls[0][2]["headers"]["Authorization"], "Bearer sk_test_x")

        order = Order.objects.get()
        self.assertEqual(order.payment_reference, "cs_1")
        self.assertFalse(order.is_paid)

        paid = FakeResponse({"payment_status": "paid", "payment_intent": "pi_1", "client_reference_id": order.number})
        with FakeHttp([("GET", "/v1/checkout/sessions/cs_1", paid)]):
            response = self.client.get(self.return_url(order, "gateway=stripe&session_id=cs_1"), follow=True)

        self.assertContains(response, "Payment received")
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "processing")
        self.assertEqual(order.payment_reference, "pi_1")

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_gets_one_line_when_the_discount_is_bigger_than_shipping_and_tax(self):
        make_coupon(code="HALF", value=50)
        product = make_product(price=20000)
        self.client.post(reverse("cart_add", args=[product.slug]))
        self.client.post(reverse("coupon_apply"), {"code": "HALF"})
        create = FakeResponse({"id": "cs_5", "url": "https://checkout.stripe.test/pay"})

        with FakeHttp([("POST", "/v1/checkout/sessions", create)]) as http:
            self.client.post(reverse("checkout"), details("stripe"))

        order = Order.objects.get()
        sent = http.calls[0][2]["data"]
        self.assertEqual(order.total, 10000)
        self.assertEqual(sent["line_items[0][price_data][unit_amount]"], 10000)
        self.assertNotIn("line_items[1][quantity]", sent)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_return_does_not_mark_unpaid_sessions_as_paid(self):
        order = make_order(payment_method="stripe", payment_reference="cs_2")
        self.open_session_for(order)
        unpaid = FakeResponse({"payment_status": "unpaid", "client_reference_id": order.number})

        with FakeHttp([("GET", "/v1/checkout/sessions/cs_2", unpaid)]):
            response = self.client.get(self.return_url(order, "gateway=stripe"), follow=True)

        self.assertContains(response, "not received the payment yet")
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_return_ignores_a_session_that_belongs_to_another_order(self):
        order = make_order(payment_method="stripe", payment_reference="cs_3")
        self.open_session_for(order)
        other = FakeResponse({"payment_status": "paid", "client_reference_id": "SOMEONE-ELSE"})

        with FakeHttp([("GET", "/v1/checkout/sessions/cs_3", other)]):
            self.client.get(self.return_url(order, "gateway=stripe"))

        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_webhook_needs_a_valid_signature(self):
        order = make_order(payment_method="stripe")
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_9",
                        "payment_status": "paid",
                        "client_reference_id": order.number,
                        "payment_intent": "pi_9",
                    }
                },
            }
        )

        def call(signature):
            return self.client.post(
                reverse("payment_webhook", args=["stripe"]),
                data=payload,
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE=signature,
            )

        self.assertEqual(call(f"t={int(time.time())},v1=bad").status_code, 400)
        self.assertEqual(self.client.post(reverse("payment_webhook", args=["stripe"]), data=payload, content_type="application/json").status_code, 400)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

        timestamp = int(time.time())
        signature = hmac.new(b"whsec_test", f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(call(f"t={timestamp},v1={signature}").status_code, 204)

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.payment_reference, "pi_9")

    @override_settings(PAYMENTS=only(stripe=True))
    def test_stripe_webhook_rejects_an_old_timestamp(self):
        order = make_order(payment_method="stripe")
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"payment_status": "paid", "client_reference_id": order.number}}})
        timestamp = int(time.time()) - 3600
        signature = hmac.new(b"whsec_test", f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("payment_webhook", args=["stripe"]),
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    # --- PayPal ---------------------------------------------------------------

    @override_settings(PAYMENTS=only(paypal=True))
    def test_paypal_creates_the_order_and_captures_on_return(self):
        token = ("POST", "/v1/oauth2/token", FakeResponse({"access_token": "tok"}))
        capture = (
            "POST",
            "/v2/checkout/orders/PP1/capture",
            FakeResponse({"status": "COMPLETED", "purchase_units": [{"payments": {"captures": [{"id": "CAP1"}]}}]}),
        )
        create = (
            "POST",
            "/v2/checkout/orders",
            FakeResponse({"id": "PP1", "links": [{"rel": "approve", "href": "https://paypal.test/approve"}]}),
        )

        with FakeHttp([token, capture, create]) as http:
            response = self.checkout_with("paypal")
            self.assertRedirects(response, "https://paypal.test/approve", fetch_redirect_response=False)

            order = Order.objects.get()
            self.assertEqual(order.payment_reference, "PP1")

            body = http.calls[1][2]["json"]
            self.assertEqual(body["purchase_units"][0]["amount"]["value"], "58.00")

            self.client.get(self.return_url(order, "gateway=paypal&token=PP1"))

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.payment_reference, "CAP1")

    @override_settings(PAYMENTS=only(paypal=True))
    def test_paypal_return_with_a_foreign_token_does_not_capture(self):
        order = make_order(payment_method="paypal", payment_reference="PP1")
        self.open_session_for(order)

        with FakeHttp() as http:
            self.client.get(self.return_url(order, "gateway=paypal&token=OTHER"))

        self.assertEqual(http.calls, [])
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    # --- Mercado Pago ---------------------------------------------------------

    @override_settings(PAYMENTS=only(mercadopago=True))
    def test_mercado_pago_creates_a_preference_and_confirms_through_the_webhook(self):
        preference = FakeResponse({"id": "pref_1", "init_point": "https://mp.test/pay"})

        with FakeHttp([("POST", "/checkout/preferences", preference)]) as http:
            response = self.checkout_with("mercadopago")

        self.assertRedirects(response, "https://mp.test/pay", fetch_redirect_response=False)
        order = Order.objects.get()
        sent = http.calls[0][2]["json"]
        self.assertEqual(sent["external_reference"], order.number)
        self.assertEqual(sent["notification_url"], "http://testserver/payment/webhook/mercadopago/")

        payment = FakeResponse({"status": "approved", "external_reference": order.number, "transaction_amount": order.total / 100})
        with FakeHttp([("GET", "/v1/payments/555", payment)]):
            response = self.client.post(
                reverse("payment_webhook", args=["mercadopago"]),
                data={"type": "payment", "data": {"id": "555"}},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 204)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.payment_reference, "555")

    @override_settings(PAYMENTS=only(mercadopago=True))
    def test_mercado_pago_confirms_when_the_customer_returns(self):
        order = make_order(payment_method="mercadopago")
        self.open_session_for(order)
        payment = FakeResponse({"status": "approved", "external_reference": order.number, "transaction_amount": 50.0})

        with FakeHttp([("GET", "/v1/payments/777", payment)]):
            self.client.get(self.return_url(order, "gateway=mercadopago&payment_id=777"))

        order.refresh_from_db()
        self.assertTrue(order.is_paid)

    @override_settings(PAYMENTS=only(mercadopago=True))
    def test_mercado_pago_ignores_payments_that_do_not_cover_the_total(self):
        order = make_order(payment_method="mercadopago")
        payment = FakeResponse({"status": "approved", "external_reference": order.number, "transaction_amount": 1.0})

        with FakeHttp([("GET", "/v1/payments/556", payment)]):
            self.client.post(
                reverse("payment_webhook", args=["mercadopago"]),
                data={"type": "payment", "data": {"id": "556"}},
                content_type="application/json",
            )

        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(PAYMENTS=only(mercadopago=True))
    def test_mercado_pago_return_cannot_confirm_another_orders_payment(self):
        mine = make_order(payment_method="mercadopago")
        other = make_order(payment_method="mercadopago")
        self.open_session_for(mine)
        payment = FakeResponse({"status": "approved", "external_reference": other.number, "transaction_amount": 50.0})

        with FakeHttp([("GET", "/v1/payments/888", payment)]):
            self.client.get(self.return_url(mine, "gateway=mercadopago&payment_id=888"))

        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(mine.is_paid)
        self.assertFalse(other.is_paid)

    # --- General --------------------------------------------------------------

    def test_a_webhook_for_a_disabled_gateway_is_not_found(self):
        response = self.client.post(reverse("payment_webhook", args=["stripe"]), data="{}", content_type="application/json")

        self.assertEqual(response.status_code, 404)

    def test_webhooks_only_accept_post(self):
        with override_settings(PAYMENTS=only(stripe=True)):
            self.assertEqual(self.client.get(reverse("payment_webhook", args=["stripe"])).status_code, 405)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_a_gateway_failure_keeps_the_order_and_shows_a_message(self):
        failure = FakeResponse({"error": {"message": "boom"}}, status=500)

        with FakeHttp([("POST", "/v1/checkout/sessions", failure)]):
            response = self.checkout_with("stripe")
            order = Order.objects.get()
            self.assertRedirects(response, reverse("order", args=[order.number]), fetch_redirect_response=False)
            response = self.client.get(reverse("order", args=[order.number]))

        self.assertContains(response, "could not reach the payment provider")
        self.assertContains(response, "Pay now with")  # the customer can try again

    @override_settings(PAYMENTS=only(stripe=True))
    def test_a_network_error_also_keeps_the_order(self):
        with mock.patch("requests.post", side_effect=requests.ConnectionError("down")):
            response = self.checkout_with("stripe")

        self.assertEqual(Order.objects.count(), 1)
        self.assertRedirects(response, reverse("order", args=[Order.objects.get().number]), fetch_redirect_response=False)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_the_customer_can_retry_paying_from_the_order_page(self):
        order = make_order(payment_method="stripe")
        self.open_session_for(order)
        create = FakeResponse({"id": "cs_7", "url": "https://checkout.stripe.test/retry"})

        with FakeHttp([("POST", "/v1/checkout/sessions", create)]):
            response = self.client.post(reverse("order_pay", args=[order.number]))

        self.assertRedirects(response, "https://checkout.stripe.test/retry", fetch_redirect_response=False)

    @override_settings(PAYMENTS=only(stripe=True))
    def test_a_paid_or_cancelled_order_cannot_be_paid_again(self):
        paid = make_order(payment_method="stripe", payment_status="paid")
        cancelled = make_order(payment_method="stripe", status="cancelled")
        session = self.client.session
        session["my_orders"] = [paid.number, cancelled.number]
        session.save()

        self.assertEqual(self.client.post(reverse("order_pay", args=[paid.number])).status_code, 404)
        self.assertEqual(self.client.post(reverse("order_pay", args=[cancelled.number])).status_code, 404)

    def test_the_payment_pages_are_private_to_the_buyer(self):
        order = make_order(payment_method="stripe")

        self.assertEqual(self.client.get(reverse("payment_return", args=[order.number])).status_code, 403)
        self.assertEqual(self.client.get(reverse("payment_cancel", args=[order.number])).status_code, 403)

    def test_cancelling_the_payment_returns_to_the_order(self):
        order = make_order()
        self.open_session_for(order)

        response = self.client.get(reverse("payment_cancel", args=[order.number]), follow=True)

        self.assertContains(response, "payment was cancelled")

    def test_mark_paid_is_idempotent(self):
        order = make_order(payment_method="stripe")

        self.assertTrue(order.mark_paid("a"))
        self.assertFalse(order.mark_paid("b"))
        order.refresh_from_db()
        self.assertEqual(order.payment_reference, "a")
