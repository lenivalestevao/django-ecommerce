import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.utils import get_random_secret_key
from django.utils.crypto import get_random_string

from shop.demo import seed_demo
from shop.models import Category, Product


class Command(BaseCommand):
    help = "Set up the shop: .env file, secret key, database, tables, demo data and an admin account."

    def add_arguments(self, parser):
        parser.add_argument("--fresh", action="store_true", help="Delete all data and start over.")
        parser.add_argument("--no-seed", action="store_true", help="Do not add the demo categories, products and coupons.")
        parser.add_argument("--admin-email", help="Create (or update) an admin account with this email.")
        parser.add_argument("--admin-password", help="Password for that admin account.")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(f"Installing {settings.SHOP['name']}..."))

        self.ensure_env_file()
        self.ensure_database_folder()

        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write("  Database tables are ready.")

        if options["fresh"]:
            call_command("flush", interactive=False, verbosity=0)
            self.stdout.write("  Existing data was deleted.")

        self.seed(options)
        credentials = self.ensure_admin(options)
        self.summary(options, credentials)

    # --- Steps ---------------------------------------------------------------

    def ensure_env_file(self):
        """Creates .env from .env.example and fills in a SECRET_KEY when it is empty."""
        base = Path(settings.BASE_DIR)
        env_file = base / ".env"

        if not env_file.is_file():
            example = base / ".env.example"

            if not example.is_file():
                raise CommandError("There is no .env file and no .env.example to copy it from.")

            env_file.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            self.stdout.write("  Created the .env file.")

        text = env_file.read_text(encoding="utf-8")

        if re.search(r"^SECRET_KEY=\s*$", text, flags=re.MULTILINE):
            text = re.sub(
                r"^SECRET_KEY=\s*$",
                lambda _: f"SECRET_KEY={get_random_secret_key()}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            env_file.write_text(text, encoding="utf-8")
            self.stdout.write("  Generated a SECRET_KEY in .env.")

    def ensure_database_folder(self):
        """SQLite creates the database file by itself, but not the folder around it."""
        database = settings.DATABASES["default"]

        name = str(database["NAME"])

        if database["ENGINE"].endswith("sqlite3") and name != ":memory:" and not name.startswith("file:"):
            Path(name).parent.mkdir(parents=True, exist_ok=True)

    def seed(self, options):
        if options["no_seed"]:
            return

        User = get_user_model()

        # Only seed an empty shop, so running the installer twice never duplicates or fails.
        if User.objects.exists() or Product.objects.exists() or Category.objects.exists():
            self.stdout.write(self.style.WARNING("  The shop already has data, so the demo data was skipped."))
            return

        seed_demo()
        self.stdout.write("  Added demo categories, products and coupons.")

    def ensure_admin(self, options):
        """Returns (email, password or None). The password is only set when we generated it."""
        User = get_user_model()
        email = options["admin_email"]

        if email:
            email = email.strip().lower()
            password = options["admin_password"] or get_random_string(14)
            generated = not options["admin_password"]

            user = User.objects.filter(email__iexact=email).first() or User(username=email, email=email)
            user.first_name = user.first_name or "Store Admin"
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

            return email, password if generated else None

        if User.objects.filter(is_superuser=True).exists():
            return None

        password = get_random_string(14)
        User.objects.create_superuser(
            username="admin@example.com", email="admin@example.com", password=password, first_name="Store Admin"
        )

        return "admin@example.com", password

    def summary(self, options, credentials):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("The shop is ready."))
        self.stdout.write("  Start it with:  python manage.py runserver")
        self.stdout.write(f"  Store:          {settings.SITE_URL}/")
        self.stdout.write(f"  Admin panel:    {settings.SITE_URL}/admin/")

        User = get_user_model()

        if credentials:
            email, password = credentials
            self.stdout.write("")
            self.stdout.write(f"  Admin login:    {email}")
            if password:
                self.stdout.write(f"  Password:       {password}   (shown once, write it down)")
        elif not options["no_seed"] and User.objects.filter(email="admin@example.com").exists():
            self.stdout.write("")
            self.stdout.write("  Demo admin:     admin@example.com / password")
            self.stdout.write(self.style.WARNING("  Change the demo passwords before going live."))
