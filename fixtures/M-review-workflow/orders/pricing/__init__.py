_UNIT_PRICES = {"book": 12.5, "pen": 1.2}


def price(sku: str, quantity: int, region: str) -> float:
    from orders.pricing.registry import RULES

    return RULES[region].gross(_UNIT_PRICES[sku] * quantity)
