from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from .money import round_half_up


@dataclass(frozen=True)
class Totals:
    """Order amounts, all in cents."""

    subtotal: int
    discount: int
    shipping: int
    tax: int
    total: int

    @classmethod
    def calculate(cls, subtotal: int, coupon=None) -> "Totals":
        shop = settings.SHOP

        discount = coupon.discount_for(subtotal) if coupon is not None else 0
        after_discount = subtotal - discount

        if subtotal == 0 or after_discount >= shop["free_shipping_over"]:
            shipping = 0
        else:
            shipping = int(shop["shipping_fee"])

        tax = round_half_up(Decimal(after_discount) * Decimal(str(shop["tax_rate"])) / 100)

        return cls(subtotal, discount, shipping, tax, after_discount + shipping + tax)
