# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read and write architecture comparisons with their snapshot metadata."""

from __future__ import annotations

from dataclasses import asdict

from archkeel.ir.codec_governance import _measurement_payload, parse_measurements
from archkeel.ir.codec_observation import (
    _parse_analyzer,
    _parse_runtime,
    _parse_verdict,
    _python_version,
)
from archkeel.ir.codec_wire import (
    _count,
    _exact,
    _object,
    _raw_object,
    _raw_value,
    _string,
    _strings,
)
from archkeel.ir.facts import EvidenceClass as _EvidenceClass
from archkeel.ir.facts import RuntimeRequirementState
from archkeel.ir.model import DELTA_SCHEMA_VERSION as DELTA_SCHEMA_VERSION
from archkeel.ir.model import (
    AnalyzerInfo,
    ArchitectureDelta,
    ComparisonStatus,
    ContractInfo,
    DeltaCoverage,
    DeltaProvenance,
    DeltaUnknown,
    DeltaVersion,
    DimensionDelta,
    Projection,
    RatchetObservations,
    SemanticChange,
    SnapshotSummary,
)
from archkeel.ir.model import RawJson as RawJson
from archkeel.ir.model import supports_nullable_delta_counts as _supports_nullable_delta_counts
from archkeel.ir.profiles import profile_for

from .facts_codec import freeze_data as _data
from .facts_codec import parse_evidence as parse_evidence


def _parse_delta_version(raw: RawJson) -> DeltaVersion:
    value = _string(raw, "delta.schema_version")
    try:
        return DeltaVersion(value)
    except ValueError as error:
        raise ValueError("unsupported delta schema version") from error


def _parse_comparison_status(value: RawJson, label: str) -> ComparisonStatus:
    if isinstance(value, str):
        try:
            return ComparisonStatus(value)
        except ValueError:
            pass
    raise ValueError(f"{label} invalid")


def _projection_payload(value: Projection) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result


def delta_payload(delta: ArchitectureDelta) -> dict[str, RawJson]:
    if delta.schema_version is not DeltaVersion.V2_0 and any(
        snapshot.runtime is not None
        and snapshot.runtime.requirement_state != RuntimeRequirementState.DECLARED
        for snapshot in (delta.baseline, delta.head)
    ):
        raise ValueError("runtime.requirement_state requires Delta schema 2.0.0")
    result = _raw_object(asdict(delta))
    for side in ("baseline", "head"):
        snapshot = result[side]
        if isinstance(snapshot, dict):
            if snapshot.get("runtime") is None:
                del snapshot["runtime"]
            runtime = snapshot.get("runtime")
            if isinstance(runtime, dict):
                if runtime.get("required") is None:
                    del runtime["required"]
                if runtime.get("requirement_state") == RuntimeRequirementState.DECLARED:
                    del runtime["requirement_state"]
            if snapshot.get("producer") is None:
                del snapshot["producer"]
    result["dimensions"] = {
        item.name: {key: value for key, value in _raw_object(asdict(item)).items() if key != "name"}
        for item in delta.dimensions
    }
    changes = []
    for item in delta.semantic_changes:
        change = _raw_object(asdict(item))
        change["before"] = _projection_payload(item.before) if item.before is not None else None
        change["after"] = _projection_payload(item.after) if item.after is not None else None
        if item.before_fingerprints is None:
            del change["before_fingerprints"]
        if item.after_fingerprints is None:
            del change["after_fingerprints"]
        changes.append(change)
    result["semantic_changes"] = changes
    ratchets = delta.ratchets
    if ratchets.status is ComparisonStatus.SUPPORTED:
        if ratchets.baseline is None or ratchets.head is None:
            raise ValueError("supported regression checks require both measurements")
        legacy_calls = not _supports_nullable_delta_counts(delta.schema_version)
        result["ratchets"] = {
            "status": ratchets.status,
            "baseline": _measurement_payload(ratchets.baseline, legacy_calls=legacy_calls),
            "head": _measurement_payload(ratchets.head, legacy_calls=legacy_calls),
        }
    else:
        if ratchets.reason is None:
            raise ValueError("unknown regression checks require a reason")
        result["ratchets"] = {"status": ratchets.status, "reason": ratchets.reason}
    return result


