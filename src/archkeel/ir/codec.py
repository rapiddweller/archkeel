# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode validated IR values and preserve the canonical wire representation."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from math import isfinite
from typing import Any, Final, TypeAlias

from archkeel.ir.lock import AcceptedLock, LockError
from archkeel.ir.measurements import SCALARS, Measurements, RatchetError, RatchetScalars, count
from archkeel.ir.model import (
    CLASSIFIED_SECTIONS,
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    AnalyzerInfo,
    ArchitectureContract,
    ArchitectureDelta,
    ArchitectureRule,
    CompleteAssignmentRule,
    ComponentRole,
    ContractCapability,
    ContractCommand,
    ContractComponent,
    ContractDeclarations,
    ContractInfo,
    ContractOwner,
    ContractPath,
    ContractPathKind,
    ContractReviewScope,
    Coverage,
    DeltaCoverage,
    DeltaProvenance,
    DeltaUnknown,
    DimensionDelta,
    Evidence,
    EvidenceClass,
    ExternalDependencyScopeRule,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    JsonValue,
    NoComponentCyclesRule,
    Observation,
    Projection,
    RatchetObservations,
    Record,
    RecordData,
    RunResult,
    Section,
    SemanticChange,
    SnapshotSummary,
    SourceInfo,
)

_STRING_REFERENCE = re.compile(r"^\$\d+$")
_ESCAPED_STRING_REFERENCE = re.compile(r"^\$\$+\d+$")
RawJson: TypeAlias = str | int | float | bool | None | list["RawJson"] | dict[str, "RawJson"]

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
CONTRACT_SCHEMA_VERSION: Final = "2.0.0"


class ContractVersionError(ValueError):
    """The contract declares a schema version this parser cannot interpret."""

    def __init__(self, actual: str) -> None:
        self.actual = actual
        super().__init__(f"contract.schema_version {actual!r} is not {CONTRACT_SCHEMA_VERSION}")


def _object(raw: object, label: str) -> dict[str, Any]:
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
    return Record(
        id=_string(item["id"], f"{label}.id"),
        evidence_class=evidence_class,
        area=_string(item["area"], f"{label}.area"),
        kind=_string(item["kind"], f"{label}.kind"),
        title=_string(item["title"], f"{label}.title"),
        subjects=_strings(item["subjects"], f"{label}.subjects"),
        evidence_ids=_strings(item["evidence_ids"], f"{label}.evidence_ids"),
        rule_ids=_strings(item["rule_ids"], f"{label}.rule_ids"),
        fact_ids=_strings(item["fact_ids"], f"{label}.fact_ids"),
        provenance=_strings(item["provenance"], f"{label}.provenance"),
        data=_data(item["data"], f"{label}.data"),
    )


