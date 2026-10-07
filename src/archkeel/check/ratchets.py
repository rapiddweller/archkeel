# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regression checks over the typed decoded-IR measurements of each analyzer profile."""

from archkeel.ir.decisions import unknown_positions as _ir_unknown_positions
from archkeel.ir.decisions import unknown_positions_by_rule as _ir_unknown_positions_by_rule
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.measurements import (
    Measurements,
    RatchetError,
    RatchetScalars,
    UnmeasurableScalar,
    compare_measurements,
)
from archkeel.ir.model import (
    CallRow,
    CallStatus,
    EvidenceClass,
    Observation,
    Record,
    UnresolvedCallChange,
    text_value,
)
from archkeel.ir.profiles import profile_for

from .python_profile import crossing_imports


# Keep the checker facade local so its exported type surface remains provable.
def unknown_positions_by_rule(observation: Observation) -> dict[str, int]:
    return _ir_unknown_positions_by_rule(observation)


def unknown_positions(observation: Observation) -> int:
    return _ir_unknown_positions(observation)


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


def _measured(
    unmeasured: frozenset[UnmeasurableScalar], name: UnmeasurableScalar, value: int | None
) -> int | None:
    if name in unmeasured:
        return None
    if value is None:
        raise RatchetError(f"{name} is missing for a profile that measures it")
    return value


def measure_python_ratchets(observation: Observation) -> Measurements:
    """Project raw counts; analyzer percentages never participate in the policy."""
    coverage = observation.coverage
    profile = profile_for(observation.analyzer.name)
    if (
        coverage.status != "PASS"
        or coverage.rules == "FAIL"
        or coverage.files_discovered == 0
        or coverage.failures
        or len({coverage.files_discovered, coverage.files_read, coverage.files_parsed}) != 1
    ):
        raise RatchetError("scan must be complete: discovered = read = parsed, without failures")
    calls_measured = "calls_unresolved" not in profile.unmeasured
    total = coverage.calls_analyzed if calls_measured else None
    if calls_measured and (
        total is None
        or coverage.calls_resolved is None
        or coverage.calls_partially_resolved is None
        or coverage.calls_unresolved is None
        or total
        != coverage.calls_resolved + coverage.calls_partially_resolved + coverage.calls_unresolved
    ):
        raise RatchetError("calls_analyzed must equal resolved + partially_resolved + unresolved")
    cycle_edges = sum(
        _positions(cycle.data.get("internal_edges"), "cycle.internal_edges")
        for cycle in _records(observation, "cycles")
    )
    typing_positions: int | None = None
    if "typing_positions" not in profile.unmeasured:
        typing_positions = 0
        for signal in _records(observation, "typing_signals"):
            if (
                signal.kind == "boundary_type_allowance"
                and signal.evidence_class == EvidenceClass.FACT
            ):
                continue
            if signal.kind == "missing_cross_package_annotation":
                typing_positions += _positions(
                    signal.data.get("positions"), "typing_signal.positions"
                )
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
    unmeasured = profile.unmeasured
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


def calls_measured(observation: Observation) -> bool:
    """Whether the observing profile measures calls at all; the Dart profile does not (AD-97)."""
    return observation.records("calls") is not None and (
        "calls_unresolved" not in profile_for(observation.analyzer.name).unmeasured
    )


def call_rows(observation: Observation) -> tuple[CallRow, ...]:
    """Every unresolved and partially resolved call, from the `calls` records (AD-100).

    The rows must add up to the coverage counts, so a listed or compared call is exactly one
    the measurements counted.
    """
    evidence = {item.id: item for item in observation.evidence}
    owners = component_owners(observation)
    rows: list[CallRow] = []
    for record in _records(observation, "calls"):
        data = record.data
        status: CallStatus
        if data.get("status") == "unresolved":
            status = "unresolved"
        elif data.get("status") == "partially_resolved":
            status = "partially_resolved"
        else:
            continue
        module = text_value(data.get("source_module"))
        caller = text_value(data.get("source_scope"))
        expression = text_value(data.get("expression"))
        reason = text_value(data.get("reason"))
        sites = [evidence[item] for item in record.evidence_ids if item in evidence]
        if not (module and caller and expression and reason) or len(sites) != 1:
            raise RatchetError("unresolved call lacks its caller, expression, reason or line")
        component = owner_of(module, owners)
        rows.append(
            CallRow(status, caller, expression, reason, component, sites[0].file, sites[0].line)
        )
    unresolved = sum(row.status == "unresolved" for row in rows)
    coverage = observation.coverage
    if (unresolved, len(rows) - unresolved) != (
        coverage.calls_unresolved,
        coverage.calls_partially_resolved,
    ):
        raise RatchetError("call records do not add up to the coverage call counts")
    return tuple(
        sorted(rows, key=lambda row: (row.path, row.line, row.caller, row.expression, row.status))
    )


def _unresolved_calls(observation: Observation) -> dict[tuple[str, str, str], tuple[CallRow, ...]]:
    """Group the unresolved calls by file, caller and expression, the identity AD-100 compares."""
    grouped: dict[tuple[str, str, str], tuple[CallRow, ...]] = {}
    for row in call_rows(observation):
        if row.status == "unresolved":
            key = (row.path, row.caller, row.expression)
            grouped[key] = (*grouped.get(key, ()), row)
    return grouped


def unresolved_call_changes(
    before: Observation, after: Observation
) -> tuple[UnresolvedCallChange, ...]:
    """Name every unresolved call whose count differs between two observations (AD-100)."""
    old, new = _unresolved_calls(before), _unresolved_calls(after)
    changes = []
    for path, caller, expression in {*old, *new}:
        was = old.get((path, caller, expression), ())
        now = new.get((path, caller, expression), ())
        if len(was) == len(now):
            continue
        added = len(now) > len(was)
        calls = now if added else was
        changes.append(
            UnresolvedCallChange(
                "added" if added else "removed",
                caller,
                expression,
                calls[0].reason,
                calls[0].component,
                path,
                tuple(sorted(call.line for call in calls)),
                len(was),
                len(now),
            )
        )
    return tuple(
        sorted(
            changes,
            key=lambda item: (item.change, item.path, item.lines, item.caller, item.expression),
        )
    )
