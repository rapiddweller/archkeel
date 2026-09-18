# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Deterministic management-level deltas between two typed ArchitectureIR snapshots."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Final

from archkeel.ir.codec import value_bytes
from archkeel.ir.measurements import RatchetError
from archkeel.ir.model import (
    SCHEMA_VERSION,
    ArchitectureDelta,
    DeltaCoverage,
    DeltaProvenance,
    DeltaUnknown,
    Diagnostic,
    DiagnosticError,
    DimensionDelta,
    Evidence,
    JsonValue,
    Observation,
    Projection,
    RatchetObservations,
    Record,
    RecordData,
    SemanticChange,
    SnapshotSummary,
    stable_id,
)

from .python_profile import crossing_imports
from .ratchets import measure_python_ratchets

# AD-43: the eight per-counter coverage records stopped being declarable semantic changes,
# so a candidate that adds one file no longer forces an agent to name five mechanical
# counter shifts; DeltaCoverage still carries one PASS/FAIL for the aggregate.
DELTA_SCHEMA_VERSION: Final = "1.3.0"
SUPPORTED_DIMENSIONS: Final = (
    "violations",
    "dependency_edges",
    "cycles",
    "api_crossings",
    "private_crossings",
    "typing_signals",
    "unknowns",
    "coverage",
)
_REFERENCE_KEYS: Final = {
    "evidence_ids",
    "fact_ids",
    "id",
    "internal_edges",
    "rule_ids",
    "source_rank",
    "target_evidence_ids",
    "target_rank",
}
_AGGREGATE_EVIDENCE_LIMIT: Final = 16


@dataclass(frozen=True, slots=True)
class _DeltaRecord:
    logical_fingerprint: str
    semantic_fingerprint: str
    location_fingerprint: str
    projection: Projection


def _fingerprint(value: JsonValue) -> str:
    return hashlib.sha256(value_bytes(RecordData((("value", value),)))).hexdigest()


def _stable_value(value: JsonValue) -> JsonValue:
    if isinstance(value, RecordData):
        return RecordData(
            tuple(
                (key, _stable_value(entry))
                for key, entry in sorted(value.entries)
                if key not in _REFERENCE_KEYS and not key.endswith("_evidence_ids")
            )
        )
    if isinstance(value, tuple):
        return tuple(_stable_value(entry) for entry in value)
    return value


def _index_records(observation: Observation) -> dict[str, Record]:
    return {record.id: record for section in observation.sections for record in section.records}


def _index_evidence(observation: Observation) -> dict[str, Evidence]:
    return {item.id: item for item in observation.evidence}


def _record_evidence(
    record: Record, *, records: dict[str, Record], evidence: dict[str, Evidence]
) -> tuple[Evidence, ...]:
    pending = [record]
    visited: set[str] = set()
    evidence_ids: set[str] = set()
    while pending:
        current = pending.pop()
        if current.id in visited:
            continue
        visited.add(current.id)
        evidence_ids.update(current.evidence_ids)
        pending.extend(records[fact] for fact in current.fact_ids if fact in records)
    return tuple(
        sorted(
            (evidence[item] for item in evidence_ids if item in evidence),
            key=lambda item: (item.file, item.line, item.end_line, item.column, item.id),
        )
    )


def _project_record(
    record: Record, *, dimension: str, records: dict[str, Record], evidence: dict[str, Evidence]
) -> Projection:
    source_evidence = _record_evidence(record, records=records, evidence=evidence)
    data = record.data
    if (
        dimension in {"cycles", "dependency_edges"}
        and len(source_evidence) > _AGGREGATE_EVIDENCE_LIMIT
    ):
        data = RecordData(
            (
                *((key, value) for key, value in data.entries if key != "delta_evidence"),
                (
                    "delta_evidence",
                    RecordData(
                        (
                            ("available", len(source_evidence)),
                            ("embedded", _AGGREGATE_EVIDENCE_LIMIT),
                            ("truncated", True),
                        )
                    ),
                ),
            )
        )
        source_evidence = source_evidence[:_AGGREGATE_EVIDENCE_LIMIT]
    return Projection(
        record.id,
        record.evidence_class.value,
        record.area,
        record.kind,
        record.title,
        record.subjects,
        data,
        source_evidence,
    )


