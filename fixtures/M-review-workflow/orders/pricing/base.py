from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Line:
    sku: str
    quantity: int
    region: str
    coupon: str | None = None


class PriceStep(Protocol):
    def apply(self, line: Line, amount: float) -> float: ...
