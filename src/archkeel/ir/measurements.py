# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate architecture measurement payloads independent of check policy."""

import builtins as _builtins
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .profiles import UnmeasurableScalar as UnmeasurableScalar

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


class MeasurementBudgetName(StrEnum):
    CYCLE_EDGES = "cycle_edges"
    PRIVATE_CROSSINGS = "private_crossings"
    TYPING_POSITIONS = "typing_positions"
    CALLS_UNRESOLVED = "calls_unresolved"
    UNTYPED_PRIVATE_ACCESSES = "untyped_private_accesses"
    UNKNOWN_POSITIONS = "unknown_positions"

# AD-97: the scalars a profile may not measure at all; each reads `None` then, never 0.
UNMEASURABLE: Final[frozenset[UnmeasurableScalar]] = frozenset(UnmeasurableScalar)
# AD-99: a facade or pair budget accepts a set of names per key rather than one scalar.
class NameBudgetKind(StrEnum):
    FACADE_NAMES = "facade_names"
    COUPLING_NAMES = "coupling_names"


class MeasurementResolution(StrEnum):
    MEASURED = "measured"
    NOT_APPLICABLE = "n/a"


class MetricComparisonStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "n/a"


@dataclass(frozen=True, slots=True)
class MeasurementBudget:
    """One accepted value: a selected scalar (AD-89), or one key's accepted names (AD-99)."""

    name: MeasurementBudgetName | NameBudgetKind
    value: int
    key: str = ""
    names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        count(self.value, f"budget {self.label}")
        _builtins.object.__setattr__(self, "name", _budget_name(self.name))
        keyed = isinstance(self.name, NameBudgetKind)
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


def _budget_name(value: MeasurementBudgetName | NameBudgetKind) -> MeasurementBudgetName | NameBudgetKind:
    try:
        return MeasurementBudgetName(value)
    except ValueError:
        try:
            return NameBudgetKind(value)
        except ValueError as error:
            raise RatchetError(f"budget {value} is not a supported measurement budget") from error


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
    calls_total: int | None
    resolution: MeasurementResolution

    def __post_init__(self) -> None:
        if self.calls_total is not None:
            count(self.calls_total, "calls_total")
        unresolved = self.scalars.calls_unresolved
        if (self.calls_total is None) != (unresolved is None):
            raise RatchetError("call count availability must agree")
        expected = (
            MeasurementResolution.MEASURED if self.calls_total else MeasurementResolution.NOT_APPLICABLE
        )
        try:
            resolution = MeasurementResolution(self.resolution)
        except ValueError as error:
            raise RatchetError(f"resolution must be {expected}") from error
        if resolution is not expected:
            raise RatchetError(f"resolution must be {expected}")
        _builtins.object.__setattr__(self, "resolution", resolution)
        if (
            unresolved is not None
            and self.calls_total is not None
            and unresolved > self.calls_total
        ):
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
    refused: bool = False,
) -> tuple[str, ...]:
    """Report every changed or mismatched budget; equality is the passing baseline state.

    A keyed budget (AD-99) rises by any name the baseline does not hold and falls by any name
    it holds that is gone, whatever the count does, so freed room cannot be reused unseen.
    `against` says the run compares a second revision, which names a calls_unresolved rise's
    call sites itself; without it the finding points at the flag that does (AD-100).
    `refused` says the findings explain a `--write-baseline` that refused, so none advises
    running it (AD-106).
    """
    rewrite = "" if refused else "; rewrite the baseline with --write-baseline"
    before = {item.label: item for item in accepted}
    after = {item.label: item for item in observed}
    findings = []
    for label in sorted(before.keys() | after.keys()):
        if label not in before:
            findings.append(f"measurement budget {label} is not in the baseline{rewrite}")
            continue
        if label not in after:
            findings.append(f"measurement budget {label} is no longer declared{rewrite}")
            continue
        new, removed = name_drift(before[label], after[label])
        if new:
            findings.append(f"measurement budget exceeded in {label}: new {', '.join(new)}")
        if removed:
            findings.append(
                f"measurement budget reduced in {label}: removed {', '.join(removed)}{rewrite}"
            )
        if new or removed:
            continue
        accepted_value = before[label].value
        observed_value = after[label].value
        if observed_value > accepted_value:
            finding = f"measurement budget exceeded in {label}: {accepted_value}->{observed_value}"
            if after[label].name is MeasurementBudgetName.CALLS_UNRESOLVED and not against:
                # AD-100: the baseline holds the value alone; a second revision names the sites.
                finding += "; validate --against <ref> names the call sites"
            findings.append(finding)
        elif observed_value < accepted_value:
            findings.append(
                f"measurement budget reduced in {label}: {accepted_value}->{observed_value}"
                f"{rewrite}"
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
) -> tuple[tuple[str, str, str, MetricComparisonStatus], ...]:
    comparisons: tuple[tuple[str, str, str, MetricComparisonStatus], ...] = tuple(
        _compare(name, before, after)
        for (name, before), (_, after) in zip(
            accepted.scalars.items(), candidate.scalars.items(), strict=True
        )
    )
    before_unresolved = accepted.scalars.calls_unresolved
    after_unresolved = candidate.scalars.calls_unresolved
    before_total = accepted.calls_total
    after_total = candidate.calls_total
    ratio_status = MetricComparisonStatus.NOT_APPLICABLE
    if (
        before_total is not None
        and after_total is not None
        and before_total > 0
        and after_total > 0
        and before_unresolved is not None
        and after_unresolved is not None
    ):
        ratio_status = (
            MetricComparisonStatus.FAIL if after_unresolved * before_total > before_unresolved * after_total else MetricComparisonStatus.PASS
        )
    return comparisons + (
        (
            "unresolved_ratio",
            f"{_shown(before_unresolved)}/{_shown(before_total)}",
            f"{_shown(after_unresolved)}/{_shown(after_total)}",
            ratio_status,
        ),
    )


def _shown(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _compare(name: str, before: int | None, after: int | None) -> tuple[str, str, str, MetricComparisonStatus]:
    """A side the profile never measured is neither a pass nor a failure (AD-97)."""
    if before is None or after is None:
        return name, _shown(before), _shown(after), MetricComparisonStatus.NOT_APPLICABLE
    return name, str(before), str(after), MetricComparisonStatus.FAIL if after > before else MetricComparisonStatus.PASS


def count(raw: object, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise RatchetError(f"{label} must be a non-negative integer")
    return raw
