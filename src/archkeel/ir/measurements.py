# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture measurement payloads independent of check policy."""

from dataclasses import dataclass
from typing import Literal

SCALARS = (
    "violations",
    "cycle_edges",
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "coverage_failures",
)


class RatchetError(ValueError):
    """The measurements are missing, inconsistent, or not safely comparable."""


@dataclass(frozen=True, slots=True)
class RatchetScalars:
    violations: int
    cycle_edges: int
    private_crossings: int
    typing_positions: int
    calls_unresolved: int
    coverage_failures: int

    def items(self) -> tuple[tuple[str, int], ...]:
        return (
            ("violations", self.violations),
            ("cycle_edges", self.cycle_edges),
            ("private_crossings", self.private_crossings),
            ("typing_positions", self.typing_positions),
            ("calls_unresolved", self.calls_unresolved),
            ("coverage_failures", self.coverage_failures),
        )

    def __post_init__(self) -> None:
        for name, value in self.items():
            count(value, name)


@dataclass(frozen=True, slots=True)
class Measurements:
    scalars: RatchetScalars
    calls_total: int
    resolution: Literal["measured", "n/a"]

    def __post_init__(self) -> None:
        count(self.calls_total, "calls_total")
        expected = "measured" if self.calls_total else "n/a"
        if self.resolution != expected:
            raise RatchetError(f"resolution must be {expected}")
        if self.scalars.calls_unresolved > self.calls_total:
            raise RatchetError("calls_unresolved must not exceed calls_total")
        if self.scalars.coverage_failures:
            raise RatchetError("scan must be complete without coverage failures")


def compare_measurements(
    accepted: Measurements, candidate: Measurements
) -> tuple[tuple[str, str, str, str], ...]:
    comparisons: tuple[tuple[str, str, str, str], ...] = tuple(
        (name, str(before), str(after), "FAIL" if after > before else "PASS")
        for (name, before), (_, after) in zip(
            accepted.scalars.items(), candidate.scalars.items(), strict=True
        )
    )
    comparable = accepted.calls_total > 0 and candidate.calls_total > 0
    ratio_failed = (
        candidate.scalars.calls_unresolved * accepted.calls_total
        > accepted.scalars.calls_unresolved * candidate.calls_total
    )
    return comparisons + (
        (
            "unresolved_ratio",
            f"{accepted.scalars.calls_unresolved}/{accepted.calls_total}",
            f"{candidate.scalars.calls_unresolved}/{candidate.calls_total}",
            "FAIL" if comparable and ratio_failed else "PASS" if comparable else "n/a",
        ),
    )


def count(raw: object, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise RatchetError(f"{label} must be a non-negative integer")
    return raw
