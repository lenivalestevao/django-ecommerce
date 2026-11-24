"""
Django settings for the shop.

Everything a store owner changes lives in the .env file (see .env.example) or in the SHOP
dictionary below. Prices are stored as integer cents.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Tiny .env reader so the project needs no extra package."""
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_env_file(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

DEBUG = env_bool("DEBUG", True)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set SECRET_KEY in your environment or .env file when DEBUG is off.")
    SECRET_KEY = "django-insecure-development-key-run-install_shop-to-get-your-own"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Public address of the site. Payment providers send customers back to it.
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context_processors.shop",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# SQLite works out of the box. Set DB_ENGINE to postgresql or mysql for a server database.

DB_ENGINE = env("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("DB_NAME") or str(BASE_DIR / "db.sqlite3"),
        }
    }
elif DB_ENGINE in {"postgresql", "postgres", "mysql", "mariadb"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql"
            if DB_ENGINE in {"postgresql", "postgres"}
            else "django.db.backends.mysql",
            "NAME": env("DB_NAME", "shop"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT"),
        }
    }
else:
    raise ImproperlyConfigured(f"Unknown DB_ENGINE '{DB_ENGINE}'. Use sqlite, postgresql or mysql.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Accounts ---------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Customers log in with their email address.
AUTHENTICATION_BACKENDS = [
    "shop.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "account"
LOGOUT_REDIRECT_URL = "home"

# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# --- Static and uploaded files ---------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Email ------------------------------------------------------------------
# "console" prints emails in the terminal. Use smtp in production.

EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if env("EMAIL_HOST")
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "shop@example.com")

# --- Store ------------------------------------------------------------------

SHOP = {
    "name": env("SHOP_NAME", "Django Shop"),
    "tagline": env("SHOP_TAGLINE", "Everything you need, delivered to your door"),
    # Symbol shown next to prices. Prices are stored as integer cents.
    "currency": env("SHOP_CURRENCY", "$"),
    # Flat shipping fee in cents. Orders above the free threshold ship free.
    "shipping_fee": env_int("SHOP_SHIPPING_FEE", 800),
    "free_shipping_over": env_int("SHOP_FREE_SHIPPING_OVER", 10000),
    # Tax rate in percent, applied to the subtotal after the discount.
    "tax_rate": env_float("SHOP_TAX_RATE", 0),
    "per_page": 12,
    "contact_email": env("SHOP_EMAIL", "shop@example.com"),
    "order_prefix": env("SHOP_ORDER_PREFIX", "DS"),
    # Methods that need no online gateway. Stripe, PayPal and Mercado Pago appear by themselves
    # when their keys are set below.
    "payment_methods": {
        "cod": "Cash on delivery",
        "bank": "Bank transfer",
    },
}

# A gateway is switched on automatically when its keys are present.
PAYMENTS = {
    "stripe": {
        "secret": env("STRIPE_SECRET"),
        "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
        "currency": env("STRIPE_CURRENCY", "usd"),
    },
    "paypal": {
        "client_id": env("PAYPAL_CLIENT_ID"),
        "secret": env("PAYPAL_SECRET"),
        "sandbox": env_bool("PAYPAL_SANDBOX", True),
        "currency": env("PAYPAL_CURRENCY", "USD"),
    },
    "mercadopago": {
        "access_token": env("MERCADOPAGO_ACCESS_TOKEN"),
        "currency": env("MERCADOPAGO_CURRENCY", "BRL"),
    },
}
