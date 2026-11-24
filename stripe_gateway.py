import hashlib
import hmac
import json
import time

import requests
from django.conf import settings

from ..models import Order
from .base import Gateway, GatewayError, WebhookError, absolute_url, safe_json

API = "https://api.stripe.com/v1"


class StripeGateway(Gateway):
    """
    Stripe Checkout (hosted page) through the REST API.
    Docs: https://docs.stripe.com/api/checkout/sessions
    """

    key = "stripe"
    label = "Credit card (Stripe)"

    @staticmethod
    def config() -> dict:
        return settings.PAYMENTS["stripe"]

    def enabled(self) -> bool:
        return bool(self.config()["secret"])

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.config()['secret']}"}

    def create_payment(self, order) -> str:
        currency = self.config()["currency"]
        data = {
            "mode": "payment",
            "client_reference_id": order.number,
            "customer_email": order.customer_email,
            "success_url": absolute_url("payment_return", order.number) + "?gateway=stripe&session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": absolute_url("payment_cancel", order.number),
            "metadata[order]": order.number,
        }

        lines = [(item.name, item.price, item.quantity) for item in order.items.all()]

        # Shipping, tax and discount are sent as one extra line so the Stripe total matches the order.
        # A discount bigger than shipping plus tax cannot be a negative line, so then the whole
        # order goes as a single line with the final total.
        extra = order.shipping + order.tax - order.discount
        if extra < 0:
            lines = [(f"Order {order.number}", order.total, 1)]
        elif extra > 0:
            lines.append(("Shipping, tax and discounts", extra, 1))

        for i, (name, unit_amount, quantity) in enumerate(lines):
            data[f"line_items[{i}][quantity]"] = quantity
            data[f"line_items[{i}][price_data][currency]"] = currency
            data[f"line_items[{i}][price_data][unit_amount]"] = unit_amount
            data[f"line_items[{i}][price_data][product_data][name]"] = name

        try:
            response = requests.post(f"{API}/checkout/sessions", data=data, headers=self._headers(), timeout=20)
        except requests.RequestException as exc:
            raise GatewayError("Stripe could not be reached.") from exc

        body = safe_json(response)

        if not response.ok or not body.get("url"):
            message = (body.get("error") or {}).get("message", "unknown error")
            raise GatewayError(f"Stripe could not create the payment: {message}")

        order.payment_reference = body.get("id", "")
        order.save(update_fields=["payment_reference", "updated_at"])

        return body["url"]

    def confirm(self, order, request) -> bool:
        session_id = request.GET.get("session_id") or order.payment_reference

        if not session_id:
            return False

        response = requests.get(f"{API}/checkout/sessions/{session_id}", headers=self._headers(), timeout=20)
        body = safe_json(response)

        if response.ok and body.get("payment_status") == "paid" and body.get("client_reference_id") == order.number:
            order.mark_paid(body.get("payment_intent") or session_id)

        order.refresh_from_db()

        return order.is_paid

    def webhook(self, request) -> None:
        payload = request.body

        if not self._valid_signature(payload, request.headers.get("Stripe-Signature", "")):
            raise WebhookError("Invalid signature")

        try:
            event = json.loads(payload)
        except ValueError as exc:
            raise WebhookError("Invalid payload") from exc

        if event.get("type") != "checkout.session.completed":
            return

        session = (event.get("data") or {}).get("object") or {}

        if session.get("payment_status") == "paid":
            order = Order.objects.filter(number=session.get("client_reference_id", "")).first()
            if order is not None:
                order.mark_paid(session.get("payment_intent") or session.get("id"))

    def _valid_signature(self, payload: bytes, header: str) -> bool:
        """Verifies the Stripe-Signature header (HMAC SHA-256 over "timestamp.payload")."""
        secret = self.config()["webhook_secret"]

        if not secret or not header:
            return False

        timestamp = None
        signatures = []

        for part in header.split(","):
            name, _, value = part.partition("=")
            if name == "t":
                timestamp = value
            elif name == "v1":
                signatures.append(value)

        try:
            if timestamp is None or abs(time.time() - int(timestamp)) > 300:
                return False
        except ValueError:
            return False

        expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()

        return any(hmac.compare_digest(expected, signature) for signature in signatures)