def _projection(raw: object, label: str) -> Projection:
    item = _exact(
        raw,
        {"id", "evidence_class", "area", "kind", "title", "subjects", "data", "evidence"},
        label,
    )
    if not isinstance(item["evidence"], list):
        raise ValueError(f"{label}.evidence must be an array")
    return Projection(
        _string(item["id"], f"{label}.id"),
        _string(item["evidence_class"], f"{label}.evidence_class"),
        _string(item["area"], f"{label}.area"),
        _string(item["kind"], f"{label}.kind"),
        _string(item["title"], f"{label}.title"),
        _strings(item["subjects"], f"{label}.subjects"),
        _data(item["data"], f"{label}.data"),
        tuple(parse_evidence(v, f"{label}.evidence[]") for v in item["evidence"]),
    )


def parse_delta(raw: object) -> ArchitectureDelta:
    item = _exact(
        raw,
        {
            "schema_version",
            "analyzer",
            "provenance",
            "baseline",
            "head",
            "contract",
            "coverage",
            "dimensions",
            "ratchets",
            "semantic_changes",
            "unknowns",
        },
        "delta",
    )
    analyzer = _exact(item["analyzer"], {"name", "version", "code_digest"}, "delta.analyzer")
    provenance = _exact(
        item["provenance"],
        {"checker_digest", "analyzer_digest", "contract_digest", "baseline_digest", "head_digest"},
        "delta.provenance",
    )
    c = _exact(item["contract"], {"schema_version", "digest", "path"}, "delta.contract")
    cv = _exact(
        item["coverage"],
        {"status", "baseline_status", "head_status", "supported_dimensions", "unknown_dimensions"},
        "delta.coverage",
    )
    delta_status = _parse_verdict(cv["status"], "delta coverage status")
    baseline_status = _parse_verdict(cv["baseline_status"], "delta coverage status")
    head_status = _parse_verdict(cv["head_status"], "delta coverage status")
    version = _parse_delta_version(item["schema_version"])
    profile_for(_string(analyzer["name"], "delta.analyzer.name"))
    dimensions_raw = _object(item["dimensions"], "delta.dimensions")
    dimensions = tuple(
        _parse_dimension(name, raw_dimension, version=version)
        for name, raw_dimension in sorted(dimensions_raw.items())
    )
    ratchets = _parse_ratchets(
        item["ratchets"], nullable_calls=_supports_nullable_delta_counts(version)
    )
    semantic_changes_raw = item["semantic_changes"]
    unknowns_raw = item["unknowns"]
    if not isinstance(semantic_changes_raw, list) or not isinstance(unknowns_raw, list):
        raise ValueError("semantic_changes and unknowns must be arrays")
    changes = tuple(
        _parse_semantic_change(value, index) for index, value in enumerate(semantic_changes_raw)
    )
    unknowns = tuple(_parse_delta_unknown(value) for value in unknowns_raw)
    return ArchitectureDelta(
        version,
        AnalyzerInfo(
            _string(analyzer["name"], "analyzer.name"),
            _string(analyzer["version"], "analyzer.version"),
            _string(analyzer["code_digest"], "analyzer.code_digest"),
        ),
        DeltaProvenance(
            *(
                _string(provenance[k], k)
                for k in (
                    "checker_digest",
                    "analyzer_digest",
                    "contract_digest",
                    "baseline_digest",
                    "head_digest",
                )
            )
        ),
        _parse_snapshot_summary(
            item["baseline"],
            "delta.baseline",
            allow_requirement_state=version is DeltaVersion.V2_0,
        ),
        _parse_snapshot_summary(
            item["head"], "delta.head", allow_requirement_state=version is DeltaVersion.V2_0
        ),
        ContractInfo(
            _string(c["schema_version"], "contract.schema_version"),
            _string(c["digest"], "contract.digest"),
            _string(c["path"], "contract.path"),
        ),
        DeltaCoverage(
            delta_status,
            baseline_status,
            head_status,
            _strings(cv["supported_dimensions"], "supported_dimensions"),
            _strings(cv["unknown_dimensions"], "unknown_dimensions"),
        ),
        dimensions,
        ratchets,
        changes,
        unknowns,
    )


