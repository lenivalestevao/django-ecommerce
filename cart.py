from dataclasses import dataclass

from .models import Coupon, Product
from .totals import Totals

ITEMS_KEY = "cart_items"
COUPON_KEY = "cart_coupon"


@dataclass(frozen=True)
class Line:
    product: Product
    quantity: int
    total: int


class Cart:
    """
    Session based shopping cart. It stores only product ids and quantities,
    and always reads current prices and stock from the database.
    """

    def __init__(self, session):
        self.session = session

    def raw(self) -> dict[int, int]:
        """product id -> quantity"""
        return {int(pk): int(qty) for pk, qty in self.session.get(ITEMS_KEY, {}).items()}

    def _save(self, items: dict[int, int]) -> None:
        self.session[ITEMS_KEY] = {str(pk): qty for pk, qty in items.items()}
        self.session.modified = True

    def add(self, product: Product, quantity: int = 1) -> None:
        items = self.raw()
        items[product.pk] = min(items.get(product.pk, 0) + quantity, max(product.stock, 1))
        self._save(items)

    def set(self, product: Product, quantity: int) -> None:
        if quantity < 1:
            self.remove(product)
            return

        items = self.raw()
        items[product.pk] = min(quantity, max(product.stock, 1))
        self._save(items)

    def remove(self, product: Product) -> None:
        items = self.raw()
        items.pop(product.pk, None)
        self._save(items)

    def clear(self) -> None:
        self.session.pop(ITEMS_KEY, None)
        self.session.pop(COUPON_KEY, None)
        self.session.modified = True

    def count(self) -> int:
        return sum(self.raw().values())

    def is_empty(self) -> bool:
        return not self.raw()

    def lines(self) -> list[Line]:
        """Cart lines with their products. Products that were deleted or disabled are dropped."""
        items = self.raw()

        if not items:
            return []

        products = {p.pk: p for p in Product.objects.active().filter(pk__in=items.keys())}

        return [
            Line(products[pk], qty, products[pk].current_price * qty)
            for pk, qty in items.items()
            if pk in products
        ]

    def subtotal(self) -> int:
        return sum(line.total for line in self.lines())

    def apply_coupon(self, coupon: Coupon) -> None:
        self.session[COUPON_KEY] = coupon.code
        self.session.modified = True

    def remove_coupon(self) -> None:
        self.session.pop(COUPON_KEY, None)
        self.session.modified = True

    def coupon(self) -> Coupon | None:
        """The coupon in the cart, or None when none was applied or it is no longer valid."""
        code = self.session.get(COUPON_KEY)

        if not code:
            return None

        coupon = Coupon.objects.filter(code=code).first()

        if coupon is None or coupon.problem_for(self.subtotal()) is not None:
            self.remove_coupon()
            return None

        return coupon

    def totals(self) -> Totals:
        return Totals.calculate(self.subtotal(), self.coupon())
