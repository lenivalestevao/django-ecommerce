from django.urls import reverse

from shop.models import Coupon, Order, OrderItem, Product

from .base import ShopTestCase, make_category, make_order, make_product, make_staff, make_user


class DashboardTests(ShopTestCase):
    def test_guests_are_sent_to_login_and_customers_are_forbidden(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_the_dashboard_shows_the_numbers(self):
        make_order(status="processing", payment_status="paid", total=12345)
        make_order(status="cancelled", payment_status="paid", total=99999)  # cancelled orders do not count
        make_order(status="pending")
        make_product(name="Nearly Gone", stock=2)
        self.client.force_login(make_staff())

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "$123.45")
        self.assertNotContains(response, "$999.99")
        self.assertContains(response, "Nearly Gone")
        self.assertEqual(response.context["orders_count"], 2)
        self.assertEqual(response.context["pending_count"], 1)

    def test_the_admin_pages_load(self):
        make_product()
        make_order()
        self.client.force_login(make_staff())

        names = [
            "admin:shop_product_changelist",
            "admin:shop_product_add",
            "admin:shop_category_changelist",
            "admin:shop_category_add",
            "admin:shop_coupon_changelist",
            "admin:shop_coupon_add",
            "admin:shop_order_changelist",
            "admin:auth_user_changelist",
            "dashboard",
        ]
        for name in names:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        order = Order.objects.get()
        self.assertEqual(self.client.get(reverse("admin:shop_order_change", args=[order.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:shop_order_add")).status_code, 403)

    def test_customers_cannot_open_the_admin(self):
        self.client.force_login(make_user())

        self.assertEqual(self.client.get(reverse("admin:shop_product_changelist")).status_code, 302)


class AdminCatalogTests(ShopTestCase):
    def setUp(self):
        self.client.force_login(make_staff())

    def product_form(self, **extra):
        data = {
            "name": "Brand New Mug",
            "slug": "",
            "sku": "MUG-1",
            "short_description": "",
            "description": "",
            "price": "19.90",
            "sale_price": "",
            "stock": 7,
            "is_active": "on",
        }
        data.update(extra)

        return data

    def test_a_product_can_be_created_updated_and_deleted(self):
        category = make_category()

        response = self.client.post(
            reverse("admin:shop_product_add"),
            self.product_form(category=category.pk, sale_price="15.50"),
        )
        self.assertRedirects(response, reverse("admin:shop_product_changelist"))

        product = Product.objects.get(sku="MUG-1")
        self.assertEqual(product.slug, "brand-new-mug")
        self.assertEqual(product.price, 1990)
        self.assertEqual(product.sale_price, 1550)
        self.assertFalse(product.is_featured)

        # The edit form shows normal units, not cents.
        response = self.client.get(reverse("admin:shop_product_change", args=[product.pk]))
        self.assertContains(response, 'value="19.90"')

        response = self.client.post(
            reverse("admin:shop_product_change", args=[product.pk]),
            self.product_form(slug="brand-new-mug", price="25", stock=3, is_featured="on"),
        )
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.price, 2500)
        self.assertIsNone(product.sale_price)
        self.assertTrue(product.is_featured)

        self.client.post(reverse("admin:shop_product_delete", args=[product.pk]), {"post": "yes"})
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_the_sale_price_must_be_lower_than_the_price(self):
        response = self.client.post(
            reverse("admin:shop_product_add"),
            self.product_form(sku="BAD-1", price="10", sale_price="12"),
        )

        self.assertContains(response, "must be lower than the price")
        self.assertFalse(Product.objects.filter(sku="BAD-1").exists())

    def test_a_category_is_created_with_a_slug(self):
        self.client.post(reverse("admin:shop_category_add"), {"name": "Garden Tools", "slug": "", "sort_order": 0, "is_active": "on"})

        self.assertTrue(make_category.__name__)  # helper imported for other tests
        self.assertEqual(self.client.get(reverse("category", args=["garden-tools"])).status_code, 200)

    def coupon_form(self, **extra):
        data = {"code": "spring", "type": "fixed", "value": "5.00", "min_subtotal": "20", "used_count": 0, "is_active": "on"}
        data.update(extra)

        return data

    def test_coupons_are_stored_in_cents_with_an_upper_case_code(self):
        self.client.post(reverse("admin:shop_coupon_add"), self.coupon_form())

        coupon = Coupon.objects.get()
        self.assertEqual((coupon.code, coupon.type, coupon.value, coupon.min_subtotal), ("SPRING", "fixed", 500, 2000))

        response = self.client.get(reverse("admin:shop_coupon_change", args=[coupon.pk]))
        self.assertContains(response, 'value="5.00"')

    def test_a_percent_coupon_must_be_a_whole_number_up_to_100(self):
        response = self.client.post(reverse("admin:shop_coupon_add"), self.coupon_form(code="HALF", type="percent", value="150"))
        self.assertContains(response, "whole number from 0 to 100")

        response = self.client.post(reverse("admin:shop_coupon_add"), self.coupon_form(code="ODD", type="percent", value="12.5"))
        self.assertContains(response, "whole number from 0 to 100")

        self.client.post(reverse("admin:shop_coupon_add"), self.coupon_form(code="TEN", type="percent", value="10", min_subtotal=""))
        coupon = Coupon.objects.get(code="TEN")
        self.assertEqual((coupon.value, coupon.min_subtotal), (10, 0))


class AdminOrderTests(ShopTestCase):
    def setUp(self):
        self.client.force_login(make_staff())

    def act(self, action, *orders):
        return self.client.post(
            reverse("admin:shop_order_changelist"),
            {"action": action, "_selected_action": [str(order.pk) for order in orders]},
            follow=True,
        )

    def test_cancelling_an_order_puts_the_stock_back_once(self):
        product = make_product(stock=3)
        order = make_order(with_item=False)
        OrderItem.objects.create(order=order, product=product, name="x", sku="x", price=100, quantity=2, total=200)

        self.act("mark_cancelled", order)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

        self.act("mark_cancelled", order)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

    def test_cancelling_gives_the_coupon_use_back(self):
        from .base import make_coupon

        coupon = make_coupon(used_count=1)
        order = make_order(coupon=coupon)

        self.act("mark_cancelled", order)

        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)

    def test_the_status_can_be_changed_and_an_order_marked_paid(self):
        order = make_order()

        self.assertContains(self.act("mark_shipped", order), "set to shipped")
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")

        self.act("mark_paid", order)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "shipped")  # only a pending order moves to processing

    def test_orders_can_be_exported_as_csv(self):
        order = make_order(customer_name="Export Person", total=12345)

        response = self.client.post(
            reverse("admin:shop_order_changelist"),
            {"action": "export_csv", "_selected_action": [str(order.pk)]},
        )

        self.assertEqual(response["Content-Type"], "text/csv")
        body = response.content.decode()
        self.assertIn(order.number, body)
        self.assertIn("Export Person", body)
        self.assertIn("123.45", body)
