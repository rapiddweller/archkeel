# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regression checks over the typed Python decoded-IR measurement profile."""

from typing import Final

from archkeel.ir.measurements import (
    Measurements,
    RatchetError,
    RatchetScalars,
    compare_measurements,
)
from archkeel.ir.model import Observation, Record

from .python_profile import crossing_imports

# AD-92: the only `unknowns` kinds that never count. `dynamic_call_limit` and
# `context_alias_limit` are standing disclaimers about the analyzer's static reach that fire on
# every run regardless of the contract, and `private_attribute_access_limit` has its own scalar;
# counting them would make every run UNKNOWN and PASS unreachable. Naming the exceptions rather
# than the counted kinds means a kind a future analyzer profile adds defaults to UNKNOWN, not to
# a silent PASS.
_STANDING_DISCLAIMERS: Final = frozenset(
    {"dynamic_call_limit", "context_alias_limit", "private_attribute_access_limit"}
)
# AD-67 refinement: `external_type` (`_boundary_type_verdict`, `violations.py`) fires once a
# position's type resolves to a module the contract simply does not own, so `boundary_types`
# has no `public` list to check it against -- the question does not apply, unlike the other
# undecidable kinds (`missing_annotation`, `forward_reference`, `dotted_name`, `generic`,
# `union`, `unresolved_name`, `other`), each a real gap in what the checker could read. Naming
# this one exception, rather than that full list, means a kind added to `_UNDECIDABLE_KINDS`
# later defaults to counting: the same fail-toward-UNKNOWN default AD-67 itself chose over
# reading "no violation" as "probably fine". The totals `positions`, `decided` and `undecided`
# that `boundary_type_limits` writes beside the per-kind counts would count a position twice.
_BOUNDARY_TYPE_NEUTRAL: Final = frozenset(
    {"external_type", "positions", "decided", "undecided", "undecidable_positions"}
)
_BOUNDARY_TYPE_TOTALS: Final = _BOUNDARY_TYPE_NEUTRAL - {"external_type"}


def _records(observation: Observation, section: str) -> tuple[Record, ...]:
    records = observation.records(section)
    if records is None:
        raise RatchetError(f"{section} must be a record list")
    return records


def _positions(value: object, label: str) -> int:
    if (
        not isinstance(value, tuple)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise RatchetError(f"{label} must be a non-empty list of distinct strings")
    return len(value)


def _undecided(record: Record) -> int:
    if record.kind == "boundary_type_limit":
        positions = record.data.get("positions")
        decided = record.data.get("decided")
        undecided = record.data.get("undecided")
        reason_counts = {
            reason: value
            for reason, value in record.data.entries
            if reason not in _BOUNDARY_TYPE_TOTALS
        }
        valid_reason_counts = {
            reason: value
            for reason, value in reason_counts.items()
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        }
        if (
            not isinstance(positions, int)
            or isinstance(positions, bool)
            or positions <= 0
            or not isinstance(decided, int)
            or isinstance(decided, bool)
            or decided < 0
            or not isinstance(undecided, int)
            or isinstance(undecided, bool)
            or undecided < 0
            or positions != decided + undecided
            or len(valid_reason_counts) != len(reason_counts)
            or sum(valid_reason_counts.values()) != undecided
        ):
            raise RatchetError("boundary_type_limit has incoherent aggregate counts")
        return sum(
            value for reason, value in valid_reason_counts.items() if reason != "external_type"
        )
    undecided = record.data.get("undecided")
    if isinstance(undecided, int) and not isinstance(undecided, bool) and undecided > 0:
        return undecided
    # A record without a usable count still names at least one position left undecided.
    return 1


def unknown_positions(observation: Observation) -> int:
    """AD-92: count what the scan left undecided, except the kinds that never count."""
    # A coverage failure already makes the scan incomplete (exit 2); counting it adds nothing.
    failed = {record.id for record in observation.coverage.failures}
    return sum(
        _undecided(record)
        for record in _records(observation, "unknowns")
        if record.id not in failed and record.kind not in _STANDING_DISCLAIMERS
    )


def measure_python_ratchets(observation: Observation) -> Measurements:
    """Project raw counts; analyzer percentages never participate in the policy."""
    coverage = observation.coverage
    if (
        coverage.status != "PASS"
        or coverage.rules == "FAIL"
        or coverage.files_discovered == 0
        or coverage.failures
        or len({coverage.files_discovered, coverage.files_read, coverage.files_parsed}) != 1
    ):
        raise RatchetError("scan must be complete: discovered = read = parsed, without failures")
    total = coverage.calls_analyzed
    if (
        total
        != coverage.calls_resolved + coverage.calls_partially_resolved + coverage.calls_unresolved
    ):
        raise RatchetError("calls_analyzed must equal resolved + partially_resolved + unresolved")
    cycle_edges = sum(
        _positions(cycle.data.get("internal_edges"), "cycle.internal_edges")
        for cycle in _records(observation, "cycles")
    )
    typing_positions = 0
    for signal in _records(observation, "typing_signals"):
        if signal.kind == "missing_cross_package_annotation":
            typing_positions += _positions(signal.data.get("positions"), "typing_signal.positions")
        else:
            typing_positions += 1
    imports = _records(observation, "imports")
    unknowns = _records(observation, "unknowns")
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        if symbol is not None and not isinstance(symbol, str):
            raise RatchetError("import.symbol must be a string or null")
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise RatchetError("import packages must be non-empty strings")
    return Measurements(
        scalars=RatchetScalars(
            violations=len(_records(observation, "violations")),
            cycle_edges=cycle_edges,
            private_crossings=len(crossing_imports(imports, private=True)),
            typing_positions=typing_positions,
            calls_unresolved=coverage.calls_unresolved,
            coverage_failures=len(coverage.failures),
            untyped_private_accesses=sum(
                1 for item in unknowns if item.kind == "private_attribute_access_limit"
            ),
            unknown_positions=unknown_positions(observation),
        ),
        calls_total=total,
        resolution="measured" if total else "n/a",
    )


def compare_ratchets(accepted: Measurements, candidate: Measurements) -> tuple[str, ...]:
    """Compare validated measurements supplied by the caller, without rounding."""
    return tuple(
        sorted(
            f"regression check failed in {name}: {accepted_value}->{candidate_value}"
            for name, accepted_value, candidate_value, status in compare_measurements(
                accepted, candidate
            )
            if status == "FAIL"
        )
    )
