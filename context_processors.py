from django.conf import settings

from .cart import Cart
from .models import Category


def shop(request):
    """Makes the store settings, the cart size and the category menu available in every template."""
    session = getattr(request, "session", None)

    return {
        "SHOP": settings.SHOP,
        "cart_count": Cart(session).count() if session is not None else 0,
        "menu_categories": Category.objects.active(),
    }
