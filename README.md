# Django Shop

[![Tests](https://github.com/lenivalestevao/django-ecommerce/actions/workflows/tests.yml/badge.svg)](https://github.com/lenivalestevao/django-ecommerce/actions/workflows/tests.yml)

A free, complete e-commerce starter for **Django 6.1** (Python 3.12+). Download it, run a few commands and you have a working online store with a catalog, cart, checkout, customer accounts and an admin panel, in the spirit of OpenCart but on a modern Django codebase you can read and change. It is the Python port of my [Laravel e-commerce template](https://github.com/lenivalestevao/laravel-ecommerce).

## Features

**Storefront**
- Home page with featured products, categories and new arrivals
- Catalog with search, category filter, sorting and pagination
- Product page with sale price, stock and related products
- Session cart, quantity limits based on stock, coupon codes
- Checkout for guests or registered customers
- Order confirmation, order tracking by number and email, email notifications
- Customer registration, login, password reset, profile and order history

**Payments**
- Stripe (Checkout), PayPal (Orders v2) and Mercado Pago (Checkout Pro)
- Cash on delivery and bank transfer
- Each online gateway turns on by itself when its keys are in `.env`
- Webhooks with signature check (Stripe) and server-side payment lookup (Mercado Pago)

**Admin** (`/admin`, the Django admin, plus a staff dashboard at `/dashboard/`)
- Dashboard with revenue, orders, pending orders, customers and low stock
- Products (image upload, sale price, stock, featured, hide), categories, coupons
- Orders: filters, status actions, mark as paid, CSV export, stock restored on cancel
- Prices are typed in normal units (19.90), stored as integer cents

**Under the hood**
- Order lines keep the price paid; stock is locked inside a database transaction at checkout
- Models, migrations, forms, class-based auth views, ModelAdmin, `requests` for the gateways
- Plain CSS, no Node, no build step
- SQLite by default, PostgreSQL and MySQL through `.env`

## Install

Requirements: Python 3.12+.

```bash
git clone https://github.com/lenivalestevao/django-ecommerce.git
cd django-ecommerce
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py install_shop
python manage.py runserver
```

`python manage.py install_shop` does the rest. It is safe to run again, and it never deletes data unless you add `--fresh`:

- creates the `.env` file and a `SECRET_KEY`
- creates the database folder and file (SQLite)
- creates all the tables with the migrations
- adds demo categories, products and coupons (skipped if the shop already has data)
- makes sure there is an admin account

| Option | What it does |
| --- | --- |
| `--no-seed` | Skip the demo products and coupons, for a clean store |
| `--fresh` | Delete all data and start over (**deletes everything**) |
| `--admin-email=you@store.com --admin-password=...` | Create your own admin account |

Open http://localhost:8000. The demo data includes two coupons (`WELCOME10`, `SAVE5`) and these accounts:

| Account | Email | Password |
| --- | --- | --- |
| Admin | admin@example.com | password |
| Customer | customer@example.com | password |

**Change these before going live**, or run `python manage.py install_shop --no-seed --admin-email you@yourstore.com` on an empty database.

## Configure your store

Edit `.env` (all options are in `.env.example`) and the `SHOP` dict in `config/settings.py`:

| Setting | What it does |
| --- | --- |
| `SHOP_NAME`, `SHOP_CURRENCY` | Store name and the symbol shown next to prices |
| `SHOP_SHIPPING_FEE`, `SHOP_FREE_SHIPPING_OVER` | Flat shipping and free shipping threshold, in cents |
| `SHOP_TAX_RATE` | Tax in percent, added after discounts |
| `DB_ENGINE` | `sqlite`, `postgresql` or `mysql` (install the matching driver) |
| `EMAIL_HOST` | Set it to send real emails. Until then emails are printed in the terminal |
| `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY` | Set `DEBUG=False` and your domain in production |

## Payments

Put the keys in `.env`. A gateway shows up at checkout only when it is configured.

**Stripe**: set `STRIPE_SECRET`. Add a webhook to `https://your-domain/payment/webhook/stripe/` for the event `checkout.session.completed` and set `STRIPE_WEBHOOK_SECRET`.

**PayPal**: set `PAYPAL_CLIENT_ID` and `PAYPAL_SECRET`. Keep `PAYPAL_SANDBOX=true` until you have tested, then use `false` with live credentials.

**Mercado Pago**: set `MERCADOPAGO_ACCESS_TOKEN`. The notification URL `https://your-domain/payment/webhook/mercadopago/` is sent with every payment and must be reachable from the internet.

Each gateway is a small class in `shop/payments/` built on the `Gateway` base. To add another one, create a class and register it in `PaymentManager`.

## Tests

```bash
python manage.py test
```

The suite covers catalog, cart, coupons, checkout, stock, payments (with faked HTTP responses), admin, accounts and the `install_shop` command. GitHub runs it on every push (`.github/workflows/tests.yml`).

## Status and honesty notes

- Check the Actions tab: the badge above shows whether the test suite passes on a clean checkout. That proves the code works there, not on your server. If something fails on your machine, please open an issue with the error.
- The payment gateways are tested with fake HTTP responses only. **Run a real payment in each provider's sandbox before accepting money.** Provider APIs change.
- PayPal: the customer return URL captures the payment. If you add PayPal webhooks, verify their signature before trusting them.
- Bank transfer instructions are placeholder text in `shop/templates/shop/order.html`. Put your own bank details there.
- Review security, taxes, invoicing and legal requirements for your country (privacy policy, terms, consumer rights) before selling. For production use a real web server (gunicorn or uvicorn behind Nginx), serve `/media/` and run `collectstatic`.

## Project layout

```
config/               settings, urls, wsgi/asgi
shop/models.py        Category, Product, Coupon, Order, OrderItem
shop/views.py         storefront, account and dashboard views
shop/admin.py         Django admin setup (cents-aware forms, order actions)
shop/cart.py          session cart
shop/totals.py        discount, shipping and tax
shop/services.py      order creation, stock locking, restock
shop/payments/        Stripe, PayPal, Mercado Pago and PaymentManager
shop/management/      install_shop command
shop/templates/       HTML templates
shop/static/          CSS
shop/tests/           test suite
```

## License

MIT. Use it for personal or commercial projects. If it helps you, a ⭐ on the repository is much appreciated.