def _logical_payload(dimension: str, record: Record) -> RecordData:
    data = record.data
    if dimension == "violations":
        return RecordData(
            (
                ("kind", record.kind),
                ("rule_ids", record.rule_ids),
                ("source_module", data.get("source_module")),
                ("target_module", data.get("target_module")),
            )
        )
    if dimension == "dependency_edges":
        return RecordData(tuple((key, data.get(key)) for key in ("level", "source", "target")))
    if dimension == "cycles":
        return RecordData(tuple((key, data.get(key)) for key in ("level", "members")))
    if dimension in {"api_crossings", "private_crossings"}:
        return RecordData(
            tuple((key, data.get(key)) for key in ("source_module", "target_module", "symbol"))
        )
    if dimension == "typing_signals":
        return RecordData(
            (("kind", record.kind), ("owner", data.get("owner")), ("signal", data.get("signal")))
        )
    if dimension == "unknowns":
        return RecordData((("kind", record.kind), ("subjects", record.subjects)))
    return RecordData((("kind", record.kind),))


def _semantic_payload(dimension: str, record: Record) -> RecordData:
    data = (
        RecordData(tuple((key, record.data.get(key)) for key in ("level", "members")))
        if dimension == "cycles"
        else _stable_value(record.data)
    )
    return RecordData(
        (
            ("evidence_class", record.evidence_class.value),
            ("area", record.area),
            ("kind", record.kind),
            ("subjects", record.subjects),
            ("rule_ids", record.rule_ids),
            ("data", data),
        )
    )


def _section(observation: Observation, dimension: str) -> tuple[Record, ...] | None:
    name = {
        "violations": "violations",
        "dependency_edges": "dependency_edges",
        "cycles": "cycles",
        "api_crossings": "imports",
        "private_crossings": "imports",
        "typing_signals": "typing_signals",
        "unknowns": "unknowns",
    }.get(dimension)
    if name is None:
        return None
    records = observation.records(name)
    if records is None:
        return None
    return (
        crossing_imports(records, private=dimension == "private_crossings")
        if dimension in {"api_crossings", "private_crossings"}
        else records
    )


def _delta_records(observation: Observation, dimension: str) -> tuple[_DeltaRecord, ...] | None:
    if dimension == "coverage":
        # AD-43: the counters live on both observations already; comparing them here would
        # make every file added or removed anywhere declare five mechanical entries that
        # carry no information about what the candidate actually changed.
        return ()
    values = _section(observation, dimension)
    if values is None:
        return None
    records, evidence = _index_records(observation), _index_evidence(observation)
    result = []
    for item in values:
        projection = _project_record(item, dimension=dimension, records=records, evidence=evidence)
        locations: JsonValue = tuple(
            tuple((entry.file, entry.line, entry.end_line, entry.column))
            for entry in projection.evidence
        )
        result.append(
            _DeltaRecord(
                _fingerprint(_logical_payload(dimension, item)),
                _fingerprint(_semantic_payload(dimension, item)),
                _fingerprint(locations),
                projection,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.logical_fingerprint,
                item.semantic_fingerprint,
                item.location_fingerprint,
            ),
        )
    )


def _change(
    dimension: str,
    kind: str,
    fingerprint: str,
    before: tuple[_DeltaRecord, ...],
    after: tuple[_DeltaRecord, ...],
) -> SemanticChange:
    return SemanticChange(
        dimension,
        kind,
        fingerprint,
        len(before),
        len(after),
        before[0].projection if before else None,
        after[0].projection if after else None,
        tuple(sorted({item.semantic_fingerprint for item in before}))
        if kind == "changed"
        else None,
        tuple(sorted({item.semantic_fingerprint for item in after})) if kind == "changed" else None,
    )


