from orders.pricing.base import Line


class BulkDiscount:
    """Ten or more units of one SKU cost five percent less."""

    def apply(self, line: Line, amount: float) -> float:
        return amount * 0.95 if line.quantity >= 10 else amount
