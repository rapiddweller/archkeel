# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture measurement payloads independent of check policy."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

SCALARS = (
    "violations",
    "cycle_edges",
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "coverage_failures",
    "untyped_private_accesses",
)


MeasurementBudgetName: TypeAlias = Literal[
    "cycle_edges",
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "untyped_private_accesses",
]


@dataclass(frozen=True, slots=True)
class MeasurementBudget:
    name: MeasurementBudgetName
    value: int

    def __post_init__(self) -> None:
        count(self.value, f"budget {self.name}")


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
    untyped_private_accesses: int = 0

    def items(self) -> tuple[tuple[str, int], ...]:
        return (
            ("violations", self.violations),
            ("cycle_edges", self.cycle_edges),
            ("private_crossings", self.private_crossings),
            ("typing_positions", self.typing_positions),
            ("calls_unresolved", self.calls_unresolved),
            ("coverage_failures", self.coverage_failures),
            ("untyped_private_accesses", self.untyped_private_accesses),
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


def selected_budgets(
    measurements: Measurements, names: tuple[MeasurementBudgetName, ...]
) -> tuple[MeasurementBudget, ...]:
    """Project contract-selected scalar values from the one typed measurement profile."""
    values = dict(measurements.scalars.items())
    return tuple(MeasurementBudget(name, values[name]) for name in sorted(names))


def compare_budgets(
    accepted: tuple[MeasurementBudget, ...], observed: tuple[MeasurementBudget, ...]
) -> tuple[str, ...]:
    """Report every changed or mismatched budget; equality is the passing baseline state."""
    before = {item.name: item.value for item in accepted}
    after = {item.name: item.value for item in observed}
    findings = []
    for name in sorted(before.keys() | after.keys()):
        if name not in before:
            findings.append(
                f"measurement budget {name} is not in the baseline; rewrite the baseline "
                "with --write-baseline"
            )
            continue
        if name not in after:
            findings.append(
                f"measurement budget {name} is no longer declared; rewrite the baseline "
                "with --write-baseline"
            )
            continue
        accepted_value = before[name]
        observed_value = after[name]
        if observed_value > accepted_value:
            findings.append(
                f"measurement budget exceeded in {name}: {accepted_value}->{observed_value}"
            )
        elif observed_value < accepted_value:
            findings.append(
                f"measurement budget reduced in {name}: {accepted_value}->{observed_value}; "
                "rewrite the baseline with --write-baseline"
            )
    return tuple(findings)


def budget_regressions(
    accepted: tuple[MeasurementBudget, ...], observed: tuple[MeasurementBudget, ...]
) -> int:
    """Count observed rises; new declarations have no prior value to regress from."""
    before = {item.name: item.value for item in accepted}
    return sum(item.name in before and item.value > before[item.name] for item in observed)


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
