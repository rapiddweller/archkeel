from orders.pricing.base import Line

_CLEARANCE = frozenset({"lamp"})


class Clearance:
    """Clearance SKUs are sold at half price before any other discount."""

    def apply(self, line: Line, amount: float) -> float:
        return amount / 2 if line.sku in _CLEARANCE else amount
