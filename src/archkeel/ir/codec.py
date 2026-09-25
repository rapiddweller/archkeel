# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode validated IR values and preserve the canonical wire representation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from math import isfinite
from typing import Any, Final, Literal, TypeAlias, TypeGuard, get_args

from archkeel.ir.baseline import (
    BASELINE_SCHEMA_VERSION,
    LEGACY_BASELINE_SCHEMA_VERSION,
    ROLES_BASELINE_SCHEMA_VERSION,
    SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION,
    KnownViolation,
    ValidationBaseline,
    canonical_fingerprint,
)
from archkeel.ir.lock import AcceptedLock, LockError
from archkeel.ir.measurements import (
    SCALARS,
    MeasurementBudget,
    MeasurementBudgetName,
    Measurements,
    NameBudgetKind,
    RatchetError,
    RatchetScalars,
    count,
)
from archkeel.ir.model import (
    CLASSIFIED_SECTIONS,
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    AllowedDependencyRule,
    AnalyzerInfo,
    ArchitectureContract,
    ArchitectureDelta,
    ArchitectureRule,
    BoundaryTypeAllowance,
    BoundaryTypesRule,
    ComparisonStatus,
    CompatibilityLifetime,
    CompatibilityShim,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ComponentRole,
    ContractCapability,
    ContractCommand,
    ContractComponent,
    ContractDeclarations,
    ContractInfo,
    ContractMeasurementBudget,
    ContractOwner,
    ContractPath,
    ContractPathKind,
    ContractReviewScope,
    CouplingBudget,
    Coverage,
    DeltaCoverage,
    DeltaProvenance,
    DeltaUnknown,
    DimensionDelta,
    Evidence,
    EvidenceClass,
    ExternalDependencyScopeRule,
    FacadeBudget,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    JsonValue,
    NoComponentCyclesRule,
    Observation,
    OpenDecision,
    Projection,
    RatchetObservations,
    Record,
    RecordData,
    RequiredComponent,
    RootLayoutRule,
    RunResult,
    Section,
    SemanticChange,
    SiblingIsolationRule,
    SnapshotSummary,
    SourceInfo,
    SymbolClassKind,
    SymbolPlacementRule,
    Verdict,
    contract_relative_path,
)
from archkeel.ir.profiles import OPTIONAL_SECTIONS
from archkeel.ir.widening import AMENDMENT_SCHEMA_VERSION, Amendment

_STRING_REFERENCE = re.compile(r"^\$\d+$")
_ESCAPED_STRING_REFERENCE = re.compile(r"^\$\$+\d+$")
_PUBLIC_ENTRY = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)
_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
RawJson: TypeAlias = str | int | float | bool | None | Sequence["RawJson"] | Mapping[str, "RawJson"]

_MISSING_VALUE = object()
_TOP_LEVEL = {
    "schema_version",
    "analyzer",
    "source",
    "contract",
    "coverage",
    *CLASSIFIED_SECTIONS,
    "evidence",
}
_RECORD_KEYS = set(RECORD_FIELDS)
_EVIDENCE_KEYS = set(EVIDENCE_FIELDS)
_COVERAGE_KEYS = {
    "status",
    "files_discovered",
    "files_read",
    "files_parsed",
    "calls_analyzed",
    "calls_resolved",
    "calls_partially_resolved",
    "calls_unresolved",
    "ast_coverage_percent",
    "call_resolution_percent",
    "failures",
    "rules",
}
_COVERAGE_REQUIRED_KEYS = _COVERAGE_KEYS - {"rules"}
CONTRACT_SCHEMA_VERSION: Final = "2.1.0"


class ContractVersionError(ValueError):
    """The contract declares a schema version this parser cannot interpret."""

    def __init__(self, actual: str) -> None:
        self.actual = actual
        super().__init__(f"contract.schema_version {actual!r} is not {CONTRACT_SCHEMA_VERSION}")


def _object(raw: object, label: str) -> dict[str, RawJson]:
    if not isinstance(raw, dict) or not all(isinstance(k, str) for k in raw):
        raise ValueError(f"{label} must be an object")
    return raw