def _parse_snapshot_summary(
    raw: RawJson, label: str, *, allow_requirement_state: bool
) -> SnapshotSummary:
    x = _object(raw, label)
    optional = {"python_version", "runtime", "producer"}
    if set(x) - optional != {"git_head", "source_digest", "coverage_status"}:
        raise ValueError(f"{label} fields mismatch")
    coverage_status = _parse_verdict(x["coverage_status"], f"{label}.coverage_status")
    return SnapshotSummary(
        _string(x["git_head"], f"{label}.git_head"),
        _string(x["source_digest"], f"{label}.source_digest"),
        coverage_status,
        _python_version(x["python_version"]) if x.get("python_version") is not None else None,
        _parse_runtime(x["runtime"], allow_requirement_state=allow_requirement_state)
        if "runtime" in x
        else None,
        _parse_analyzer(x["producer"], f"{label}.producer") if "producer" in x else None,
    )


def _parse_dimension(name: str, raw: RawJson, *, version: DeltaVersion) -> DimensionDelta:
    label = f"dimensions.{name}"
    dimension = _exact(
        raw,
        {"status", "before_count", "after_count", "added", "removed", "relocated", "changed"},
        label,
    )
    status = _parse_comparison_status(dimension["status"], f"{label}.status")
    return DimensionDelta(
        name,
        status,
        None
        if _supports_nullable_delta_counts(version)
        and status is ComparisonStatus.UNKNOWN
        and dimension["before_count"] is None
        else _count(dimension["before_count"], f"{label}.before_count"),
        None
        if _supports_nullable_delta_counts(version)
        and status is ComparisonStatus.UNKNOWN
        and dimension["after_count"] is None
        else _count(dimension["after_count"], f"{label}.after_count"),
        _strings(dimension["added"], f"{label}.added"),
        _strings(dimension["removed"], f"{label}.removed"),
        _strings(dimension["relocated"], f"{label}.relocated"),
        _strings(dimension["changed"], f"{label}.changed"),
    )


def _parse_ratchets(raw: object, *, nullable_calls: bool) -> RatchetObservations:
    ratchet_raw = _object(raw, "delta.ratchets")
    status = _parse_comparison_status(ratchet_raw.get("status"), "delta.ratchets status")
    if status is ComparisonStatus.SUPPORTED:
        if set(ratchet_raw) != {"status", "baseline", "head"}:
            raise ValueError("supported regression check fields mismatch")
        return RatchetObservations(
            status,
            parse_measurements(
                ratchet_raw["baseline"], "ratchets.baseline", nullable_calls=nullable_calls
            ),
            parse_measurements(ratchet_raw["head"], "ratchets.head", nullable_calls=nullable_calls),
        )
    if status is ComparisonStatus.UNKNOWN:
        if set(ratchet_raw) != {"status", "reason"}:
            raise ValueError("unknown regression check fields mismatch")
        return RatchetObservations(
            status, reason=_string(ratchet_raw.get("reason"), "ratchets.reason")
        )
    raise ValueError("delta.ratchets status invalid")


def _parse_semantic_change(raw: RawJson, index: int) -> SemanticChange:
    x = _object(raw, f"semantic_changes[{index}]")
    required = {
        "dimension",
        "change",
        "fingerprint",
        "before_count",
        "after_count",
        "before",
        "after",
    }
    optional = {"before_fingerprints", "after_fingerprints"}
    if set(x) - required - optional or not required.issubset(x):
        raise ValueError(f"semantic_changes[{index}] fields mismatch")
    return SemanticChange(
        _string(x["dimension"], "dimension"),
        _string(x["change"], "change"),
        _string(x["fingerprint"], "fingerprint"),
        _count(x["before_count"], "before_count"),
        _count(x["after_count"], "after_count"),
        _projection(x["before"], "before") if x["before"] is not None else None,
        _projection(x["after"], "after") if x["after"] is not None else None,
        _strings(x["before_fingerprints"], "before_fingerprints")
        if "before_fingerprints" in x
        else None,
        _strings(x["after_fingerprints"], "after_fingerprints")
        if "after_fingerprints" in x
        else None,
    )


def _parse_delta_unknown(raw: RawJson) -> DeltaUnknown:
    unknown = _exact(raw, {"id", "dimension", "reason", "evidence_class"}, "unknown")
    raw_evidence = unknown["evidence_class"]
    try:
        evidence_class = _EvidenceClass(raw_evidence) if isinstance(raw_evidence, str) else None
    except ValueError:
        evidence_class = None
    if evidence_class is not _EvidenceClass.UNKNOWN:
        raise ValueError("unknown.evidence_class invalid")
    return DeltaUnknown(
        _string(unknown["id"], "unknown.id"),
        _string(unknown["dimension"], "unknown.dimension"),
        _string(unknown["reason"], "unknown.reason"),
    )
