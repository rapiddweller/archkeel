# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Order and Line value types with Money arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

__all__ = ["Order", "Line", "Money", "OrderPayload", "LinePayload"]


class LinePayload(TypedDict):
    """The serialised shape of one order line."""

    description: str
    quantity: int
    unit_price: int


class OrderPayload(TypedDict):
    """The serialised shape of one order."""

    order_id: str
    lines: list[LinePayload]


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in integer cents."""

    cents: int

    def __add__(self, other: Money) -> Money:
        return Money(self.cents + other.cents)

    def __mul__(self, quantity: int) -> Money:
        return Money(self.cents * quantity)

    def __str__(self) -> str:
        return f"{self.cents / 100:.2f}"


@dataclass(frozen=True, slots=True)
class Discount:
    """A percentage discount; not part of the component's public interface."""

    percent: int

    def apply(self, amount: Money) -> Money:
        return Money(amount.cents * (100 - self.percent) // 100)


@dataclass(frozen=True, slots=True)
class Line:
    description: str
    quantity: int
    unit_price: Money

    def total(self) -> Money:
        return self.unit_price * self.quantity

    def to_dict(self) -> LinePayload:
        return {
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price.cents,
        }

    @classmethod
    def from_dict(cls, payload: LinePayload) -> Line:
        return cls(
            description=payload["description"],
            quantity=payload["quantity"],
            unit_price=Money(payload["unit_price"]),
        )


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    lines: tuple[Line, ...]

    def total(self) -> Money:
        result = Money(0)
        for line in self.lines:
            result = result + line.total()
        return result

    def to_dict(self) -> OrderPayload:
        return {"order_id": self.order_id, "lines": [line.to_dict() for line in self.lines]}

    @classmethod
    def from_dict(cls, payload: OrderPayload) -> Order:
        lines = tuple(Line.from_dict(item) for item in payload["lines"])
        return cls(order_id=payload["order_id"], lines=lines)