def _compare_records(
    dimension: str, before: tuple[_DeltaRecord, ...], after: tuple[_DeltaRecord, ...]
) -> tuple[SemanticChange, ...]:
    old_groups: dict[str, list[_DeltaRecord]] = defaultdict(list)
    new_groups: dict[str, list[_DeltaRecord]] = defaultdict(list)
    for item in before:
        old_groups[item.logical_fingerprint].append(item)
    for item in after:
        new_groups[item.logical_fingerprint].append(item)
    changes: list[SemanticChange] = []
    for logical in sorted(old_groups.keys() | new_groups.keys()):
        old = sorted(
            old_groups[logical],
            key=lambda item: (item.semantic_fingerprint, item.location_fingerprint),
        )
        new = sorted(
            new_groups[logical],
            key=lambda item: (item.semantic_fingerprint, item.location_fingerprint),
        )
        exact: dict[tuple[str, str], list[_DeltaRecord]] = defaultdict(list)
        for item in new:
            exact[(item.semantic_fingerprint, item.location_fingerprint)].append(item)
        unmatched_old: list[_DeltaRecord] = []
        for item in old:
            matches = exact[(item.semantic_fingerprint, item.location_fingerprint)]
            if matches:
                matches.pop()
            else:
                unmatched_old.append(item)
        remaining_old = tuple(unmatched_old)
        remaining_new = tuple(item for items in exact.values() for item in items)
        old_by: dict[str, list[_DeltaRecord]] = defaultdict(list)
        new_by: dict[str, list[_DeltaRecord]] = defaultdict(list)
        for item in remaining_old:
            old_by[item.semantic_fingerprint].append(item)
        for item in remaining_new:
            new_by[item.semantic_fingerprint].append(item)
        changed_old: list[_DeltaRecord] = []
        changed_new: list[_DeltaRecord] = []
        for semantic in sorted(old_by.keys() | new_by.keys()):
            left, right = old_by[semantic], new_by[semantic]
            count = min(len(left), len(right))
            if count:
                changes.append(
                    _change(
                        dimension, "relocated", semantic, tuple(left[:count]), tuple(right[:count])
                    )
                )
            changed_old.extend(left[count:])
            changed_new.extend(right[count:])
        count = min(len(changed_old), len(changed_new))
        if count:
            changes.append(
                _change(
                    dimension,
                    "changed",
                    logical,
                    tuple(changed_old[:count]),
                    tuple(changed_new[:count]),
                )
            )
        removed = changed_old[count:]
        added = changed_new[count:]
        for semantic, count in sorted(
            Counter(item.semantic_fingerprint for item in removed).items()
        ):
            changes.append(
                _change(
                    dimension,
                    "removed",
                    semantic,
                    tuple(item for item in removed if item.semantic_fingerprint == semantic)[
                        :count
                    ],
                    (),
                )
            )
        for semantic, count in sorted(Counter(item.semantic_fingerprint for item in added).items()):
            changes.append(
                _change(
                    dimension,
                    "added",
                    semantic,
                    (),
                    tuple(item for item in added if item.semantic_fingerprint == semantic)[:count],
                )
            )
    return tuple(sorted(changes, key=lambda item: (item.dimension, item.change, item.fingerprint)))


def _unknown(dimension: str, reason: str) -> DeltaUnknown:
    return DeltaUnknown(stable_id("UNKNOWN-DELTA", dimension, reason), dimension, reason)


def require_comparable_runtime(baseline: str | None, head: str | None) -> None:
    if baseline is None or head is None or baseline != head:
        raise DiagnosticError(
            Diagnostic(
                "incomparable_runtime",
                f"python_version: {baseline or 'unknown'} -> {head or 'unknown'}",
                "AST observations from different or unknown Python runtimes cannot be compared.",
                "Reobserve both revisions with the same compatible Python runtime.",
            )
        )


