import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase, override_settings

from shop.models import Category, Coupon, Product

from .base import FAST_HASHERS, TEST_SHOP, make_product


def install(*args, **kwargs):
    out = StringIO()
    call_command("install_shop", *args, stdout=out, **kwargs)

    return out.getvalue()


@override_settings(SHOP=TEST_SHOP, PASSWORD_HASHERS=FAST_HASHERS)
class InstallCommandTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        (self.base / ".env.example").write_text("APP_NAME=Demo\nSECRET_KEY=\nDEBUG=True\n", encoding="utf-8")

    def run_install(self, *args, **kwargs):
        with self.settings(BASE_DIR=self.base):
            return install(*args, **kwargs)

    def test_it_creates_the_env_file_with_a_secret_key(self):
        self.run_install()

        text = (self.base / ".env").read_text(encoding="utf-8")
        self.assertIn("APP_NAME=Demo", text)
        key = [line for line in text.splitlines() if line.startswith("SECRET_KEY=")][0].split("=", 1)[1]
        self.assertGreaterEqual(len(key), 40)

    def test_an_existing_env_file_and_key_are_kept(self):
        (self.base / ".env").write_text("SECRET_KEY=keep-me\n", encoding="utf-8")

        self.run_install()

        self.assertEqual((self.base / ".env").read_text(encoding="utf-8"), "SECRET_KEY=keep-me\n")

    def test_it_fails_clearly_without_env_files(self):
        (self.base / ".env.example").unlink()

        with self.assertRaisesMessage(CommandError, ".env.example"):
            self.run_install()

    def test_it_seeds_the_demo_shop_and_creates_an_admin(self):
        output = self.run_install()

        self.assertEqual(Category.objects.count(), 4)
        self.assertEqual(Product.objects.count(), 16)
        self.assertTrue(Coupon.objects.filter(code="WELCOME10").exists())
        self.assertTrue(get_user_model().objects.filter(email="customer@example.com").exists())
        self.assertIn("admin@example.com", output)

    def test_running_it_twice_changes_nothing(self):
        self.run_install()
        output = self.run_install()

        self.assertEqual(Product.objects.count(), 16)
        self.assertEqual(get_user_model().objects.filter(email="admin@example.com").count(), 1)
        self.assertIn("demo data was skipped", output)

    def test_no_seed_skips_the_demo_data_but_still_makes_an_admin(self):
        self.run_install(no_seed=True)

        self.assertEqual(Product.objects.count(), 0)
        self.assertTrue(get_user_model().objects.filter(is_superuser=True).exists())

    def test_a_chosen_admin_account_is_created_with_that_password(self):
        output = self.run_install(admin_email="Owner@Shop.com", admin_password="my-own-pass-1", no_seed=True)

        user = get_user_model().objects.get(email="owner@shop.com")
        self.assertTrue(user.is_superuser and user.is_staff)
        self.assertTrue(user.check_password("my-own-pass-1"))
        self.assertNotIn("my-own-pass-1", output)

    def test_an_existing_shop_is_not_seeded(self):
        make_product()

        self.run_install()

        self.assertEqual(Product.objects.count(), 1)


@override_settings(SHOP=TEST_SHOP, PASSWORD_HASHERS=FAST_HASHERS)
class InstallFreshTests(TransactionTestCase):
    def test_fresh_wipes_the_data_and_starts_over(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / ".env.example").write_text("SECRET_KEY=\n", encoding="utf-8")
            make_product(name="Old Stuff")

            with self.settings(BASE_DIR=base):
                install("--fresh")

            self.assertFalse(Product.objects.filter(name="Old Stuff").exists())
            self.assertEqual(Product.objects.count(), 16)
