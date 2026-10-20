from orders.checkout import Receipt, place
from orders.checkout.rounding import round_cents
from orders.common.util import slugify
from orders.pricing import price


def place_order(sku: str, quantity: int, region: str) -> Receipt:
    """Entry point: price one order line, persist the receipt and return it."""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return place(slugify(sku), quantity, region)


def quote(sku: str, quantity: int, region: str) -> int:
    """Entry point: the total in cents an order would cost, without placing it."""
    return round_cents(price(slugify(sku), quantity, region))
