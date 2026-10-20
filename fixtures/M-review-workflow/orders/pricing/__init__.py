from orders.pricing.base import Line
from orders.pricing.pipeline import run


def price(sku: str, quantity: int, region: str, coupon: str | None = None) -> float:
    return run(Line(sku, quantity, region, coupon))
