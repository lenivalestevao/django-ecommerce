from django.test import override_settings

from shop.models import Coupon
from shop.money import format_money, to_cents, to_input
from shop.totals import Totals

from .base import TEST_SHOP, ShopTestCase


class MoneyAndTotalsTests(ShopTestCase):
    def test_money_converts_between_cents_and_text(self):
        self.assertEqual(to_cents("19.90"), 1990)
        self.assertEqual(to_cents("19,90"), 1990)
        self.assertEqual(to_cents(""), 0)
        self.assertEqual(to_cents(None), 0)
        self.assertEqual(to_cents(19.9), 1990)
        self.assertEqual(to_input(1990), "19.90")
        self.assertEqual(format_money(123450), "$1,234.50")

    def test_money_rounds_half_up(self):
        self.assertEqual(to_cents("0.125"), 13)

    def test_shipping_is_free_over_the_threshold(self):
        shop = {**TEST_SHOP, "shipping_fee": 800, "free_shipping_over": 10000, "tax_rate": 0}

        with override_settings(SHOP=shop):
            self.assertEqual(Totals.calculate(5000).shipping, 800)
            self.assertEqual(Totals.calculate(10000).shipping, 0)
            self.assertEqual(Totals.calculate(0).shipping, 0)

    def test_tax_is_applied_after_the_discount(self):
        shop = {**TEST_SHOP, "shipping_fee": 0, "free_shipping_over": 1, "tax_rate": 10}
        coupon = Coupon(type=Coupon.FIXED, value=1000)

        with override_settings(SHOP=shop):
            totals = Totals.calculate(10000, coupon)

        self.assertEqual(totals.discount, 1000)
        self.assertEqual(totals.tax, 900)
        self.assertEqual(totals.total, 9900)

    def test_the_discount_never_exceeds_the_subtotal(self):
        self.assertEqual(Coupon(type=Coupon.FIXED, value=99999).discount_for(2000), 2000)

    def test_a_percent_discount_rounds_half_up(self):
        self.assertEqual(Coupon(type=Coupon.PERCENT, value=15).discount_for(10), 2)  # 1.5 -> 2