def _string(raw: object, label: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be a string")
    return raw


def _strings(raw: object, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise ValueError(f"{label} must be a string array")
    return tuple(raw)


def _is_verdict(value: RawJson) -> TypeGuard[Verdict]:
    return value in get_args(Verdict)


def _is_comparison_status(value: RawJson) -> TypeGuard[ComparisonStatus]:
    return value in get_args(ComparisonStatus)


def _is_compatibility_lifetime(value: RawJson) -> TypeGuard[CompatibilityLifetime]:
    return value in get_args(CompatibilityLifetime)


def _percent(value: RawJson, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0 <= value <= 100
    ):
        raise ValueError(f"{label} percentages invalid")
    return value


def _data(raw: object, label: str = "data") -> RecordData:
    value = _object(raw, label)
    return RecordData(tuple((key, _value(item, f"{label}.{key}")) for key, item in value.items()))


def _value(raw: object, label: str) -> JsonValue:
    if raw is None or isinstance(raw, (str, bool, int, float)):
        return raw
    if isinstance(raw, list):
        return tuple(_value(item, f"{label}[]") for item in raw)
    if isinstance(raw, dict):
        return _data(raw, label)
    raise ValueError(f"{label} is not a JSON value")


def parse_record(raw: object, label: str = "record") -> Record:
    item = _object(raw, label)
    if set(item) != _RECORD_KEYS:
        raise ValueError(f"{label} fields mismatch")
    try:
        evidence_class = EvidenceClass(_string(item["evidence_class"], f"{label}.evidence_class"))
    except ValueError as exc:
        raise ValueError(f"{label}.evidence_class is invalid") from exc
    rule_ids = _strings(item["rule_ids"], f"{label}.rule_ids")
    # schema/architecture-ir-common.schema.json promises minItems: 1 here for VIOLATION but
    # does not enforce it at runtime; a downstream count keyed on `rule_ids[0]` (AD-51, AD-54)
    # would otherwise fail on a malformed file with an IndexError, not a named diagnosis.
    if evidence_class == EvidenceClass.VIOLATION and not rule_ids:
        raise ValueError(f"{label}.rule_ids must not be empty for a VIOLATION record")
    return Record(
        id=_string(item["id"], f"{label}.id"),
        evidence_class=evidence_class,
        area=_string(item["area"], f"{label}.area"),
        kind=_string(item["kind"], f"{label}.kind"),
        title=_string(item["title"], f"{label}.title"),
        subjects=_strings(item["subjects"], f"{label}.subjects"),
        evidence_ids=_strings(item["evidence_ids"], f"{label}.evidence_ids"),
        rule_ids=rule_ids,
        fact_ids=_strings(item["fact_ids"], f"{label}.fact_ids"),
        provenance=_strings(item["provenance"], f"{label}.provenance"),
        data=_data(item["data"], f"{label}.data"),
    )


def _position(raw: RawJson, label: str) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{label} positions must be integers")
    return raw


def parse_evidence(raw: object, label: str = "evidence") -> Evidence:
    item = _object(raw, label)
    if set(item) != _EVIDENCE_KEYS:
        raise ValueError(f"{label} fields mismatch")
    line, end_line, column = (_position(item[key], label) for key in ("line", "end_line", "column"))
    return Evidence(
        id=_string(item["id"], f"{label}.id"),
        file=_string(item["file"], f"{label}.file"),
        line=line,
        end_line=end_line,
        column=column,
        excerpt=_string(item["excerpt"], f"{label}.excerpt"),
    )


def parse_observation(raw: object) -> Observation:
    item = _object(raw, "observation")
    if set(item) - {"python_version"} != _TOP_LEVEL:
        raise ValueError("observation fields mismatch")
    analyzer = _object(item["analyzer"], "analyzer")
    source = _object(item["source"], "source")
    contract = _object(item["contract"], "contract")
    coverage = _object(item["coverage"], "coverage")
    if set(analyzer) != {"name", "version", "code_digest"}:
        raise ValueError("analyzer fields mismatch")
    if set(source) != {"git_head", "dirty", "source_digest", "scope"}:
        raise ValueError("source fields mismatch")
    if set(contract) != {"schema_version", "digest", "path"}:
        raise ValueError("contract fields mismatch")
    dirty = source["dirty"]
    if dirty is not True and dirty is not False and dirty != "unknown":
        raise ValueError("source.dirty is invalid")
    dirty_value: bool | Literal["unknown"] = (
        True if dirty is True else False if dirty is False else "unknown"
    )
    coverage_value = _parse_coverage(coverage)
    evidence_raw = item["evidence"]
    if not isinstance(evidence_raw, list):
        raise ValueError("coverage.failures and evidence must be arrays")
    sections = tuple(
        Section(name, tuple(parse_record(value, f"{name}[]") for value in section_items))
        for name in CLASSIFIED_SECTIONS
        if isinstance(section_items := item[name], list)
    )
    # AD-97: a section the profile never observes is null, so `records()` answers None for it.
    absent = {name for name in OPTIONAL_SECTIONS if item[name] is None}
    if len(sections) + len(absent) != len(CLASSIFIED_SECTIONS):
        raise ValueError("sections must be arrays")
    return Observation(
        schema_version=_string(item["schema_version"], "schema_version"),
        analyzer=AnalyzerInfo(
            *(_string(analyzer[k], f"analyzer.{k}") for k in ("name", "version", "code_digest"))
        ),
        source=SourceInfo(
            _string(source["git_head"], "source.git_head"),
            dirty_value,
            _string(source["source_digest"], "source.source_digest"),
            _strings(source["scope"], "source.scope"),
        ),
        contract=ContractInfo(
            *(_string(contract[k], f"contract.{k}") for k in ("schema_version", "digest", "path"))
        ),
        coverage=coverage_value,
        sections=sections,
        evidence=tuple(parse_evidence(value, "evidence[]") for value in evidence_raw),
        python_version=_python_version(item["python_version"])
        if "python_version" in item
        else None,
    )


def _parse_coverage(coverage: dict[str, RawJson]) -> Coverage:
    if set(coverage) - _COVERAGE_KEYS or not _COVERAGE_REQUIRED_KEYS.issubset(coverage):
        raise ValueError("coverage fields mismatch")
    status = coverage["status"]
    rules = coverage.get("rules")
    if not _is_verdict(status):
        raise ValueError("coverage status/rules invalid")
    if rules is not None and not _is_verdict(rules):
        raise ValueError("coverage status/rules invalid")
    counts = (
        "files_discovered",
        "files_read",
        "files_parsed",
        "calls_analyzed",
        "calls_resolved",
        "calls_partially_resolved",
        "calls_unresolved",
    )
    count_values = {k: _count(coverage[k], f"coverage.{k}") for k in counts}
    ast_coverage_percent = _percent(coverage["ast_coverage_percent"], "coverage")
    call_resolution_percent = _percent(coverage["call_resolution_percent"], "coverage")
    failures_raw = coverage["failures"]
    if not isinstance(failures_raw, list):
        raise ValueError("coverage.failures and evidence must be arrays")
    return Coverage(
        status=status,
        **count_values,
        ast_coverage_percent=ast_coverage_percent,
        call_resolution_percent=call_resolution_percent,
        failures=tuple(parse_record(v, "coverage.failures[]") for v in failures_raw),
        rules=rules,
    )


def _python_version(raw: object) -> str:
    value = _string(raw, "python_version")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[ab][0-9]+|rc[0-9]+)?", value) is None:
        raise ValueError("python_version must be a canonical full Python version")
    return value


def _raw_object(value: dict[str, Any]) -> dict[str, RawJson]:
    return {key: _raw_value(item) for key, item in value.items()}


def _raw_value(value: JsonValue | dict[str, Any] | tuple[Any, ...]) -> RawJson:
    if isinstance(value, RecordData):
        return {key: _raw_value(item) for key, item in value.entries}
    if isinstance(value, tuple):
        return [_raw_value(item) for item in value]
    if isinstance(value, dict):
        return _raw_object(value)
    return value


def value_bytes(value: JsonValue) -> bytes:
    """Canonical JSON bytes for one immutable IR value."""
    return (
        json.dumps(_raw_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def observation_payload(observation: Observation) -> dict[str, RawJson]:
    result = _raw_object(asdict(observation))
    if observation.python_version is None:
        del result["python_version"]
    del result["sections"]
    result["coverage"] = _coverage_payload(observation.coverage)
    for name in OPTIONAL_SECTIONS:
        result[name] = None
    result.update(
        {
            section.name: [_record_payload(record) for record in section.records]
            for section in observation.sections
        }
    )
    return result


def canonical_json_bytes(model: dict[str, RawJson]) -> bytes:
    """Serialize the canonical model without time, locale, or filesystem noise."""
    return (
        json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def encode_canonical_model(model: dict[str, RawJson]) -> dict[str, RawJson]:
    """Losslessly columnize and intern repeated IR strings for browser-safe reports."""
    encoded = {
        key: value for key, value in model.items() if key not in {*CLASSIFIED_SECTIONS, "evidence"}
    }
    section_data_fields: dict[str, list[str]] = {}
    # AD-2: rows hold the non-JSON _MISSING_VALUE sentinel until intern writes "$m".
    rows_by_section: dict[str, list[list[Any]]] = {}
    for section in CLASSIFIED_SECTIONS:
        raw_items = model.get(section, [])
        if raw_items is None and section in OPTIONAL_SECTIONS:
            encoded[section] = None
            section_data_fields[section] = []
            continue
        if not isinstance(raw_items, list):
            raise ValueError(f"{section} must be an array")
        items = [_object(entry, f"{section}[]") for entry in raw_items]
        data_fields = sorted({key for item in items for key in _object(item["data"], "data")})
        section_data_fields[section] = data_fields
        rows_by_section[section] = [
            [
                *(item[field] for field in RECORD_FIELDS[:-1]),
                [_object(item["data"], "data").get(field, _MISSING_VALUE) for field in data_fields],
            ]
            for item in items
        ]
    raw_evidence = model.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raise ValueError("evidence must be an array")
    evidence_items = [_object(entry, "evidence[]") for entry in raw_evidence]
    evidence_rows = [[item[field] for field in EVIDENCE_FIELDS] for item in evidence_items]

    counts: Counter[str] = Counter()

    def count_strings(value: object) -> None:
        if isinstance(value, str):
            counts[value] += 1
        elif isinstance(value, list):
            for entry in value:
                count_strings(entry)
        elif isinstance(value, dict):
            for entry in value.values():
                count_strings(entry)

    count_strings(rows_by_section)
    count_strings(evidence_rows)
    string_table = sorted(
        value
        for value, count in counts.items()
        if count >= 2 and len(value) >= 8 and (count - 1) * len(value) - count * 8 > 100
    )
    string_indexes = {value: index for index, value in enumerate(string_table)}

    # AD-2: rows mix RawJson with the _MISSING_VALUE sentinel; see rows_by_section.
    def intern(value: Any) -> Any:
        if value is _MISSING_VALUE:
            return "$m"
        if isinstance(value, str):
            if value in string_indexes:
                return f"${string_indexes[value]}"
            if (
                value == "$m"
                or value == "$$m"
                or _STRING_REFERENCE.fullmatch(value)
                or _ESCAPED_STRING_REFERENCE.fullmatch(value)
            ):
                return f"${value}"
            return value
        if isinstance(value, list):
            return [intern(entry) for entry in value]
        if isinstance(value, dict):
            return {key: intern(entry) for key, entry in value.items()}
        return value

    encoded.update({section: intern(rows) for section, rows in rows_by_section.items()})
    encoded["evidence"] = intern(evidence_rows)
    encoding: dict[str, RawJson] = {
        "kind": "architecture-ir-columnar-v1",
        "record_fields": list(RECORD_FIELDS),
        "evidence_fields": list(EVIDENCE_FIELDS),
        "section_data_fields": section_data_fields,
        "string_reference": "$<index>",
        "escaped_literal": "additional leading $",
    }
    encoded["encoding"] = encoding
    encoded["string_table"] = string_table
    return encoded


def decode_canonical_model(encoded: dict[str, RawJson]) -> dict[str, RawJson]:
    """Inflate the canonical columnar report into the in-memory ArchitectureIR."""
    encoding = encoded.get("encoding")
    if not isinstance(encoding, dict) or encoding.get("kind") != "architecture-ir-columnar-v1":
        return encoded
    string_table = _strings(encoded["string_table"], "string_table")

    def expand(value: Any) -> Any:
        # AD-2: expanded rows may hold the non-JSON _MISSING_VALUE sentinel at any depth.
        if isinstance(value, str):
            if value == "$m":
                return _MISSING_VALUE
            if value == "$$m":
                return "$m"
            if _STRING_REFERENCE.fullmatch(value):
                return string_table[int(value[1:])]
            if _ESCAPED_STRING_REFERENCE.fullmatch(value):
                return value[1:]
            return value
        if isinstance(value, list):
            return [expand(entry) for entry in value]
        if isinstance(value, dict):
            return {key: expand(entry) for key, entry in value.items()}
        return value

    model: dict[str, RawJson] = {
        key: value
        for key, value in encoded.items()
        if key not in {*CLASSIFIED_SECTIONS, "evidence", "encoding", "string_table"}
    }
    record_fields = _strings(encoding["record_fields"], "record_fields")
    section_data_fields = _object(encoding["section_data_fields"], "section_data_fields")
    for section in CLASSIFIED_SECTIONS:
        if section not in section_data_fields:
            # An observation from an analyzer that predates this section: fail closed (AD-3).
            raise ValueError(f"observation has no section {section}")
        data_fields = _strings(section_data_fields[section], f"section_data_fields.{section}")
        encoded_rows = encoded.get(section, [])
        if encoded_rows is None and section in OPTIONAL_SECTIONS:
            model[section] = None
            continue
        if not isinstance(encoded_rows, list):
            raise ValueError(f"{section} must be an array")
        records = []
        for encoded_row in encoded_rows:
            row = expand(encoded_row)
            item = dict(zip(record_fields, row, strict=True))
            item["data"] = {
                key: value
                for key, value in zip(data_fields, item["data"], strict=True)
                if value is not _MISSING_VALUE
            }
            records.append(item)
        model[section] = records
    evidence_fields = _strings(encoding["evidence_fields"], "evidence_fields")
    encoded_evidence = encoded.get("evidence", [])
    if not isinstance(encoded_evidence, list):
        raise ValueError("evidence must be an array")
    model["evidence"] = [
        dict(zip(evidence_fields, expand(row), strict=True)) for row in encoded_evidence
    ]
    return model


def canonical_report_bytes(model: Observation | dict[str, RawJson]) -> bytes:
    raw = observation_payload(model) if isinstance(model, Observation) else model
    return canonical_json_bytes(encode_canonical_model(raw))


def _measurement_payload(value: Measurements) -> dict[str, RawJson]:
    return _raw_object(asdict(value))


def _coverage_payload(value: Coverage) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    result["failures"] = [_record_payload(record) for record in value.failures]
    if value.rules is None:
        del result["rules"]
    return result


def _projection_payload(value: Projection) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result


def delta_payload(delta: ArchitectureDelta) -> dict[str, RawJson]:
    result = _raw_object(asdict(delta))
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
    if ratchets.status == "SUPPORTED":
        if ratchets.baseline is None or ratchets.head is None:
            raise ValueError("supported regression checks require both measurements")
        result["ratchets"] = {
            "status": "SUPPORTED",
            "baseline": _measurement_payload(ratchets.baseline),
            "head": _measurement_payload(ratchets.head),
        }
    else:
        if ratchets.reason is None:
            raise ValueError("unknown regression checks require a reason")
        result["ratchets"] = {"status": "UNKNOWN", "reason": ratchets.reason}
    return result


def decode_json(payload: bytes | str) -> object:
    try:
        return json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc


def _exact(value: object, keys: set[str], label: str) -> dict[str, RawJson]:
    result = _object(value, label)
    if set(result) != keys:
        raise ValueError(f"{label} fields mismatch")
    return result


def _contract_fields(
    raw: RawJson, required: set[str], optional: set[str], label: str
) -> dict[str, RawJson]:
    item: dict[str, RawJson] = _object(raw, label)
    if not required <= set(item) or set(item) - required - optional:
        raise ValueError(f"{label} fields mismatch")
    return item


def _nonempty(raw: RawJson, label: str) -> str:
    value = _string(raw, label)
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _decided_by(raw: RawJson, label: str) -> Literal["architect", "agent"]:
    """Narrow to the Literal by value, never by cast (AD-16)."""
    value = _nonempty(raw, label)
    if value == "architect":
        return "architect"
    if value == "agent":
        return "agent"
    raise ValueError(f"{label} must be architect or agent")


def _contract_strings(raw: RawJson, label: str, *, required: bool = False) -> tuple[str, ...]:
    values = _strings(raw, label)
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    if any(not value.strip() for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must contain unique non-empty strings")
    return values


def _contract_record(
    raw: RawJson, required: set[str], optional: set[str], label: str
) -> tuple[dict[str, RawJson], str, tuple[str, ...]]:
    item = _contract_fields(raw, required | {"id", "provenance"}, optional, label)
    provenance = _contract_strings(item["provenance"], label + ".provenance", required=True)
    return item, _nonempty(item["id"], label + ".id"), provenance


def parse_contract(raw: object) -> ArchitectureContract:
    """Parse Contract 2.0 structure without repository-dependent reference checks."""
    root = _contract_fields(
        _object(raw, "contract"),
        {"schema_version", "components", "rules"},
        {"$schema", "declarations"},
        "contract",
    )
    if root["schema_version"] != CONTRACT_SCHEMA_VERSION:
        raise ContractVersionError(str(root["schema_version"]))
    components_raw = root["components"]
    rules_raw = root["rules"]
    if not isinstance(components_raw, list) or not isinstance(rules_raw, list):
        raise ValueError("contract components and rules must be arrays")

    declarations_raw = root.get("declarations")
    declarations = (
        _contract_fields(
            declarations_raw,
            set(),
            {
                "capabilities",
                "review_scopes",
                "public_api",
                "public_api_provenance",
                "public_commands",
                "context_roots",
                "context_roots_provenance",
                "paths",
                "spot_owners",
                "compat",
                "measurement_budgets",
                "facade_budgets",
                "coupling_budgets",
            },
            "contract.declarations",
        )
        if declarations_raw is not None
        else {}
    )

    def records(key: str) -> list[RawJson]:
        value = declarations.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"contract.declarations.{key} must be an array")
        return value

    capabilities = tuple(
        _parse_capability(value, f"capabilities[{index}]")
        for index, value in enumerate(records("capabilities"))
    )
    components = tuple(
        _parse_component(value, f"components[{index}]")
        for index, value in enumerate(components_raw)
    )
    for component in components:
        if (
            component.namespace is not None
            and sum(component.namespace in other.packages for other in components) != 1
        ):
            raise ValueError(
                f"component {component.label!r}.namespace must identify one component package"
            )
    scopes = tuple(
        _parse_review_scope(value, f"review_scopes[{index}]")
        for index, value in enumerate(records("review_scopes"))
    )
    commands = tuple(
        _parse_command(value, f"public_commands[{index}]")
        for index, value in enumerate(records("public_commands"))
    )
    paths = tuple(
        _parse_contract_path(value, f"paths[{index}]")
        for index, value in enumerate(records("paths"))
    )
    owners = tuple(
        _parse_owner(value, f"spot_owners[{index}]")
        for index, value in enumerate(records("spot_owners"))
    )
    compat = tuple(
        _parse_compat(value, f"compat[{index}]") for index, value in enumerate(records("compat"))
    )
    if len({item.module for item in compat}) != len(compat):
        raise ValueError("contract.declarations.compat modules must be unique")
    budgets = tuple(
        _parse_measurement_budget(value, f"measurement_budgets[{index}]")
        for index, value in enumerate(records("measurement_budgets"))
    )
    if len({item.name for item in budgets}) != len(budgets):
        raise ValueError("contract.declarations.measurement_budgets repeats a name")
    facade_budgets = (
        tuple(
            _parse_facade_budget(value, f"facade_budgets[{index}]")
            for index, value in enumerate(records("facade_budgets"))
        )
        if "facade_budgets" in declarations
        else None
    )
    coupling_budgets = (
        tuple(
            _parse_coupling_budget(value, f"coupling_budgets[{index}]")
            for index, value in enumerate(records("coupling_budgets"))
        )
        if "coupling_budgets" in declarations
        else None
    )
    rules = tuple(_parse_rule(value, f"rules[{index}]") for index, value in enumerate(rules_raw))
    labels = {component.label for component in components}
    for index, rule in enumerate(rules):
        if isinstance(rule, NoComponentCyclesRule) and rule.components is not None:
            unknown = sorted(set(rule.components) - labels)
            if unknown:
                raise ValueError(
                    f"rules[{index}].components names no declared component: {unknown}"
                )
    _check_interface_budgets(components, rules, facade_budgets or (), coupling_budgets or ())
    ids = [
        item.id
        for group in (capabilities, components, scopes, commands, paths, owners, rules)
        for item in group
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate contract ID")
    schema = root.get("$schema")
    return ArchitectureContract(
        CONTRACT_SCHEMA_VERSION,
        components,
        rules,
        _nonempty(schema, "contract.$schema") if schema is not None else None,
        ContractDeclarations(
            capabilities,
            scopes,
            _contract_strings(
                declarations.get("public_api", []), "contract.declarations.public_api"
            ),
            _contract_strings(
                declarations.get("public_api_provenance", []),
                "contract.declarations.public_api_provenance",
            ),
            commands,
            _contract_strings(
                declarations.get("context_roots", []), "contract.declarations.context_roots"
            ),
            _contract_strings(
                declarations.get("context_roots_provenance", []),
                "contract.declarations.context_roots_provenance",
            ),
            paths,
            owners,
            compat,
            budgets,
            facade_budgets,
            coupling_budgets,
        )
        if declarations_raw is not None
        else None,
    )


def contract_bytes(contract: ArchitectureContract) -> bytes:
    """Encode a contract in Contract 2.0 key order so parse_contract returns the same value."""
    fields = asdict(contract)
    schema = fields.pop("schema")
    document = {**({"$schema": schema} if schema is not None else {}), **fields}
    return (json.dumps(_without_none(document), indent=2, ensure_ascii=False) + "\n").encode()


def contract_digest(contract: ArchitectureContract) -> str:
    """The digest an amendment binds to (AD-61): the canonical bytes `contract_bytes` writes."""
    return hashlib.sha256(contract_bytes(contract)).hexdigest()


def _without_none(value: object) -> object:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_without_none(item) for item in value]
    return value


def _parse_capability(raw: RawJson, label: str) -> ContractCapability:
    item, item_id, provenance = _contract_record(
        raw, {"name", "label", "review_order"}, set(), label
    )
    order = item["review_order"]
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise ValueError(f"{label}.review_order must be a positive integer")
    name = _nonempty(item["name"], f"{label}.name")
    title = _nonempty(item["label"], f"{label}.label")
    return ContractCapability(item_id, name, title, order, provenance)


def _parse_compat(raw: RawJson, label: str) -> CompatibilityShim:
    item = _contract_fields(raw, {"module", "target", "lifetime"}, set(), label)
    module = _string(item["module"], f"{label}.module")
    target = _string(item["target"], f"{label}.target")
    if _PACKAGE_NAME.fullmatch(module) is None:
        raise ValueError(f"{label}.module must be a dotted module name")
    if _PACKAGE_NAME.fullmatch(target) is None:
        raise ValueError(f"{label}.target must be a dotted module name")
    if module == target:
        raise ValueError(f"{label}.module and target must differ")
    lifetime = item["lifetime"]
    if not _is_compatibility_lifetime(lifetime):
        raise ValueError(f"{label}.lifetime must be permanent or migration")
    return CompatibilityShim(module, target, lifetime)


def _public_entry(value: str, label: str) -> str:
    if _PUBLIC_ENTRY.fullmatch(value) is None:
        raise ValueError(f"{label} must be pkg.module or pkg.module:Name")
    return value


def _required_component(raw: RawJson, label: str) -> RequiredComponent:
    item = _contract_fields(raw, {"component", "rationale"}, {"through", "decided_by"}, label)
    decided_by = item.get("decided_by")
    return RequiredComponent(
        _nonempty(item["component"], f"{label}.component"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        _contract_strings(item.get("through", []), f"{label}.through"),
        _decided_by(decided_by, f"{label}.decided_by") if decided_by is not None else None,
    )


def _parse_component(raw: RawJson, label: str) -> ContractComponent:
    item, item_id, provenance = _contract_record(
        raw,
        {"label", "role", "packages", "responsibilities", "forbidden_responsibilities"},
        {
            "capability_id",
            "decided_by",
            "inside",
            "planned",
            "public",
            "requires",
            "namespace",
        },
        label,
    )
    try:
        role = ComponentRole(_string(item["role"], f"{label}.role"))
    except ValueError as exc:
        raise ValueError(f"{label}.role is invalid") from exc
    capability = item.get("capability_id")
    public_raw = item.get("public")
    public = (
        tuple(
            _public_entry(value, f"{label}.public[{index}]")
            for index, value in enumerate(_contract_strings(public_raw, f"{label}.public"))
        )
        if public_raw is not None
        else None
    )
    planned_raw = item.get("planned")
    planned = (
        tuple(
            _public_entry(value, f"{label}.planned[{index}]")
            for index, value in enumerate(_contract_strings(planned_raw, f"{label}.planned"))
        )
        if planned_raw is not None
        else None
    )
    requires_raw = item.get("requires")
    if requires_raw is not None and not isinstance(requires_raw, list):
        raise ValueError(f"{label}.requires must be a list")
    requires = (
        tuple(
            _required_component(value, f"{label}.requires[{index}]")
            for index, value in enumerate(requires_raw)
        )
        if requires_raw is not None
        else None
    )
    inside = item.get("inside")
    decided_by = item.get("decided_by")
    packages = _contract_strings(item["packages"], f"{label}.packages", required=True)
    namespace_raw = item.get("namespace")
    namespace = (
        _nonempty(namespace_raw, f"{label}.namespace") if namespace_raw is not None else None
    )
    if namespace is not None and _PACKAGE_NAME.fullmatch(namespace) is None:
        raise ValueError(f"{label}.namespace must be a dotted Python package")
    if namespace is not None and namespace not in packages:
        raise ValueError(f"{label}.namespace must name one of {label}.packages")
    return ContractComponent(
        item_id,
        _nonempty(item["label"], f"{label}.label"),
        role,
        packages,
        _contract_strings(item["responsibilities"], f"{label}.responsibilities"),
        _contract_strings(
            item["forbidden_responsibilities"], f"{label}.forbidden_responsibilities"
        ),
        provenance,
        _nonempty(capability, f"{label}.capability_id") if capability is not None else None,
        requires,
        _nonempty(inside, f"{label}.inside") if inside is not None else None,
        public,
        planned,
        _decided_by(decided_by, f"{label}.decided_by") if decided_by is not None else None,
        namespace,
    )


def _parse_review_scope(raw: RawJson, label: str) -> ContractReviewScope:
    item, item_id, provenance = _contract_record(
        raw, {"label", "parent_id", "subjects"}, set(), label
    )
    title = _nonempty(item["label"], f"{label}.label")
    parent_id = _nonempty(item["parent_id"], f"{label}.parent_id")
    subjects = _contract_strings(item["subjects"], f"{label}.subjects", required=True)
    return ContractReviewScope(item_id, title, parent_id, subjects, provenance)


def _parse_command(raw: RawJson, label: str) -> ContractCommand:
    item, item_id, provenance = _contract_record(raw, {"command", "description"}, set(), label)
    command = _nonempty(item["command"], f"{label}.command")
    description = _nonempty(item["description"], f"{label}.description")
    return ContractCommand(item_id, command, description, provenance)


def _parse_contract_path(raw: RawJson, label: str) -> ContractPath:
    item, item_id, provenance = _contract_record(raw, {"label", "kind", "steps"}, set(), label)
    try:
        kind = ContractPathKind(_string(item["kind"], f"{label}.kind"))
    except ValueError as exc:
        raise ValueError(f"{label}.kind is invalid") from exc
    title = _nonempty(item["label"], f"{label}.label")
    steps = _contract_strings(item["steps"], f"{label}.steps", required=True)
    return ContractPath(item_id, title, kind, steps, provenance)


def _parse_owner(raw: RawJson, label: str) -> ContractOwner:
    item, item_id, provenance = _contract_record(
        raw, {"label", "owner", "responsibility"}, set(), label
    )
    title = _nonempty(item["label"], f"{label}.label")
    owner = _nonempty(item["owner"], f"{label}.owner")
    responsibility = _nonempty(item["responsibility"], f"{label}.responsibility")
    return ContractOwner(item_id, title, owner, responsibility, provenance)


def _parse_measurement_budget(raw: RawJson, label: str) -> ContractMeasurementBudget:
    item = _contract_fields(raw, {"name", "provenance"}, set(), label)
    return ContractMeasurementBudget(
        _measurement_budget_name(item["name"], f"{label}.name"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _parse_facade_budget(raw: RawJson, label: str) -> FacadeBudget:
    item = _contract_fields(raw, {"component", "max_names", "provenance"}, set(), label)
    return FacadeBudget(
        _nonempty(item["component"], f"{label}.component"),
        _count(item["max_names"], f"{label}.max_names"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _parse_coupling_budget(raw: RawJson, label: str) -> CouplingBudget:
    item = _contract_fields(raw, {"source", "target", "max_names", "provenance"}, set(), label)
    return CouplingBudget(
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _count(item["max_names"], f"{label}.max_names"),
        _contract_strings(item["provenance"], f"{label}.provenance", required=True),
    )


def _budget_component(public: dict[str, bool], label: str, component: str, *, facade: bool) -> None:
    if component not in public:
        raise ValueError(f"contract.declarations.{label} names no component: {component!r}")
    if facade and not public[component]:
        raise ValueError(f"contract.declarations.{label} {component!r} declares no public facade")


def _check_interface_budgets(
    components: tuple[ContractComponent, ...],
    rules: tuple[ArchitectureRule, ...],
    facades: tuple[FacadeBudget, ...],
    pairs: tuple[CouplingBudget, ...],
) -> None:
    """AD-99: a budget counts a declared facade, so an unknown key is an error, not a PASS.

    A pair counts only names its source reaches through the target's facade. An import past
    the facade, `TYPE_CHECKING` ones included, must therefore be an `interface_boundary`
    finding instead, or the budget would pass on names it never saw.
    """
    public = {item.label: item.public is not None for item in components}
    if pairs and not any(
        isinstance(rule, InterfaceBoundaryRule) and rule.include_type_checking for rule in rules
    ):
        raise ValueError(
            "contract.declarations.coupling_budgets need an interface_boundary rule that "
            "includes TYPE_CHECKING imports, or an import past the facade is counted nowhere"
        )
    for index, budget in enumerate(facades):
        _budget_component(
            public, f"facade_budgets[{index}].component", budget.component, facade=True
        )
    for index, pair in enumerate(pairs):
        _budget_component(public, f"coupling_budgets[{index}].source", pair.source, facade=False)
        _budget_component(public, f"coupling_budgets[{index}].target", pair.target, facade=True)
        if pair.source == pair.target:
            raise ValueError(
                f"contract.declarations.coupling_budgets[{index}] names one component twice"
            )
    for key, subjects in (
        ("facade_budgets", [item.subject for item in facades]),
        ("coupling_budgets", [item.subject for item in pairs]),
    ):
        repeated = sorted({subject for subject in subjects if subjects.count(subject) > 1})
        if repeated:
            raise ValueError(f"contract.declarations.{key} repeats {repeated[0]!r}")


def _parse_forbidden_dependency(raw: RawJson, label: str) -> ForbiddenDependencyRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "include_type_checking", "rationale", "decided_by"},
        {"target_symbol", "allowed_sources"},
        label,
    )
    if item["kind"] != "forbidden_dependency":
        raise ValueError(f"{label}.kind is unsupported")
    include = item["include_type_checking"]
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    symbol = item.get("target_symbol")
    if symbol is not None and (not isinstance(symbol, str) or not symbol.isidentifier()):
        raise ValueError(f"{label}.target_symbol must be a Python identifier")
    source = _nonempty(item["source"], f"{label}.source")
    target = _nonempty(item["target"], f"{label}.target")
    rationale = _nonempty(item["rationale"], f"{label}.rationale")
    decided_by = _decided_by(item["decided_by"], f"{label}.decided_by")
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    return ForbiddenDependencyRule(
        item_id,
        "forbidden_dependency",
        source,
        target,
        include,
        rationale,
        provenance,
        decided_by,
        symbol,
        allowed,
    )


def _parse_allowed_dependency(raw: RawJson, label: str) -> AllowedDependencyRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "target", "rationale", "decided_by"}, set(), label
    )
    if item["kind"] != "allowed_dependency":
        raise ValueError(f"{label}.kind is unsupported")
    return AllowedDependencyRule(
        item_id,
        "allowed_dependency",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["target"], f"{label}.target"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_forbidden_construct(raw: RawJson, label: str) -> ForbiddenConstructRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "constructs", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    raw_constructs = _contract_strings(item["constructs"], f"{label}.constructs", required=True)
    try:
        constructs = tuple(ForbiddenConstructKind(value) for value in raw_constructs)
    except ValueError as exc:
        raise ValueError(f"{label}.constructs contains an unsupported construct") from exc
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    return ForbiddenConstructRule(
        item_id,
        "forbidden_construct",
        _nonempty(item["source"], f"{label}.source"),
        constructs,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
    )


def _parse_external_dependency_scope(raw: RawJson, label: str) -> ExternalDependencyScopeRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "dependency", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    dependency = _nonempty(item["dependency"], f"{label}.dependency")
    if not dependency.isidentifier():
        raise ValueError(f"{label}.dependency must be a top-level import name")
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    if not allowed and not exact:
        raise ValueError(f"{label} must name allowed_sources or exact_sources")
    return ExternalDependencyScopeRule(
        item_id,
        "external_dependency_scope",
        dependency,
        allowed,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        exact,
    )


def _parse_complete_assignment(raw: RawJson, label: str) -> CompleteAssignmentRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "rationale", "decided_by"}, set(), label
    )
    return CompleteAssignmentRule(
        item_id,
        "complete_assignment",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_root_layout(raw: RawJson, label: str) -> RootLayoutRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "root", "allowed_children", "rationale", "decided_by"}, set(), label
    )
    root = _nonempty(item["root"], f"{label}.root")
    allowed_children = _contract_strings(item["allowed_children"], f"{label}.allowed_children")
    root_length = len(root)
    for index, child in enumerate(allowed_children):
        if (
            len(child) <= root_length + 1
            or child[:root_length] != root
            or child[root_length] != "."
            or any(part == "." for part in child[root_length + 1 :])
        ):
            raise ValueError(
                f"{label}.allowed_children[{index}] must be exactly one immediate child "
                f"of {label}.root"
            )
    return RootLayoutRule(
        item_id,
        "root_layout",
        root,
        allowed_children,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_complete_external_scope(raw: RawJson, label: str) -> CompleteExternalScopeRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "rationale", "decided_by"}, set(), label
    )
    return CompleteExternalScopeRule(
        item_id,
        "complete_external_scope",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
    )


def _parse_complete_requires(raw: RawJson, label: str) -> CompleteRequiresRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return CompleteRequiresRule(
        item_id,
        "complete_requires",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
    )


def _cycle_level(raw: RawJson, label: str) -> Literal["module"] | None:
    """Narrow to the Literal by value; the default component level parses to absent (AD-98)."""
    value = _nonempty(raw, label)
    if value == "component":
        return None
    if value == "module":
        return "module"
    raise ValueError(f"{label} must be component or module")


def _parse_no_component_cycles(raw: RawJson, label: str) -> NoComponentCyclesRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"level", "components"}, label
    )
    level = item.get("level")
    components = item.get("components")
    return NoComponentCyclesRule(
        item_id,
        "no_component_cycles",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        _cycle_level(level, f"{label}.level") if level is not None else None,
        _contract_strings(components, f"{label}.components", required=True)
        if components is not None
        else None,
    )


