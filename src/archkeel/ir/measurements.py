# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture measurement payloads independent of check policy."""

from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

SCALARS = (
    "violations",
    "cycle_edges",
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "coverage_failures",
    "untyped_private_accesses",
    "unknown_positions",
)


MeasurementBudgetName: TypeAlias = Literal[
    "cycle_edges",
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "untyped_private_accesses",
    "unknown_positions",
]
# AD-99: a facade or pair budget accepts a set of names per key rather than one scalar.
NameBudgetKind: TypeAlias = Literal["facade_names", "coupling_names"]


@dataclass(frozen=True, slots=True)
class MeasurementBudget:
    """One accepted value: a selected scalar (AD-89), or one key's accepted names (AD-99)."""

    name: MeasurementBudgetName | NameBudgetKind
    value: int
    key: str = ""
    names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        count(self.value, f"budget {self.label}")
        keyed = self.name in get_args(NameBudgetKind)
        if keyed != bool(self.key) or (not keyed and self.names):
            raise RatchetError(f"budget {self.label} mixes a scalar with a keyed name set")
        if keyed and (
            self.names != tuple(sorted(set(self.names))) or self.value != len(self.names)
        ):
            raise RatchetError(f"budget {self.label} names must be sorted, unique and counted")

    @property
    def label(self) -> str:
        return budget_label(self.name, self.key)


def budget_label(name: str, key: str = "") -> str:
    """How a baseline budget is named in a finding: a scalar alone, a keyed set with its key."""
    return f"{name} {key}" if key else name


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
    unknown_positions: int = 0

    def items(self) -> tuple[tuple[str, int], ...]:
        return (
            ("violations", self.violations),
            ("cycle_edges", self.cycle_edges),
            ("private_crossings", self.private_crossings),
            ("typing_positions", self.typing_positions),
            ("calls_unresolved", self.calls_unresolved),
            ("coverage_failures", self.coverage_failures),
            ("untyped_private_accesses", self.untyped_private_accesses),
            ("unknown_positions", self.unknown_positions),
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
    """Report every changed or mismatched budget; equality is the passing baseline state.

    A keyed budget (AD-99) rises by any name the baseline does not hold and falls by any name
    it holds that is gone, whatever the count does, so freed room cannot be reused unseen.
    """
    before = {item.label: item for item in accepted}
    after = {item.label: item for item in observed}
    findings = []
    for label in sorted(before.keys() | after.keys()):
        if label not in before:
            findings.append(
                f"measurement budget {label} is not in the baseline; rewrite the baseline "
                "with --write-baseline"
            )
            continue
        if label not in after:
            findings.append(
                f"measurement budget {label} is no longer declared; rewrite the baseline "
                "with --write-baseline"
            )
            continue
        new, removed = name_drift(before[label], after[label])
        if new:
            findings.append(f"measurement budget exceeded in {label}: new {', '.join(new)}")
        if removed:
            findings.append(
                f"measurement budget reduced in {label}: removed {', '.join(removed)}; "
                "rewrite the baseline with --write-baseline"
            )
        if new or removed:
            continue
        accepted_value = before[label].value
        observed_value = after[label].value
        if observed_value > accepted_value:
            findings.append(
                f"measurement budget exceeded in {label}: {accepted_value}->{observed_value}"
            )
        elif observed_value < accepted_value:
            findings.append(
                f"measurement budget reduced in {label}: {accepted_value}->{observed_value}; "
                "rewrite the baseline with --write-baseline"
            )
    return tuple(findings)


def name_drift(
    accepted: MeasurementBudget, observed: MeasurementBudget
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The names `observed` adds to and drops from `accepted`; always empty for a scalar."""
    return (
        tuple(sorted(set(observed.names) - set(accepted.names))),
        tuple(sorted(set(accepted.names) - set(observed.names))),
    )


def budget_regressions(
    accepted: tuple[MeasurementBudget, ...], observed: tuple[MeasurementBudget, ...]
) -> int:
    """Count observed rises; new declarations have no prior value to regress from."""
    before = {item.label: item for item in accepted}
    return sum(
        item.label in before
        and (bool(name_drift(before[item.label], item)[0]) or item.value > before[item.label].value)
        for item in observed
    )


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
