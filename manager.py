from django.conf import settings

from .mercadopago_gateway import MercadoPagoGateway
from .paypal_gateway import PayPalGateway
from .stripe_gateway import StripeGateway


class PaymentManager:
    """
    Knows every gateway and which ones are switched on.
    Offline methods (cash on delivery, bank transfer) are always available.
    """

    def __init__(self):
        self._gateways = {gateway.key: gateway for gateway in (StripeGateway(), PayPalGateway(), MercadoPagoGateway())}

    def gateway(self, key: str):
        gateway = self._gateways.get(key)

        return gateway if gateway is not None and gateway.enabled() else None

    def methods(self) -> dict[str, str]:
        """key -> label for every method the customer can pick."""
        online = {key: gateway.label for key, gateway in self._gateways.items() if gateway.enabled()}

        return {**online, **settings.SHOP["payment_methods"]}

    def is_online(self, key: str) -> bool:
        return self.gateway(key) is not None

    def label_for(self, key: str) -> str:
        """The label of any method, even one whose gateway was switched off later."""
        if key in self._gateways:
            return self._gateways[key].label

        return settings.SHOP["payment_methods"].get(key, key)
