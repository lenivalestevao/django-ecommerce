import requests
from django.conf import settings

from .base import Gateway, GatewayError, absolute_url, safe_json


class PayPalGateway(Gateway):
    """
    PayPal Checkout through the Orders v2 REST API (redirect flow).
    Docs: https://developer.paypal.com/docs/api/orders/v2/
    """

    key = "paypal"
    label = "PayPal"

    @staticmethod
    def config() -> dict:
        return settings.PAYMENTS["paypal"]

    def enabled(self) -> bool:
        config = self.config()

        return bool(config["client_id"] and config["secret"])

    def _base(self) -> str:
        return "https://api-m.sandbox.paypal.com" if self.config()["sandbox"] else "https://api-m.paypal.com"

    def _token(self) -> str:
        config = self.config()

        try:
            response = requests.post(
                f"{self._base()}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(config["client_id"], config["secret"]),
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GatewayError("PayPal could not be reached.") from exc

        token = safe_json(response).get("access_token")

        if not response.ok or not token:
            raise GatewayError("PayPal authentication failed.")

        return token

    def create_payment(self, order) -> str:
        response = requests.post(
            f"{self._base()}/v2/checkout/orders",
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": order.number,
                        "invoice_id": order.number,
                        "amount": {
                            "currency_code": self.config()["currency"],
                            "value": f"{order.total / 100:.2f}",
                        },
                    }
                ],
                "application_context": {
                    "return_url": absolute_url("payment_return", order.number) + "?gateway=paypal",
                    "cancel_url": absolute_url("payment_cancel", order.number),
                    "user_action": "PAY_NOW",
                },
            },
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=20,
        )
        body = safe_json(response)

        links = {link.get("rel"): link.get("href") for link in body.get("links", []) if isinstance(link, dict)}
        approve = links.get("approve") or links.get("payer-action")

        if not response.ok or not approve:
            raise GatewayError("PayPal could not create the payment.")

        order.payment_reference = body.get("id", "")
        order.save(update_fields=["payment_reference", "updated_at"])

        return approve

    def confirm(self, order, request) -> bool:
        # PayPal returns ?token=<paypal order id>. It must match the order we created.
        paypal_order_id = request.GET.get("token")

        if not paypal_order_id or paypal_order_id != order.payment_reference:
            return order.is_paid

        response = requests.post(
            f"{self._base()}/v2/checkout/orders/{paypal_order_id}/capture",
            data="{}",
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            timeout=20,
        )
        body = safe_json(response)

        if body.get("status") == "COMPLETED":
            try:
                capture_id = body["purchase_units"][0]["payments"]["captures"][0]["id"]
            except (KeyError, IndexError, TypeError):
                capture_id = paypal_order_id
            order.mark_paid(capture_id)

        order.refresh_from_db()

        return order.is_paid

    def webhook(self, request) -> None:
        # The customer return URL captures the payment. If you rely on PayPal webhooks, verify
        # their signature with PayPal's /v1/notifications/verify-webhook-signature endpoint
        # before trusting any event here.
        return None
