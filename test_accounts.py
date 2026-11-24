from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from .base import ShopTestCase, make_staff, make_user

STRONG = "Str0ng-Pass-Phrase-91"


class AccountTests(ShopTestCase):
    def test_a_customer_can_register_and_is_logged_in(self):
        response = self.client.post(
            reverse("register"),
            {"name": "Ann Lee", "email": "Ann@Example.com", "password1": STRONG, "password2": STRONG},
        )

        self.assertRedirects(response, reverse("account"))
        user = get_user_model().objects.get(email="ann@example.com")
        self.assertEqual(user.first_name, "Ann Lee")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

    def test_registering_cannot_create_an_admin(self):
        self.client.post(
            reverse("register"),
            {"name": "Eve", "email": "eve@example.com", "password1": STRONG, "password2": STRONG, "is_staff": "on", "is_superuser": "on"},
        )

        user = get_user_model().objects.get(email="eve@example.com")
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_registration_is_validated(self):
        make_user("taken@example.com")

        response = self.client.post(
            reverse("register"),
            {"name": "X", "email": "TAKEN@example.com", "password1": STRONG, "password2": "different"},
        )
        errors = response.context["form"].errors
        self.assertIn("email", errors)
        self.assertIn("password2", errors)

        response = self.client.post(
            reverse("register"),
            {"name": "X", "email": "weak@example.com", "password1": "12345678", "password2": "12345678"},
        )
        self.assertIn("password1", response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(email="weak@example.com").exists())

    def test_login_works_with_the_email_in_any_case(self):
        make_user("Mixed@Example.com", "secret-pass-1")

        response = self.client.post(reverse("login"), {"username": "mixed@example.COM", "password": "secret-pass-1"})

        self.assertRedirects(response, reverse("account"))

    def test_a_wrong_password_is_refused(self):
        make_user("user@example.com", "right-pass-1")

        response = self.client.post(reverse("login"), {"username": "user@example.com", "password": "nope"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_needs_a_post(self):
        self.client.force_login(make_user())

        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_account_page_needs_a_login(self):
        response = self.client.get(reverse("account"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('account')}")

    def test_details_and_password_can_be_updated(self):
        user = make_user("old@example.com", "old-pass-123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("account"),
            {"name": "New Name", "email": "new@example.com", "password1": STRONG, "password2": STRONG},
        )

        self.assertRedirects(response, reverse("account"))
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.email, user.username), ("New Name", "new@example.com", "new@example.com"))
        self.assertTrue(user.check_password(STRONG))
        # Still logged in after the password change.
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

    def test_the_email_cannot_be_taken_from_another_account(self):
        make_user("other@example.com")
        self.client.force_login(make_user("me@example.com"))

        response = self.client.post(reverse("account"), {"name": "Me", "email": "other@example.com"})

        self.assertIn("email", response.context["form"].errors)

    def test_a_password_reset_email_is_sent(self):
        make_user("forgot@example.com")

        response = self.client.post(reverse("password_reset"), {"email": "forgot@example.com"})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["forgot@example.com"])
        self.assertIn("/password-reset/", mail.outbox[0].body)

    def test_staff_can_sign_in_and_open_the_dashboard(self):
        make_staff("boss@example.com", "boss-pass-123")
        self.client.post(reverse("login"), {"username": "boss@example.com", "password": "boss-pass-123"})

        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
