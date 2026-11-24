from django.urls import reverse

from shop.cart import Cart

from .base import ShopTestCase, make_coupon, make_product, yesterday


class CartTests(ShopTestCase):
    def cart_items(self):
        return Cart(self.client.session).raw()

    def test_a_product_can_be_added_and_shown_in_the_cart(self):
        product = make_product(name="Desk Lamp", price=2500)

        response = self.client.post(reverse("cart_add", args=[product.slug]), {"quantity": 2}, follow=True)

        self.assertContains(response, "was added to your cart")
        response = self.client.get(reverse("cart"))
        self.assertContains(response, "Desk Lamp")
        self.assertContains(response, "$50.00")

    def test_the_cart_size_shows_in_the_header(self):
        product = make_product()
        self.client.post(reverse("cart_add", args=[product.slug]), {"quantity": 3})

        self.assertEqual(self.client.get(reverse("home")).context["cart_count"], 3)

    def test_quantity_is_capped_at_the_stock(self):
        product = make_product(stock=2)

        self.client.post(reverse("cart_add", args=[product.slug]), {"quantity": 5})

        self.assertEqual(self.cart_items(), {product.pk: 2})

    def test_an_out_of_stock_product_cannot_be_added(self):
        product = make_product(stock=0)

        response = self.client.post(reverse("cart_add", args=[product.slug]), follow=True)

        self.assertContains(response, "out of stock")
        self.assertEqual(self.cart_items(), {})

    def test_quantity_can_be_updated_and_removed(self):
        product = make_product(stock=10)
        self.client.post(reverse("cart_add", args=[product.slug]))

        self.client.post(reverse("cart_update", args=[product.slug]), {"quantity": 4})
        self.assertEqual(self.cart_items(), {product.pk: 4})

        self.client.post(reverse("cart_update", args=[product.slug]), {"quantity": 0})
        self.assertEqual(self.cart_items(), {})

        self.client.post(reverse("cart_add", args=[product.slug]))
        self.client.post(reverse("cart_remove", args=[product.slug]))
        self.assertEqual(self.cart_items(), {})

    def test_a_percent_coupon_lowers_the_total(self):
        product = make_product(price=10000)
        make_coupon(code="TEN", value=10)
        self.client.post(reverse("cart_add", args=[product.slug]))

        response = self.client.post(reverse("coupon_apply"), {"code": "ten"}, follow=True)
        self.assertContains(response, "Coupon TEN applied")

        # 100.00 - 10.00 discount + 8.00 shipping (below the free shipping threshold)
        response = self.client.get(reverse("cart"))
        self.assertContains(response, "TEN")
        self.assertContains(response, "$98.00")

    def test_a_coupon_can_be_removed(self):
        product = make_product(price=10000)
        make_coupon(code="TEN")
        self.client.post(reverse("cart_add", args=[product.slug]))
        self.client.post(reverse("coupon_apply"), {"code": "TEN"})

        self.client.post(reverse("coupon_remove"))

        self.assertContains(self.client.get(reverse("cart")), "$108.00")

    def test_unknown_expired_and_minimum_coupons_are_refused(self):
        product = make_product(price=1000)
        self.client.post(reverse("cart_add", args=[product.slug]))

        response = self.client.post(reverse("coupon_apply"), {"code": "NOPE"}, follow=True)
        self.assertContains(response, "does not exist")

        make_coupon(code="OLD", expires_at=yesterday())
        response = self.client.post(reverse("coupon_apply"), {"code": "OLD"}, follow=True)
        self.assertContains(response, "has expired")

        make_coupon(code="BIG", min_subtotal=50000)
        response = self.client.post(reverse("coupon_apply"), {"code": "BIG"}, follow=True)
        self.assertContains(response, "minimum amount")

    def test_a_coupon_at_its_usage_limit_is_refused(self):
        product = make_product()
        make_coupon(code="ONCE", max_uses=1, used_count=1)
        self.client.post(reverse("cart_add", args=[product.slug]))

        response = self.client.post(reverse("coupon_apply"), {"code": "ONCE"}, follow=True)

        self.assertContains(response, "usage limit")

    def test_a_disabled_product_is_dropped_from_the_cart(self):
        product = make_product(name="Vanishing Act")
        self.client.post(reverse("cart_add", args=[product.slug]))

        product.is_active = False
        product.save()

        self.assertNotContains(self.client.get(reverse("cart")), "Vanishing Act")

    def test_cart_actions_need_a_post(self):
        product = make_product()

        self.assertEqual(self.client.get(reverse("cart_add", args=[product.slug])).status_code, 405)
