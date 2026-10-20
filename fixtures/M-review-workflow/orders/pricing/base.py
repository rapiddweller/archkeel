from typing import Protocol


class TaxRule(Protocol):
    region: str

    def gross(self, net: float) -> float: ...
