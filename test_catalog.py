from django.urls import reverse

from .base import ShopTestCase, make_category, make_product


class CatalogTests(ShopTestCase):
    def test_home_page_lists_featured_products(self):
        make_product(name="Blue Lamp", is_featured=True)

        self.assertContains(self.client.get(reverse("home")), "Blue Lamp")

    def test_hidden_products_are_not_listed_or_reachable(self):
        product = make_product(name="Secret Item", is_active=False)

        self.assertNotContains(self.client.get(reverse("shop")), "Secret Item")
        self.assertEqual(self.client.get(reverse("product", args=[product.slug])).status_code, 404)

    def test_catalog_filters_by_category_and_search(self):
        shoes = make_category(name="Shoes")
        hats = make_category(name="Hats")
        make_product(category=shoes, name="Trail Runner")
        make_product(category=hats, name="Straw Hat")

        response = self.client.get(reverse("category", args=[shoes.slug]))
        self.assertContains(response, "Trail Runner")
        self.assertNotContains(response, "Straw Hat")

        response = self.client.get(reverse("shop"), {"q": "Straw"})
        self.assertContains(response, "Straw Hat")
        self.assertNotContains(response, "Trail Runner")

    def test_search_also_matches_the_sku(self):
        make_product(name="Plain Thing", sku="ZX-4242")

        self.assertContains(self.client.get(reverse("shop"), {"q": "zx-42"}), "Plain Thing")

    def test_catalog_sorts_by_price(self):
        make_product(name="Cheap One", price=1000)
        make_product(name="Pricey One", price=9000)

        html = self.client.get(reverse("shop"), {"sort": "price_desc"}).content.decode()

        self.assertLess(html.index("Pricey One"), html.index("Cheap One"))

    def test_product_page_shows_the_sale_price(self):
        product = make_product(price=10000, sale_price=7500)

        response = self.client.get(reverse("product", args=[product.slug]))

        self.assertContains(response, "$75.00")
        self.assertContains(response, "$100.00")

    def test_an_invalid_sort_falls_back_to_the_default(self):
        make_product(name="Still Listed")

        self.assertContains(self.client.get(reverse("shop"), {"sort": "nonsense"}), "Still Listed")

    def test_the_catalog_is_paginated(self):
        for _ in range(13):
            make_product()

        self.assertEqual(len(self.client.get(reverse("shop")).context["products"]), 12)
        self.assertEqual(len(self.client.get(reverse("shop"), {"page": 2}).context["products"]), 1)

    def test_slugs_stay_unique(self):
        first = make_product(name="Same Name")
        second = make_product(name="Same Name")

        self.assertEqual(first.slug, "same-name")
        self.assertEqual(second.slug, "same-name-2")
