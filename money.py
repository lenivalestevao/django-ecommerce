"""
All prices are stored as integer cents. These helpers convert them for display and for forms.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings


def round_half_up(value) -> int:
    """Round like a shop does (2.5 becomes 3), not like Python's round()."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(cents: int | None) -> str:
    """123450 -> "$1,234.50"."""
    amount = Decimal(cents or 0) / 100
    return f"{settings.SHOP['currency']}{amount:,.2f}"


def to_cents(value) -> int:
    """"19.90", "19,90", 19.9 or Decimal("19.90") -> 1990."""
    if value is None:
        return 0

    text = str(value).strip().replace(",", ".")
    if text == "":
        return 0

    return round_half_up(Decimal(text) * 100)


def to_input(cents: int | None) -> str:
    """1990 -> "19.90" (value for an input field)."""
    return f"{Decimal(cents or 0) / 100:.2f}"
