from orders.pricing.base import Line


class Shipping:
    """Orders below 25 pay a flat 4.90; Sweden adds a remote-delivery fee."""

    def apply(self, line: Line, amount: float) -> float:
        fee = 4.90 if amount < 25 else 0.0
        return amount + fee + (2.0 if line.region == "se" else 0.0)