def parse_evidence(raw: object, label: str = "evidence") -> Evidence:
    item = _object(raw, label)
    if set(item) != _EVIDENCE_KEYS:
        raise ValueError(f"{label} fields mismatch")
    integers = ("line", "end_line", "column")
    values = {key: item[key] for key in integers}
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values.values()):
        raise ValueError(f"{label} positions must be integers")
    return Evidence(
        id=_string(item["id"], f"{label}.id"),
        file=_string(item["file"], f"{label}.file"),
        line=values["line"],
        end_line=values["end_line"],
        column=values["column"],
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
    if (
        source["dirty"] is not True
        and source["dirty"] is not False
        and source["dirty"] != "unknown"
    ):
        raise ValueError("source.dirty is invalid")
    coverage_keys = {
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
    if set(coverage) - coverage_keys or not {
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
    }.issubset(coverage):
        raise ValueError("coverage fields mismatch")
    if coverage["status"] not in ("PASS", "FAIL") or coverage.get("rules") not in (
        None,
        "PASS",
        "FAIL",
    ):
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
    if any(
        not isinstance(coverage[k], int) or isinstance(coverage[k], bool) or coverage[k] < 0
        for k in counts
    ):
        raise ValueError("coverage counts invalid")
    if any(
        not isinstance(coverage[k], (int, float))
        or isinstance(coverage[k], bool)
        or not isfinite(coverage[k])
        or not 0 <= coverage[k] <= 100
        for k in ("ast_coverage_percent", "call_resolution_percent")
    ):
        raise ValueError("coverage percentages invalid")
    if not isinstance(coverage["failures"], list) or not isinstance(item["evidence"], list):
        raise ValueError("coverage.failures and evidence must be arrays")
    sections = tuple(
        Section(name, tuple(parse_record(value, f"{name}[]") for value in item[name]))
        for name in CLASSIFIED_SECTIONS
        if isinstance(item[name], list)
    )
    if len(sections) != len(CLASSIFIED_SECTIONS):
        raise ValueError("sections must be arrays")
    return Observation(
        schema_version=_string(item["schema_version"], "schema_version"),
        analyzer=AnalyzerInfo(
            *(_string(analyzer[k], f"analyzer.{k}") for k in ("name", "version", "code_digest"))
        ),
        source=SourceInfo(
            _string(source["git_head"], "source.git_head"),
            source["dirty"],
            _string(source["source_digest"], "source.source_digest"),
            _strings(source["scope"], "source.scope"),
        ),
        contract=ContractInfo(
            *(_string(contract[k], f"contract.{k}") for k in ("schema_version", "digest", "path"))
        ),
        coverage=Coverage(
            status=coverage["status"],
            **{k: coverage[k] for k in counts},
            ast_coverage_percent=coverage["ast_coverage_percent"],
            call_resolution_percent=coverage["call_resolution_percent"],
            failures=tuple(parse_record(v, "coverage.failures[]") for v in coverage["failures"]),
            rules=coverage.get("rules"),
        ),
        sections=sections,
        evidence=tuple(parse_evidence(value, "evidence[]") for value in item["evidence"]),
        python_version=_python_version(item["python_version"])
        if "python_version" in item
        else None,
    )


def _python_version(raw: object) -> str:
    value = _string(raw, "python_version")
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[ab][0-9]+|rc[0-9]+)?", value) is None:
        raise ValueError("python_version must be a canonical full Python version")
    return value


def _raw_object(value: dict[str, Any]) -> dict[str, Any]:
    return {key: _raw_value(item) for key, item in value.items()}


def _raw_value(value: Any) -> Any:
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


def observation_payload(observation: Observation) -> dict[str, Any]:
    result = _raw_object(asdict(observation))
    if observation.python_version is None:
        del result["python_version"]
    del result["sections"]
    result["coverage"] = _coverage_payload(observation.coverage)
    result.update(
        {
            section.name: [_record_payload(record) for record in section.records]
            for section in observation.sections
        }
    )
    return result


def canonical_json_bytes(model: dict[str, Any]) -> bytes:
    """Serialize the canonical model without time, locale, or filesystem noise."""
    return (
        json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def encode_canonical_model(model: dict[str, Any]) -> dict[str, Any]:
    """Losslessly columnize and intern repeated IR strings for browser-safe reports."""
    encoded = {
        key: value for key, value in model.items() if key not in {*CLASSIFIED_SECTIONS, "evidence"}
    }
    section_data_fields: dict[str, list[str]] = {}
    rows_by_section: dict[str, list[list[Any]]] = {}
    for section in CLASSIFIED_SECTIONS:
        items = model.get(section, [])
        data_fields = sorted({key for item in items for key in item["data"]})
        section_data_fields[section] = data_fields
        rows_by_section[section] = [
            [
                *(item[field] for field in RECORD_FIELDS[:-1]),
                [item["data"].get(field, _MISSING_VALUE) for field in data_fields],
            ]
            for item in items
        ]
    evidence_rows = [
        [item[field] for field in EVIDENCE_FIELDS] for item in model.get("evidence", [])
    ]

    counts: Counter[str] = Counter()

    def count_strings(value: Any) -> None:
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
    encoded["encoding"] = {
        "kind": "architecture-ir-columnar-v1",
        "record_fields": list(RECORD_FIELDS),
        "evidence_fields": list(EVIDENCE_FIELDS),
        "section_data_fields": section_data_fields,
        "string_reference": "$<index>",
        "escaped_literal": "additional leading $",
    }
    encoded["string_table"] = string_table
    return encoded


def decode_canonical_model(encoded: dict[str, Any]) -> dict[str, Any]:
    """Inflate the canonical columnar report into the in-memory ArchitectureIR."""
    encoding = encoded.get("encoding")
    if not isinstance(encoding, dict) or encoding.get("kind") != "architecture-ir-columnar-v1":
        return encoded
    string_table = encoded["string_table"]

    def expand(value: Any) -> Any:
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

    model = {
        key: value
        for key, value in encoded.items()
        if key not in {*CLASSIFIED_SECTIONS, "evidence", "encoding", "string_table"}
    }
    record_fields = encoding["record_fields"]
    for section in CLASSIFIED_SECTIONS:
        data_fields = encoding["section_data_fields"][section]
        records = []
        for encoded_row in encoded.get(section, []):
            row = expand(encoded_row)
            item = dict(zip(record_fields, row, strict=True))
            item["data"] = {
                key: value
                for key, value in zip(data_fields, item["data"], strict=True)
                if value is not _MISSING_VALUE
            }
            records.append(item)
        model[section] = records
    model["evidence"] = [
        dict(zip(encoding["evidence_fields"], expand(row), strict=True))
        for row in encoded.get("evidence", [])
    ]
    return model


def canonical_report_bytes(model: Observation | dict[str, Any]) -> bytes:
    raw = observation_payload(model) if isinstance(model, Observation) else model
    return canonical_json_bytes(encode_canonical_model(raw))


def _measurement_payload(value: Measurements) -> dict[str, Any]:
    return _raw_object(asdict(value))


def _coverage_payload(value: Coverage) -> dict[str, Any]:
    result = _raw_object(asdict(value))
    result["failures"] = [_record_payload(record) for record in value.failures]
    if value.rules is None:
        del result["rules"]
    return result


def _projection_payload(value: Projection) -> dict[str, Any]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result


def delta_payload(delta: ArchitectureDelta) -> dict[str, Any]:
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


def _exact(value: object, keys: set[str], label: str) -> dict[str, Any]:
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
    rules = tuple(_parse_rule(value, f"rules[{index}]") for index, value in enumerate(rules_raw))
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
        )
        if declarations_raw is not None
        else None,
    )


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


