from django import template

from ..money import format_money

register = template.Library()


@register.filter
def money(cents):
    """{{ product.price|money }} -> $19.90"""
    return format_money(cents)
