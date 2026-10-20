from orders.pricing.base import Line

_STANDARD = {"de": 0.19, "fr": 0.20, "se": 0.25}
_REDUCED = {"de": 0.07, "fr": 0.055, "se": 0.06}
_REDUCED_SKUS = frozenset({"book"})


class Vat:
    """Books carry the region's reduced rate; everything else the standard rate."""

    def apply(self, line: Line, amount: float) -> float:
        rates = _REDUCED if line.sku in _REDUCED_SKUS else _STANDARD
        return amount * (1 + rates[line.region])