def _parse_interface_boundary(raw: RawJson, label: str) -> InterfaceBoundaryRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return InterfaceBoundaryRule(
        item_id,
        "interface_boundary",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
    )


def _parse_sibling_isolation(raw: RawJson, label: str) -> SiblingIsolationRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "members", "rationale", "decided_by"}, {"include_type_checking"}, label
    )
    members = _contract_strings(item["members"], f"{label}.members", required=True)
    if len(members) < 2:
        raise ValueError(f"{label}.members must name at least two peers")
    include = item.get("include_type_checking", True)
    if not isinstance(include, bool):
        raise ValueError(f"{label}.include_type_checking must be a boolean")
    return SiblingIsolationRule(
        item_id,
        "sibling_isolation",
        members,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        include,
    )


def _parse_symbol_placement(raw: RawJson, label: str) -> SymbolPlacementRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "class_kinds", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources"},
        label,
    )
    raw_kinds = _contract_strings(item["class_kinds"], f"{label}.class_kinds", required=True)
    try:
        class_kinds = tuple(SymbolClassKind(value) for value in raw_kinds)
    except ValueError as exc:
        raise ValueError(f"{label}.class_kinds contains an unsupported class kind") from exc
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    if not allowed and not exact:
        raise ValueError(f"{label} must name allowed_sources or exact_sources")
    return SymbolPlacementRule(
        item_id,
        "symbol_placement",
        _nonempty(item["source"], f"{label}.source"),
        class_kinds,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
    )