def _parse_component(raw: RawJson, label: str) -> ContractComponent:
    item, item_id, provenance = _contract_record(
        raw,
        {"label", "role", "packages", "responsibilities", "forbidden_responsibilities"},
        {"capability_id"},
        label,
    )
    try:
        role = ComponentRole(_string(item["role"], f"{label}.role"))
    except ValueError as exc:
        raise ValueError(f"{label}.role is invalid") from exc
    capability = item.get("capability_id")
    return ContractComponent(
        item_id,
        _nonempty(item["label"], f"{label}.label"),
        role,
        _contract_strings(item["packages"], f"{label}.packages", required=True),
        _contract_strings(item["responsibilities"], f"{label}.responsibilities"),
        _contract_strings(
            item["forbidden_responsibilities"], f"{label}.forbidden_responsibilities"
        ),
        provenance,
        _nonempty(capability, f"{label}.capability_id") if capability is not None else None,
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


def _parse_forbidden_dependency(raw: RawJson, label: str) -> ForbiddenDependencyRule:
    item, item_id, provenance = _contract_record(
        raw,
        {"kind", "source", "target", "include_type_checking", "rationale"},
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
    allowed = _contract_strings(item.get("allowed_sources", []), f"{label}.allowed_sources")
    return ForbiddenDependencyRule(
        item_id,
        "forbidden_dependency",
        source,
        target,
        include,
        rationale,
        provenance,
        symbol,
        allowed,
    )


def _parse_forbidden_construct(raw: RawJson, label: str) -> ForbiddenConstructRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "source", "constructs", "rationale"}, set(), label
    )
    raw_constructs = _contract_strings(item["constructs"], f"{label}.constructs", required=True)
    try:
        constructs = tuple(ForbiddenConstructKind(value) for value in raw_constructs)
    except ValueError as exc:
        raise ValueError(f"{label}.constructs contains an unsupported construct") from exc
    return ForbiddenConstructRule(
        item_id,
        "forbidden_construct",
        _nonempty(item["source"], f"{label}.source"),
        constructs,
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
    )


def _parse_external_dependency_scope(raw: RawJson, label: str) -> ExternalDependencyScopeRule:
    item, item_id, provenance = _contract_record(
        raw, {"kind", "dependency", "allowed_sources", "rationale"}, set(), label
    )
    dependency = _nonempty(item["dependency"], f"{label}.dependency")
    if not dependency.isidentifier():
        raise ValueError(f"{label}.dependency must be a top-level import name")
    return ExternalDependencyScopeRule(
        item_id,
        "external_dependency_scope",
        dependency,
        _contract_strings(item["allowed_sources"], f"{label}.allowed_sources", required=True),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
    )


