# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture measurement payloads independent of check policy."""

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

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
# AD-97: the scalars a profile may not measure at all; each reads `None` then, never 0.
UnmeasurableScalar: TypeAlias = Literal[
    "private_crossings",
    "typing_positions",
    "calls_unresolved",
    "untyped_private_accesses",
]
UNMEASURABLE: Final[frozenset[UnmeasurableScalar]] = frozenset(
    {"private_crossings", "typing_positions", "calls_unresolved", "untyped_private_accesses"}
)


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
    private_crossings: int | None
    typing_positions: int | None
    calls_unresolved: int | None
    coverage_failures: int
    untyped_private_accesses: int | None = 0
    unknown_positions: int = 0

    def items(self) -> tuple[tuple[str, int | None], ...]:
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
            if value is not None or name not in UNMEASURABLE:
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
        unresolved = self.scalars.calls_unresolved
        if unresolved is not None and unresolved > self.calls_total:
            raise RatchetError("calls_unresolved must not exceed calls_total")
        if self.scalars.coverage_failures:
            raise RatchetError("scan must be complete without coverage failures")


def selected_budgets(
    measurements: Measurements, names: tuple[MeasurementBudgetName, ...]
) -> tuple[MeasurementBudget, ...]:
    """Project contract-selected scalar values from the one typed measurement profile."""
    values = dict(measurements.scalars.items())
    budgets = []
    for name in sorted(names):
        value = values[name]
        if value is None:
            # The analyzer already refuses a budget on a scalar its profile does not measure.
            raise RatchetError(f"measurement budget {name} is not measured by this profile")
        budgets.append(MeasurementBudget(name, value))
    return tuple(budgets)


def compare_budgets(
    accepted: tuple[MeasurementBudget, ...],
    observed: tuple[MeasurementBudget, ...],
    *,
    against: bool,
) -> tuple[str, ...]:
    """Report every changed or mismatched budget; equality is the passing baseline state.

    `against` says the run compares a second revision, which names a calls_unresolved rise's
    call sites itself; without it the finding points at the flag that does (AD-100).
    """
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
            finding = f"measurement budget exceeded in {name}: {accepted_value}->{observed_value}"
            if name == "calls_unresolved" and not against:
                # AD-100: the baseline holds the value alone; a second revision names the sites.
                finding += "; validate --against <ref> names the call sites"
            findings.append(finding)
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
        _compare(name, before, after)
        for (name, before), (_, after) in zip(
            accepted.scalars.items(), candidate.scalars.items(), strict=True
        )
    )
    before_unresolved = accepted.scalars.calls_unresolved
    after_unresolved = candidate.scalars.calls_unresolved
    comparable = accepted.calls_total > 0 and candidate.calls_total > 0
    ratio_failed = (
        before_unresolved is not None
        and after_unresolved is not None
        and after_unresolved * accepted.calls_total > before_unresolved * candidate.calls_total
    )
    return comparisons + (
        (
            "unresolved_ratio",
            f"{_shown(before_unresolved)}/{accepted.calls_total}",
            f"{_shown(after_unresolved)}/{candidate.calls_total}",
            "FAIL" if comparable and ratio_failed else "PASS" if comparable else "n/a",
        ),
    )


def _shown(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _compare(name: str, before: int | None, after: int | None) -> tuple[str, str, str, str]:
    """A side the profile never measured is neither a pass nor a failure (AD-97)."""
    if before is None or after is None:
        return name, _shown(before), _shown(after), "n/a"
    return name, str(before), str(after), "FAIL" if after > before else "PASS"


def count(raw: object, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise RatchetError(f"{label} must be a non-negative integer")
    return raw