def _parse_boundary_types(raw: RawJson, label: str) -> BoundaryTypesRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "rationale", "decided_by"},
        {"allowed_sources", "exact_sources", "allowed_positions"},
        label,
    )
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    exact = _contract_strings(item.get("exact_sources", []), f"{label}.exact_sources")
    raw_positions = item.get("allowed_positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError(f"{label}.allowed_positions must be an array")
    positions: list[BoundaryTypeAllowance] = []
    for index, value in enumerate(raw_positions):
        entry_label = f"{label}.allowed_positions[{index}]"
        entry = _exact(
            value, {"qualified_name", "position", "field_path", "annotation"}, entry_label
        )
        qualified_name = _nonempty(entry["qualified_name"], f"{entry_label}.qualified_name")
        position = _nonempty(entry["position"], f"{entry_label}.position")
        field_path = _nonempty(entry["field_path"], f"{entry_label}.field_path")
        annotation = _nonempty(entry["annotation"], f"{entry_label}.annotation")
        if annotation == "dict":
            raise ValueError(f"{entry_label}.annotation cannot allow bare dict")
        positions.append(BoundaryTypeAllowance(qualified_name, position, field_path, annotation))
    if len(set(positions)) != len(positions):
        raise ValueError(f"{label}.allowed_positions must contain unique entries")
    return BoundaryTypesRule(
        item_id,
        "boundary_types",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
        _decided_by(item["decided_by"], f"{label}.decided_by"),
        allowed,
        exact,
        tuple(positions),
    )


_RULE_PARSERS: Final[dict[str, Callable[[RawJson, str], ArchitectureRule]]] = {
    "forbidden_dependency": _parse_forbidden_dependency,
    "allowed_dependency": _parse_allowed_dependency,
    "forbidden_construct": _parse_forbidden_construct,
    "external_dependency_scope": _parse_external_dependency_scope,
    "complete_assignment": _parse_complete_assignment,
    "root_layout": _parse_root_layout,
    "complete_external_scope": _parse_complete_external_scope,
    "complete_requires": _parse_complete_requires,
    "no_component_cycles": _parse_no_component_cycles,
    "interface_boundary": _parse_interface_boundary,
    "sibling_isolation": _parse_sibling_isolation,
    "symbol_placement": _parse_symbol_placement,
    "boundary_types": _parse_boundary_types,
}


def _parse_rule(raw: RawJson, label: str) -> ArchitectureRule:
    kind = _object(raw, label).get("kind")
    if not isinstance(kind, str) or kind not in _RULE_PARSERS:
        raise ValueError(f"{label}.kind is unsupported")
    return _RULE_PARSERS[kind](raw, label)


def _count(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


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
    delta_status = cv["status"]
    baseline_status = cv["baseline_status"]
    head_status = cv["head_status"]
    if not _is_verdict(delta_status):
        raise ValueError("delta coverage status invalid")
    if not _is_verdict(baseline_status):
        raise ValueError("delta coverage status invalid")
    if not _is_verdict(head_status):
        raise ValueError("delta coverage status invalid")
    dimensions_raw = _object(item["dimensions"], "delta.dimensions")
    dimensions = tuple(
        _parse_dimension(name, raw_dimension)
        for name, raw_dimension in sorted(dimensions_raw.items())
    )
    ratchets = _parse_ratchets(item["ratchets"])
    semantic_changes_raw = item["semantic_changes"]
    unknowns_raw = item["unknowns"]
    if not isinstance(semantic_changes_raw, list) or not isinstance(unknowns_raw, list):
        raise ValueError("semantic_changes and unknowns must be arrays")
    changes = tuple(
        _parse_semantic_change(value, index) for index, value in enumerate(semantic_changes_raw)
    )
    unknowns = tuple(_parse_delta_unknown(value) for value in unknowns_raw)
    return ArchitectureDelta(
        _string(item["schema_version"], "schema_version"),
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
        _parse_snapshot_summary(item["baseline"], "delta.baseline"),
        _parse_snapshot_summary(item["head"], "delta.head"),
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


def _parse_snapshot_summary(raw: RawJson, label: str) -> SnapshotSummary:
    x = _object(raw, label)
    if set(x) - {"python_version"} != {"git_head", "source_digest", "coverage_status"}:
        raise ValueError(f"{label} fields mismatch")
    coverage_status = x["coverage_status"]
    if not _is_verdict(coverage_status):
        raise ValueError(f"{label}.coverage_status invalid")
    return SnapshotSummary(
        _string(x["git_head"], f"{label}.git_head"),
        _string(x["source_digest"], f"{label}.source_digest"),
        coverage_status,
        _python_version(x["python_version"]) if "python_version" in x else None,
    )


def _parse_dimension(name: str, raw: RawJson) -> DimensionDelta:
    label = f"dimensions.{name}"
    dimension = _exact(
        raw,
        {"status", "before_count", "after_count", "added", "removed", "relocated", "changed"},
        label,
    )
    status = dimension["status"]
    if not _is_comparison_status(status):
        raise ValueError(f"{label}.status invalid")
    return DimensionDelta(
        name,
        status,
        _count(dimension["before_count"], f"{label}.before_count"),
        _count(dimension["after_count"], f"{label}.after_count"),
        _strings(dimension["added"], f"{label}.added"),
        _strings(dimension["removed"], f"{label}.removed"),
        _strings(dimension["relocated"], f"{label}.relocated"),
        _strings(dimension["changed"], f"{label}.changed"),
    )


def _parse_ratchets(raw: object) -> RatchetObservations:
    ratchet_raw = _object(raw, "delta.ratchets")
    if ratchet_raw.get("status") == "SUPPORTED":
        if set(ratchet_raw) != {"status", "baseline", "head"}:
            raise ValueError("supported regression check fields mismatch")
        return RatchetObservations(
            "SUPPORTED",
            parse_measurements(ratchet_raw["baseline"], "ratchets.baseline"),
            parse_measurements(ratchet_raw["head"], "ratchets.head"),
        )
    if ratchet_raw.get("status") == "UNKNOWN":
        if set(ratchet_raw) != {"status", "reason"}:
            raise ValueError("unknown regression check fields mismatch")
        return RatchetObservations(
            "UNKNOWN", reason=_string(ratchet_raw.get("reason"), "ratchets.reason")
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
    if unknown["evidence_class"] != "UNKNOWN":
        raise ValueError("unknown.evidence_class invalid")
    return DeltaUnknown(
        _string(unknown["id"], "unknown.id"),
        _string(unknown["dimension"], "unknown.dimension"),
        _string(unknown["reason"], "unknown.reason"),
    )


def _rule_payload(rule: ArchitectureRule) -> dict[str, RawJson]:
    return {key: value for key, value in _raw_object(asdict(rule)).items() if value is not None}


def _open_decision_payload(decision: OpenDecision) -> dict[str, RawJson]:
    return {
        "source": decision.source,
        "target": decision.target,
        "source_package": decision.source_package,
        "target_package": decision.target_package,
        "observed": decision.observed,
        "import_sites": decision.import_sites,
        "options": {
            "allowed_dependency": _rule_payload(decision.allowed_option),
            "forbidden_dependency": _rule_payload(decision.forbidden_option),
        },
    }


def result_payload(result: RunResult) -> dict[str, RawJson]:
    payload = _raw_object(asdict(result))
    payload["diagnostics"] = [
        {
            key: value
            for key, value in _raw_object(asdict(diagnostic)).items()
            if key not in {"pointer", "code"} or value is not None
        }
        for diagnostic in result.diagnostics
    ]
    payload["open_decisions"] = [
        _open_decision_payload(decision) for decision in result.open_decisions
    ]
    # report_filter needs no rebuild: it holds no RecordData, so asdict's own recursion (null
    # when unset) already matches every other optional RunResult field's JSON shape.
    if result.filtered_violations is not None:
        payload["filtered_violations"] = [
            _record_payload(record) for record in result.filtered_violations
        ]
    if result.observation is not None:
        payload["observation"] = observation_payload(result.observation)
    if result.coverage is not None:
        payload["coverage"] = _coverage_payload(result.coverage)
    if result.delta is not None:
        payload["delta"] = delta_payload(result.delta)
    return payload


def result_bytes(result: RunResult) -> bytes:
    return canonical_json_bytes(result_payload(result))


def _measured(scalars: dict[str, RawJson], key: str, label: str) -> int:
    return count(scalars.get(key, 0), f"{label}.{key}")


def _optional(scalars: dict[str, RawJson], key: str, label: str) -> int | None:
    # AD-97: a scalar the profile does not measure is null, and stays null, never 0.
    return None if scalars.get(key, 0) is None else _measured(scalars, key, label)


def parse_measurements(raw: object, label: str) -> Measurements:
    value = _object(raw, label)
    if set(value) != {"scalars", "calls_total", "resolution"}:
        raise RatchetError(f"{label} measurement fields mismatch")
    scalars = _object(value.get("scalars"), f"{label}.scalars")
    scalar_keys = set(SCALARS)
    # Each scalar added later reads as 0 from the payloads written before it existed.
    before_unknown_positions = scalar_keys - {"unknown_positions"}
    before_untyped_private_accesses = before_unknown_positions - {"untyped_private_accesses"}
    if set(scalars) not in (scalar_keys, before_unknown_positions, before_untyped_private_accesses):
        raise RatchetError(f"{label}.scalars must contain exactly {SCALARS}")
    counts = RatchetScalars(
        violations=_measured(scalars, "violations", label),
        cycle_edges=_measured(scalars, "cycle_edges", label),
        private_crossings=_optional(scalars, "private_crossings", label),
        typing_positions=_optional(scalars, "typing_positions", label),
        calls_unresolved=_optional(scalars, "calls_unresolved", label),
        coverage_failures=_measured(scalars, "coverage_failures", label),
        untyped_private_accesses=_optional(scalars, "untyped_private_accesses", label),
        unknown_positions=_measured(scalars, "unknown_positions", label),
    )
    total = count(value.get("calls_total"), f"{label}.calls_total")
    if total:
        if value.get("resolution") != "measured":
            raise RatchetError(f"{label}.resolution must be measured")
        return Measurements(counts, total, "measured")
    if value.get("resolution") != "n/a":
        raise RatchetError(f"{label}.resolution must be n/a")
    return Measurements(counts, total, "n/a")


def parse_lock(payload: bytes) -> AcceptedLock:
    try:
        raw = _exact(
            decode_json(payload),
            {
                "schema_version",
                "accepted_commit",
                "observation_digest",
                "config_digest",
                "checker_digest",
                "measurements",
                "approval_ref",
            },
            "accepted lock",
        )
        if raw["schema_version"] != "1.0.0":
            raise ValueError("invalid accepted lock schema")
        digests: dict[str, str] = {}
        for key, size in (
            ("accepted_commit", 40),
            ("observation_digest", 64),
            ("config_digest", 64),
            ("checker_digest", 64),
        ):
            value = raw[key]
            if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{size}}}", value) is None:
                raise ValueError(f"invalid lock {key}")
            digests[key] = value
        approval_ref = _string(raw["approval_ref"], "approval_ref")
        if not approval_ref.strip():
            raise ValueError("accepted lock needs an opaque approval_ref")
        return AcceptedLock(
            digests["accepted_commit"],
            digests["observation_digest"],
            digests["config_digest"],
            digests["checker_digest"],
            parse_measurements(raw["measurements"], "accepted"),
            approval_ref,
        )
    except (ValueError, TypeError, KeyError) as error:
        raise LockError(str(error)) from error


def contract_provenance_paths(contract: ArchitectureContract) -> tuple[str, ...]:
    """Return every repository path cited as contract provenance."""
    declarations = contract.declarations or ContractDeclarations()
    paths = {
        *declarations.public_api_provenance,
        *declarations.context_roots_provenance,
    }
    for records in (
        contract.components,
        contract.rules,
        declarations.capabilities,
        declarations.review_scopes,
        declarations.public_commands,
        declarations.paths,
        declarations.spot_owners,
        declarations.measurement_budgets,
        declarations.facade_budgets or (),
        declarations.coupling_budgets or (),
    ):
        for record in records:
            paths.update(record.provenance)
    return tuple(sorted(paths))


def declaration_paths(payload: bytes, contract_path: str) -> tuple[str, ...]:
    """Every repository path a contract's declarations are read from, the insides included.

    A `check` snapshot that left the inside contracts behind would observe the level above
    while the lock was written over both, so the two could never agree (AD-36). The same
    filter `report` applies decides which insides count, so both commands skip the same ones.
    """
    contract = parse_contract(decode_json(payload))
    inside = {
        component.inside
        for component in contract.components
        if component.inside is not None and contract_relative_path(component.inside) is not None
    }
    return tuple(sorted({contract_path, *inside, *contract_provenance_paths(contract)}))


def _record_payload(value: Record) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result


def _known_violation(raw: RawJson, label: str, *, with_roles: bool) -> KnownViolation:
    fields = {"rules", "subjects", "count"}
    value = _object(raw, label)
    if with_roles and set(value) not in (fields, fields | {"roles"}):
        raise ValueError(f"{label} fields mismatch")
    if not with_roles and set(value) != fields:
        raise ValueError(f"{label} fields mismatch")
    occurrences = count(value["count"], f"{label}.count")
    if not occurrences:
        raise ValueError(f"{label}.count must be at least 1")
    roles: tuple[tuple[str, str], ...] = ()
    if with_roles and "roles" in value:
        raw_roles = value["roles"]
        if not isinstance(raw_roles, list):
            raise ValueError(f"{label}.roles must be an array")
        parsed_roles = []
        for index, raw_role in enumerate(raw_roles):
            role = _exact(raw_role, {"source", "target"}, f"{label}.roles[{index}]")
            parsed_roles.append(
                (
                    _string(role["source"], f"{label}.roles[{index}].source"),
                    _string(role["target"], f"{label}.roles[{index}].target"),
                )
            )
        if len(set(parsed_roles)) != len(parsed_roles):
            raise ValueError(f"{label}.roles repeats a role")
        roles = tuple(sorted(parsed_roles))
    return KnownViolation(
        canonical_fingerprint(
            _strings(value["rules"], f"{label}.rules"),
            _strings(value["subjects"], f"{label}.subjects"),
        ),
        occurrences,
        roles,
    )


def _measurement_budget_name(raw: object, label: str) -> MeasurementBudgetName:
    value = _string(raw, label)
    if value == "cycle_edges":
        return "cycle_edges"
    if value == "private_crossings":
        return "private_crossings"
    if value == "typing_positions":
        return "typing_positions"
    if value == "calls_unresolved":
        return "calls_unresolved"
    if value == "untyped_private_accesses":
        return "untyped_private_accesses"
    if value == "unknown_positions":
        return "unknown_positions"
    raise ValueError(f"{label} is not a supported measurement budget")


def _name_budget_kind(raw: str) -> NameBudgetKind | None:
    if raw == "facade_names":
        return "facade_names"
    if raw == "coupling_names":
        return "coupling_names"
    return None


def _name_budgets(kind: NameBudgetKind, raw: RawJson, label: str) -> list[MeasurementBudget]:
    """One budget per facade or pair key and its accepted names (AD-99)."""
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    budgets = []
    for key, names in sorted(raw.items()):
        accepted = _strings(names, f"{label}.{key}")
        if list(accepted) != sorted(set(accepted)):
            raise ValueError(f"{label}.{key} must list sorted unique names")
        budgets.append(MeasurementBudget(kind, len(accepted), _nonempty(key, label), accepted))
    return budgets


def parse_validation_baseline(raw: object) -> ValidationBaseline:
    """Read the violation and measurement-budget baseline written by validate."""
    untyped = _object(raw, "baseline")
    schema_version = untyped.get("schema_version")
    versions = {
        LEGACY_BASELINE_SCHEMA_VERSION,
        ROLES_BASELINE_SCHEMA_VERSION,
        SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION,
        BASELINE_SCHEMA_VERSION,
    }
    with_budgets = {SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION, BASELINE_SCHEMA_VERSION}
    if schema_version not in versions:
        raise ValueError(
            f"baseline schema {schema_version!r} cannot be read as {', '.join(sorted(versions))}"
        )
    fields = {"schema_version", "violations", "budgets"}
    document = _exact(
        untyped,
        fields if schema_version in with_budgets else fields - {"budgets"},
        "baseline",
    )
    entries = document["violations"]
    if not isinstance(entries, list):
        raise ValueError("baseline.violations must be an array")
    violations = tuple(
        _known_violation(
            entry,
            f"baseline.violations[{index}]",
            with_roles=schema_version != LEGACY_BASELINE_SCHEMA_VERSION,
        )
        for index, entry in enumerate(entries)
    )
    if len({item.fingerprint for item in violations}) != len(violations):
        raise ValueError("baseline.violations repeats a fingerprint; give it one count instead")
    ordered = tuple(
        sorted(violations, key=lambda item: (item.fingerprint.rules, item.fingerprint.subjects))
    )
    raw_budgets = document.get("budgets", {})
    if not isinstance(raw_budgets, dict) or not all(isinstance(name, str) for name in raw_budgets):
        raise ValueError("baseline.budgets must be an object")
    budgets: list[MeasurementBudget] = []
    for name, value in sorted(raw_budgets.items()):
        label = f"baseline.budgets.{name}"
        kind = _name_budget_kind(name) if schema_version == BASELINE_SCHEMA_VERSION else None
        if kind is not None:
            budgets.extend(_name_budgets(kind, value, label))
        else:
            budgets.append(
                MeasurementBudget(_measurement_budget_name(name, label), count(value, label))
            )
    return ValidationBaseline(ordered, tuple(budgets))


def parse_baseline(raw: object) -> tuple[KnownViolation, ...]:
    """Read known violations for callers that do not consume measurement budgets."""
    return parse_validation_baseline(raw).violations


def _budgets_payload(budgets: tuple[MeasurementBudget, ...]) -> dict[str, RawJson]:
    """Scalars by name; each keyed kind as one object of key to accepted names (AD-99)."""
    payload: dict[str, RawJson] = {}
    keyed: dict[str, dict[str, RawJson]] = {}
    for item in budgets:
        if item.key:
            keyed.setdefault(item.name, {})[item.key] = list(item.names)
        else:
            payload[item.name] = item.value
    return {**payload, **keyed}


def baseline_bytes(
    violations: tuple[KnownViolation, ...], budgets: tuple[MeasurementBudget, ...] = ()
) -> bytes:
    """Write the baseline indented and one entry per line: this file is read in diffs."""
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "budgets": _budgets_payload(budgets),
        "violations": [
            {
                "rules": list(item.fingerprint.rules),
                "subjects": list(item.fingerprint.subjects),
                "count": item.count,
                **(
                    {
                        "roles": [
                            {"source": source, "target": target}
                            for source, target in sorted(item.roles)
                        ]
                    }
                    if item.roles
                    else {}
                ),
            }
            for item in sorted(
                violations, key=lambda item: (item.fingerprint.rules, item.fingerprint.subjects)
            )
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _amendment_digest(raw: RawJson, label: str) -> str:
    value = _string(raw, label)
    if re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def parse_amendment(raw: object) -> Amendment:
    """Read a contract-widening amendment record, ordered like `archkeel validate` writes it."""
    document = _exact(
        raw,
        {"schema_version", "before_digest", "after_digest", "decided_by", "rationale"},
        "amendment",
    )
    if document["schema_version"] != AMENDMENT_SCHEMA_VERSION:
        raise ValueError(
            f"amendment schema {document['schema_version']!r} cannot be read as "
            f"{AMENDMENT_SCHEMA_VERSION}"
        )
    return Amendment(
        _amendment_digest(document["before_digest"], "amendment.before_digest"),
        _amendment_digest(document["after_digest"], "amendment.after_digest"),
        _nonempty(document["decided_by"], "amendment.decided_by"),
        _nonempty(document["rationale"], "amendment.rationale"),
    )


def amendment_bytes(amendment: Amendment) -> bytes:
    """Write the amendment indented and sorted: this file is read and reviewed in diffs."""
    payload = {
        "schema_version": AMENDMENT_SCHEMA_VERSION,
        "before_digest": amendment.before_digest,
        "after_digest": amendment.after_digest,
        "decided_by": amendment.decided_by,
        "rationale": amendment.rationale,
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