def _parse_complete_assignment(raw: RawJson, label: str) -> CompleteAssignmentRule:
    item, item_id, provenance = _contract_record(raw, {"kind", "source", "rationale"}, set(), label)
    return CompleteAssignmentRule(
        item_id,
        "complete_assignment",
        _nonempty(item["source"], f"{label}.source"),
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
    )


def _parse_no_component_cycles(raw: RawJson, label: str) -> NoComponentCyclesRule:
    item, item_id, provenance = _contract_record(raw, {"kind", "rationale"}, set(), label)
    return NoComponentCyclesRule(
        item_id,
        "no_component_cycles",
        _nonempty(item["rationale"], f"{label}.rationale"),
        provenance,
    )


_RULE_PARSERS: Final[dict[str, Callable[[RawJson, str], ArchitectureRule]]] = {
    "forbidden_dependency": _parse_forbidden_dependency,
    "forbidden_construct": _parse_forbidden_construct,
    "external_dependency_scope": _parse_external_dependency_scope,
    "complete_assignment": _parse_complete_assignment,
    "no_component_cycles": _parse_no_component_cycles,
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

    def summary(value: object, label: str) -> SnapshotSummary:
        x = _object(value, label)
        if set(x) - {"python_version"} != {"git_head", "source_digest", "coverage_status"}:
            raise ValueError(f"{label} fields mismatch")
        if x["coverage_status"] not in ("PASS", "FAIL"):
            raise ValueError(f"{label}.coverage_status invalid")
        return SnapshotSummary(
            _string(x["git_head"], f"{label}.git_head"),
            _string(x["source_digest"], f"{label}.source_digest"),
            x["coverage_status"],
            _python_version(x["python_version"]) if "python_version" in x else None,
        )

    c = _exact(item["contract"], {"schema_version", "digest", "path"}, "delta.contract")
    cv = _exact(
        item["coverage"],
        {"status", "baseline_status", "head_status", "supported_dimensions", "unknown_dimensions"},
        "delta.coverage",
    )
    if any(cv[k] not in ("PASS", "FAIL") for k in ("status", "baseline_status", "head_status")):
        raise ValueError("delta coverage status invalid")
    dimensions_raw = _object(item["dimensions"], "delta.dimensions")
    dimensions_list: list[DimensionDelta] = []
    for name, raw_dimension in sorted(dimensions_raw.items()):
        dimension = _exact(
            raw_dimension,
            {"status", "before_count", "after_count", "added", "removed", "relocated", "changed"},
            f"dimensions.{name}",
        )
        status = dimension["status"]
        if status not in ("SUPPORTED", "UNKNOWN"):
            raise ValueError(f"dimensions.{name}.status invalid")
        dimensions_list.append(
            DimensionDelta(
                name,
                status,
                _count(dimension["before_count"], f"dimensions.{name}.before_count"),
                _count(dimension["after_count"], f"dimensions.{name}.after_count"),
                _strings(dimension["added"], f"dimensions.{name}.added"),
                _strings(dimension["removed"], f"dimensions.{name}.removed"),
                _strings(dimension["relocated"], f"dimensions.{name}.relocated"),
                _strings(dimension["changed"], f"dimensions.{name}.changed"),
            )
        )
    dimensions = tuple(dimensions_list)
    ratchet_raw = _object(item["ratchets"], "delta.ratchets")
    if ratchet_raw.get("status") == "SUPPORTED":
        if set(ratchet_raw) != {"status", "baseline", "head"}:
            raise ValueError("supported regression check fields mismatch")
        ratchets = RatchetObservations(
            "SUPPORTED",
            parse_measurements(ratchet_raw["baseline"], "ratchets.baseline"),
            parse_measurements(ratchet_raw["head"], "ratchets.head"),
        )
    elif ratchet_raw.get("status") == "UNKNOWN":
        if set(ratchet_raw) != {"status", "reason"}:
            raise ValueError("unknown regression check fields mismatch")
        ratchets = RatchetObservations(
            "UNKNOWN", reason=_string(ratchet_raw.get("reason"), "ratchets.reason")
        )
    else:
        raise ValueError("delta.ratchets status invalid")
    if not isinstance(item["semantic_changes"], list) or not isinstance(item["unknowns"], list):
        raise ValueError("semantic_changes and unknowns must be arrays")
    changes = []
    for index, value in enumerate(item["semantic_changes"]):
        x = _object(value, f"semantic_changes[{index}]")
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
        changes.append(
            SemanticChange(
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
        )
    unknowns_list: list[DeltaUnknown] = []
    for value in item["unknowns"]:
        unknown = _exact(value, {"id", "dimension", "reason", "evidence_class"}, "unknown")
        if unknown["evidence_class"] != "UNKNOWN":
            raise ValueError("unknown.evidence_class invalid")
        unknowns_list.append(
            DeltaUnknown(
                _string(unknown["id"], "unknown.id"),
                _string(unknown["dimension"], "unknown.dimension"),
                _string(unknown["reason"], "unknown.reason"),
            )
        )
    unknowns = tuple(unknowns_list)
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
        summary(item["baseline"], "delta.baseline"),
        summary(item["head"], "delta.head"),
        ContractInfo(
            _string(c["schema_version"], "contract.schema_version"),
            _string(c["digest"], "contract.digest"),
            _string(c["path"], "contract.path"),
        ),
        DeltaCoverage(
            cv["status"],
            cv["baseline_status"],
            cv["head_status"],
            _strings(cv["supported_dimensions"], "supported_dimensions"),
            _strings(cv["unknown_dimensions"], "unknown_dimensions"),
        ),
        dimensions,
        ratchets,
        tuple(changes),
        unknowns,
    )


def result_payload(result: RunResult) -> dict[str, Any]:
    payload = _raw_object(asdict(result))
    for diagnostic in payload["diagnostics"]:
        if isinstance(diagnostic, dict) and diagnostic.get("pointer") is None:
            diagnostic.pop("pointer")
    if result.observation is not None:
        payload["observation"] = observation_payload(result.observation)
    if result.coverage is not None:
        payload["coverage"] = _coverage_payload(result.coverage)
    if result.delta is not None:
        payload["delta"] = delta_payload(result.delta)
    return payload


def result_bytes(result: RunResult) -> bytes:
    return canonical_json_bytes(result_payload(result))


def parse_measurements(raw: object, label: str) -> Measurements:
    value = _object(raw, label)
    if set(value) != {"scalars", "calls_total", "resolution"}:
        raise RatchetError(f"{label} measurement fields mismatch")
    scalars = _object(value.get("scalars"), f"{label}.scalars")
    if set(scalars) != set(SCALARS):
        raise RatchetError(f"{label}.scalars must contain exactly {SCALARS}")
    counts = {key: count(scalars[key], f"{label}.{key}") for key in SCALARS}
    total = count(value.get("calls_total"), f"{label}.calls_total")
    if total:
        if value.get("resolution") != "measured":
            raise RatchetError(f"{label}.resolution must be measured")
        return Measurements(RatchetScalars(**counts), total, "measured")
    if value.get("resolution") != "n/a":
        raise RatchetError(f"{label}.resolution must be n/a")
    return Measurements(RatchetScalars(**counts), total, "n/a")


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
        for key, size in (
            ("accepted_commit", 40),
            ("observation_digest", 64),
            ("config_digest", 64),
            ("checker_digest", 64),
        ):
            if (
                not isinstance(raw[key], str)
                or re.fullmatch(f"[0-9a-f]{{{size}}}", raw[key]) is None
            ):
                raise ValueError(f"invalid lock {key}")
        approval_ref = _string(raw["approval_ref"], "approval_ref")
        if not approval_ref.strip():
            raise ValueError("accepted lock needs an opaque approval_ref")
        return AcceptedLock(
            raw["accepted_commit"],
            raw["observation_digest"],
            raw["config_digest"],
            raw["checker_digest"],
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
    ):
        for record in records:
            paths.update(record.provenance)
    return tuple(sorted(paths))


def declaration_paths(payload: bytes, contract_path: str) -> tuple[str, ...]:
    contract = parse_contract(decode_json(payload))
    return tuple(sorted({contract_path, *contract_provenance_paths(contract)}))


def _record_payload(value: Record) -> dict[str, Any]:
    result = _raw_object(asdict(value))
    result["data"] = _raw_value(value.data)
    return result
