# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regression checks over the typed decoded-IR measurements of each analyzer profile."""

from typing import Final

from archkeel.ir.measurements import (
    Measurements,
    RatchetError,
    RatchetScalars,
    UnmeasurableScalar,
    compare_measurements,
)
from archkeel.ir.model import EvidenceClass, Observation, Record, RecordData
from archkeel.ir.profiles import profile_for

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
_BOUNDARY_POSITION_FIELDS: Final = frozenset(
    {"module", "qualified_name", "position", "annotation", "reason", "occurrence"}
)


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


def _boundary_position_key(data: RecordData) -> tuple[str, str, str, str, str, int]:
    if not _BOUNDARY_POSITION_FIELDS <= frozenset(key for key, _ in data.entries):
        raise RatchetError("boundary_type_position has incomplete coordinate data")
    module = data.get("module")
    qualified_name = data.get("qualified_name")
    position = data.get("position")
    annotation = data.get("annotation")
    reason = data.get("reason")
    occurrence = data.get("occurrence")
    if (
        not isinstance(module, str)
        or not module
        or not isinstance(qualified_name, str)
        or not qualified_name
        or not isinstance(position, str)
        or not position
        or not isinstance(annotation, str)
        or not isinstance(reason, str)
        or not reason
        or not isinstance(occurrence, int)
        or isinstance(occurrence, bool)
        or occurrence < 0
    ):
        raise RatchetError("boundary_type_position has invalid coordinate data")
    return module, qualified_name, position, annotation, reason, occurrence


def _boundary_type_undecided(
    record: Record, position_records: tuple[Record, ...], analyzer_version: str
) -> tuple[int, set[str]]:
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
    details_present = "undecidable_positions" in dict(record.data.entries)
    details = record.data.get("undecidable_positions")
    matching = tuple(item for item in position_records if item.rule_ids == record.rule_ids)
    if not details_present:
        if matching:
            raise RatchetError("boundary_type_limit is missing position details")
        try:
            version = tuple(int(part) for part in analyzer_version.split("."))
        except ValueError as error:
            raise RatchetError("invalid analyzer version for boundary type details") from error
        if len(version) != 3 or any(part < 0 for part in version):
            raise RatchetError("invalid analyzer version for boundary type details")
        if version >= (0, 43, 0):
            raise RatchetError("boundary_type_limit is missing position details")
        return (
            sum(
                value for reason, value in valid_reason_counts.items() if reason != "external_type"
            ),
            set(),
        )
    if not isinstance(details, tuple) or not details or len(record.rule_ids) != 1:
        raise RatchetError("boundary_type_limit has invalid position details")
    expected: list[tuple[str, str, str, str, str, int]] = []
    for detail in details:
        if not isinstance(detail, RecordData):
            raise RatchetError("boundary_type_limit has invalid position details")
        key = _boundary_position_key(detail)
        if key[4] not in valid_reason_counts:
            raise RatchetError("boundary_type_limit has an uncounted detail reason")
        expected.append(key)
    expected_coordinates = [(key[0], key[1], key[2], key[5]) for key in expected]
    if len(set(expected_coordinates)) != len(expected_coordinates):
        raise RatchetError("boundary_type_limit has duplicate position coordinates")
    if len(expected) != undecided:
        raise RatchetError("boundary_type_limit detail count mismatch")
    for reason, count in valid_reason_counts.items():
        if count != sum(1 for key in expected if key[4] == reason):
            raise RatchetError("boundary_type_limit detail reason counts mismatch")
    actual = [_boundary_position_key(item.data) for item in matching]
    actual_coordinates = [(key[0], key[1], key[2], key[5]) for key in actual]
    if len(set(actual_coordinates)) != len(actual_coordinates):
        raise RatchetError("boundary_type_position has duplicate logical coordinates")
    if sorted(actual) != sorted(expected):
        raise RatchetError("boundary_type_limit detail records are missing or inconsistent")
    return (
        sum(1 for key in expected if key[4] != "external_type"),
        {item.id for item in matching},
    )


def _undecided(record: Record) -> int:
    undecided = record.data.get("undecided")
    if isinstance(undecided, int) and not isinstance(undecided, bool) and undecided > 0:
        return undecided
    # A record without a usable count still names at least one position left undecided.
    return 1


def unknown_positions(observation: Observation) -> int:
    """AD-92: count what the scan left undecided, except the kinds that never count."""
    # A coverage failure already makes the scan incomplete (exit 2); counting it adds nothing.
    failed = {record.id for record in observation.coverage.failures}
    records = _records(observation, "unknowns")
    position_records = tuple(item for item in records if item.kind == "boundary_type_position")
    matched_positions: set[str] = set()
    total = 0
    for record in records:
        if record.id in failed or record.kind in _STANDING_DISCLAIMERS:
            continue
        if record.kind == "boundary_type_position":
            continue
        if record.kind == "boundary_type_limit":
            count, matched = _boundary_type_undecided(
                record, position_records, observation.analyzer.version
            )
            total += count
            matched_positions.update(matched)
        else:
            total += _undecided(record)
    if matched_positions != {item.id for item in position_records}:
        raise RatchetError("boundary_type_position has no matching aggregate")
    return total


def _measured(
    unmeasured: frozenset[UnmeasurableScalar], name: UnmeasurableScalar, value: int
) -> int | None:
    return None if name in unmeasured else value


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
        if signal.kind == "boundary_type_allowance" and signal.evidence_class == EvidenceClass.FACT:
            continue
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
    # AD-97: a scalar the observing profile cannot see is null, so no comparison reads it as 0.
    unmeasured = profile_for(observation.analyzer.name).unmeasured
    return Measurements(
        scalars=RatchetScalars(
            violations=len(_records(observation, "violations")),
            cycle_edges=cycle_edges,
            private_crossings=_measured(
                unmeasured, "private_crossings", len(crossing_imports(imports, private=True))
            ),
            typing_positions=_measured(unmeasured, "typing_positions", typing_positions),
            calls_unresolved=_measured(unmeasured, "calls_unresolved", coverage.calls_unresolved),
            coverage_failures=len(coverage.failures),
            untyped_private_accesses=_measured(
                unmeasured,
                "untyped_private_accesses",
                sum(1 for item in unknowns if item.kind == "private_attribute_access_limit"),
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