def build_architecture_delta(
    baseline: Observation,
    head: Observation,
    *,
    baseline_digest: str,
    head_digest: str,
    checker_digest: str,
) -> ArchitectureDelta:
    """Build a deterministic, fail-closed semantic comparison of two snapshots."""
    require_comparable_runtime(baseline.python_version, head.python_version)
    analyzer_digest, contract_digest = head.analyzer.code_digest, head.contract.digest
    shared = (
        analyzer_digest != "unknown"
        and baseline.analyzer == head.analyzer
        and contract_digest != "unknown"
        and baseline.contract.digest == contract_digest
        and baseline.schema_version == head.schema_version == SCHEMA_VERSION
        and bool(baseline.source.scope)
        and all(baseline.source.scope + head.source.scope)
        and sorted(baseline.source.scope) == sorted(head.source.scope)
    )
    coverage_complete = baseline.coverage.status == "PASS" and head.coverage.status == "PASS"
    try:
        if not shared:
            raise RatchetError(
                "Regression checks require the same known schema, scope, analyzer and contract"
            )
        ratchets = RatchetObservations(
            "SUPPORTED", measure_python_ratchets(baseline), measure_python_ratchets(head)
        )
    except RatchetError as exc:
        ratchets = RatchetObservations("UNKNOWN", reason=str(exc))
    dimensions: list[DimensionDelta] = []
    changes: list[SemanticChange] = []
    unknowns: list[DeltaUnknown] = []
    available = ratchets.status == "SUPPORTED"
    if not available:
        unknowns.append(
            _unknown(
                "ratchets",
                ratchets.reason or "Required regression check measurements are unavailable",
            )
        )
    for dimension in SUPPORTED_DIMENSIONS:
        before = (
            _delta_records(baseline, dimension) if available or dimension == "coverage" else None
        )
        after = _delta_records(head, dimension) if available or dimension == "coverage" else None
        reason = None
        if not shared:
            reason = (
                "Baseline and HEAD must use the same known schema, scope, analyzer and contract"
            )
        elif dimension != "coverage" and not coverage_complete:
            reason = "Incomplete snapshot coverage forbids negative architecture conclusions"
        elif dimension != "coverage" and not available:
            reason = "Required regression check measurements are unavailable"
        if reason is not None or before is None or after is None:
            reason = reason or f"Required ArchitectureIR data for {dimension} is unavailable"
            unknowns.append(_unknown(dimension, reason))
            dimensions.append(
                DimensionDelta(
                    dimension,
                    "UNKNOWN",
                    0 if before is None else len(before),
                    0 if after is None else len(after),
                )
            )
            continue
        current = _compare_records(dimension, before, after)
        changes.extend(current)
        before_count = len(baseline.coverage.failures) if dimension == "coverage" else len(before)
        after_count = len(head.coverage.failures) if dimension == "coverage" else len(after)
        dimensions.append(
            DimensionDelta(
                dimension,
                "SUPPORTED",
                before_count,
                after_count,
                tuple(item.fingerprint for item in current if item.change == "added"),
                tuple(item.fingerprint for item in current if item.change == "removed"),
                tuple(item.fingerprint for item in current if item.change == "relocated"),
                tuple(item.fingerprint for item in current if item.change == "changed"),
            )
        )
    unknown_dimensions = tuple(item.name for item in dimensions if item.status == "UNKNOWN")
    return ArchitectureDelta(
        DELTA_SCHEMA_VERSION,
        head.analyzer,
        DeltaProvenance(
            checker_digest, analyzer_digest, contract_digest, baseline_digest, head_digest
        ),
        SnapshotSummary(
            baseline.source.git_head,
            baseline.source.source_digest,
            baseline.coverage.status,
            baseline.python_version,
        ),
        SnapshotSummary(
            head.source.git_head,
            head.source.source_digest,
            head.coverage.status,
            head.python_version,
        ),
        head.contract,
        DeltaCoverage(
            "PASS" if not unknown_dimensions and coverage_complete and available else "FAIL",
            baseline.coverage.status,
            head.coverage.status,
            tuple(item.name for item in dimensions if item.status == "SUPPORTED"),
            unknown_dimensions,
        ),
        tuple(dimensions),
        ratchets,
        tuple(sorted(changes, key=lambda item: (item.dimension, item.change, item.fingerprint))),
        tuple(sorted(unknowns, key=lambda item: item.id)),
    )
