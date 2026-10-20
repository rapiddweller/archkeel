from orders.pricing.base import Line

_EUR_TO_SEK = 11.5


class Currency:
    """Swedish orders are charged in SEK; all others in EUR."""

    def apply(self, line: Line, amount: float) -> float:
        return amount * _EUR_TO_SEK if line.region == "se" else amount
