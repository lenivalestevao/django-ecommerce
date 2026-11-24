import json

import requests
from django.conf import settings

from ..models import Order
from ..money import to_cents
from .base import Gateway, GatewayError, absolute_url, safe_json

API = "https://api.mercadopago.com"


class MercadoPagoGateway(Gateway):
    """
    Mercado Pago Checkout Pro (preferences API).
    Docs: https://www.mercadopago.com.br/developers/en/reference/preferences/_checkout_preferences/post
    """

    key = "mercadopago"
    label = "Mercado Pago"

    @staticmethod
    def config() -> dict:
        return settings.PAYMENTS["mercadopago"]

    def enabled(self) -> bool:
        return bool(self.config()["access_token"])

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.config()['access_token']}"}

    def create_payment(self, order) -> str:
        back_url = absolute_url("payment_return", order.number) + "?gateway=mercadopago"

        try:
            response = requests.post(
                f"{API}/checkout/preferences",
                json={
                    "items": [
                        {
                            "title": f"Order {order.number}",
                            "quantity": 1,
                            "currency_id": self.config()["currency"],
                            "unit_price": round(order.total / 100, 2),
                        }
                    ],
                    "payer": {"email": order.customer_email},
                    "external_reference": order.number,
                    "back_urls": {
                        "success": back_url,
                        "pending": back_url,
                        "failure": absolute_url("payment_cancel", order.number),
                    },
                    "auto_return": "approved",
                    "notification_url": absolute_url("payment_webhook", "mercadopago"),
                },
                headers=self._headers(),
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GatewayError("Mercado Pago could not be reached.") from exc

        body = safe_json(response)

        if not response.ok or not body.get("init_point"):
            raise GatewayError("Mercado Pago could not create the payment.")

        order.payment_reference = str(body.get("id", ""))
        order.save(update_fields=["payment_reference", "updated_at"])

        return body["init_point"]

    def confirm(self, order, request) -> bool:
        # Never trust the query string alone: ask the API for the payment and check it.
        payment_id = request.GET.get("payment_id")

        if payment_id:
            self._sync_payment(payment_id, expected=order)

        order.refresh_from_db()

        return order.is_paid

    def webhook(self, request) -> None:
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            body = {}

        if not isinstance(body, dict):
            body = {}

        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        payment_id = (
            data.get("id") or request.GET.get("data.id") or request.GET.get("data_id") or request.GET.get("id")
        )
        kind = body.get("type") or request.GET.get("topic") or request.GET.get("type")

        if payment_id and kind in ("payment", None):
            self._sync_payment(str(payment_id))

    def _sync_payment(self, payment_id: str, expected=None) -> None:
        """Fetches the payment from Mercado Pago and marks the matching order as paid when approved."""
        response = requests.get(f"{API}/v1/payments/{payment_id}", headers=self._headers(), timeout=20)
        body = safe_json(response)

        if not response.ok or body.get("status") != "approved":
            return

        order = Order.objects.filter(number=body.get("external_reference", "")).first()

        if order is None or (expected is not None and expected.pk != order.pk):
            return

        # The approved amount must cover the order total.
        if to_cents(body.get("transaction_amount") or 0) >= order.total:
            order.mark_paid(payment_id)
