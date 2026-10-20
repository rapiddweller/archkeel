from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    sku: str
    quantity: int
    total_cents: int
