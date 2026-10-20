# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read observation profiles and their canonical columnar representation."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, replace
from enum import StrEnum
from math import isfinite
from typing import Any, TypeGuard

from archkeel.ir.architecture_graph import ArchitectureRuleKind
from archkeel.ir.codec_wire import (
    _count,
    _exact,
    _has_field,
    _nonempty,
    _object,
    _raw_object,
    _string,
    _strings,
    canonical_json_bytes,
)
from archkeel.ir.facts import (
    CallBindingOrigin,
    RuntimeRequirementState,
    SourceProfile,
    parse_runtime_requirement_state,
    source_dirty,
)
from archkeel.ir.facts import call_binding as _call_binding
from archkeel.ir.model import (
    CLASSIFIED_SECTIONS,
    EVIDENCE_FIELDS,
    RECORD_FIELDS,
    SCHEMA_VERSION,
    AnalyzerInfo,
    ContractInfo,
    Coverage,
    Observation,
    Record,
    RuntimeInfo,
    Section,
    SourceInfo,
    Verdict,
    identity_is_known,
)
from archkeel.ir.model import RawJson as RawJson
from archkeel.ir.profiles import (
    ObservedSection,
    Profile,
    UnmeasurableScalar,
    profile_for,
)

from .facts_codec import parse_evidence as parse_evidence
from .facts_codec import parse_record as parse_record
from .facts_codec import record_payload as _record_payload


class _ObservationVersion(StrEnum):
    V1_2 = "1.2.0"
    V1_3 = "1.3.0"
    V2 = "2.0.0"
    V2_1 = "2.1.0"
    V2_2 = "2.2.0"
    V2_3 = "2.3.0"
    V2_4 = SCHEMA_VERSION


class _VersionedConstruct(StrEnum):
    NUMERIC_OPERAND = "numeric_operand"


def _uses_numeric_operand_fields(record: Record) -> bool:
    return record.kind == _VersionedConstruct.NUMERIC_OPERAND or _has_field(
        (key for key, _ in record.data.entries), "derivation"
    )


class _EncodingKind(StrEnum):
    COLUMNAR = "architecture-ir-columnar-v1"


class _ProtocolResultKind(StrEnum):
    DECLARATION = "protocol_declaration"
    LIMIT = "protocol_declaration_limit"


def _uses_protocol_declaration_fields(section: Section) -> bool:
    return any(
        record.kind
        in {
            ArchitectureRuleKind.PROTOCOL_DECLARATIONS,
            _ProtocolResultKind.DECLARATION,
            _ProtocolResultKind.LIMIT,
        }
        or _has_field((key for key, _ in record.data.entries), "protocol_scope_proof")
        for record in section.records
    )


class _StringSentinel(StrEnum):
    MISSING = "$m"
    ESCAPED_MISSING = "$$m"


def _string_sentinel(value: str) -> _StringSentinel | None:
    if value == _StringSentinel.MISSING:
        return _StringSentinel.MISSING
    if value == _StringSentinel.ESCAPED_MISSING:
        return _StringSentinel.ESCAPED_MISSING
    return None


def _observation_version(value: RawJson) -> _ObservationVersion:
    try:
        return _ObservationVersion(_string(value, "schema_version"))
    except ValueError as error:
        raise ValueError("unsupported observation schema_version") from error


def _is_columnar(value: RawJson) -> TypeGuard[dict[str, RawJson]]:
    if not isinstance(value, dict):
        return False
    kind = value.get("kind")
    if not isinstance(kind, str):
        return False
    try:
        return _EncodingKind(kind) is _EncodingKind.COLUMNAR
    except ValueError:
        return False


_STRING_REFERENCE = re.compile(r"^\$\d+$")


_ESCAPED_STRING_REFERENCE = re.compile(r"^\$\$+\d+$")


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


def _parse_verdict(value: RawJson, label: str) -> Verdict:
    if not isinstance(value, str):
        raise ValueError(f"{label} invalid")
    try:
        return Verdict(value)
    except ValueError as error:
        raise ValueError(f"{label} invalid") from error


def _percent(value: RawJson, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0 <= value <= 100
    ):
        raise ValueError(f"{label} percentages invalid")
    return value


def _validate_versioned_records(
    schema_version: _ObservationVersion, sections: tuple[Section, ...], profile: Profile
) -> None:
    if schema_version in {
        _ObservationVersion.V1_2,
        _ObservationVersion.V1_3,
        _ObservationVersion.V2,
        _ObservationVersion.V2_1,
    } and any(
        _uses_numeric_operand_fields(record)
        for section in sections
        if section.name == ObservedSection.CONSTRUCTS
        for record in section.records
    ):
        raise ValueError("numeric_operand constructs require observation schema 2.2.0")
    if schema_version in {
        _ObservationVersion.V2_1,
        _ObservationVersion.V2_2,
        _ObservationVersion.V2_3,
        _ObservationVersion.V2_4,
    }:
        python_calls = SourceProfile(profile.analyzer) is SourceProfile.PYTHON
        for section in sections:
            if section.name == ObservedSection.CALLS:
                for call in section.records:
                    if python_calls and not _has_field(
                        (key for key, _ in call.data.entries), "call_binding"
                    ):
                        raise ValueError("Python 2.1.0 calls require explicit call_binding or null")
                    binding = _call_binding(call.data.get("call_binding"))
                    if (
                        schema_version is not _ObservationVersion.V2_4
                        and binding is not None
                        and binding.origin
                        not in {CallBindingOrigin.DIRECT, CallBindingOrigin.DECLARED_RECEIVER}
                    ):
                        raise ValueError(
                            "extended call bindings require observation schema 2.4.0"
                        )
    if schema_version in {
        _ObservationVersion.V1_2,
        _ObservationVersion.V1_3,
        _ObservationVersion.V2,
        _ObservationVersion.V2_1,
        _ObservationVersion.V2_2,
    } and any(_uses_protocol_declaration_fields(section) for section in sections):
        raise ValueError("protocol_declarations require observation schema 2.3.0")


def parse_observation(raw: object) -> Observation:
    item = _object(raw, "observation")
    optional = {"python_version", "runtime", "producer"}
    if set(item) - optional != _TOP_LEVEL:
        raise ValueError("observation fields mismatch")
    schema_version = _observation_version(item["schema_version"])
    analyzer = _exact(item["analyzer"], {"name", "version", "code_digest"}, "analyzer")
    source = _exact(item["source"], {"git_head", "dirty", "source_digest", "scope"}, "source")
    contract = _exact(item["contract"], {"schema_version", "digest", "path"}, "contract")
    coverage = _object(item["coverage"], "coverage")
    profile = profile_for(_string(analyzer["name"], "analyzer.name"))
    dirty_raw = source["dirty"]
    if not isinstance(dirty_raw, (bool, str)):
        raise ValueError("source.dirty is invalid")
    dirty_value = source_dirty(dirty_raw)
    coverage_value = _parse_coverage(
        coverage,
        profile,
        calls_measured=item.get("calls") is not None,
    )
    evidence_raw = item["evidence"]
    if not isinstance(evidence_raw, list):
        raise ValueError("coverage.failures and evidence must be arrays")
    _validate_profile_sections(item, profile)
    sections = tuple(
        Section(name, tuple(parse_record(value, f"{name}[]") for value in section_items))
        for name in CLASSIFIED_SECTIONS
        if isinstance(section_items := item[name], list)
    )
    _validate_versioned_records(schema_version, sections, profile)
    return Observation(
        schema_version=schema_version,
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
        if item.get("python_version", _MISSING_VALUE) is not _MISSING_VALUE
        else None,
        runtime=_parse_runtime(
            item["runtime"],
            allow_requirement_state=schema_version
            in {
                _ObservationVersion.V2,
                _ObservationVersion.V2_1,
                _ObservationVersion.V2_2,
                _ObservationVersion.V2_3,
                _ObservationVersion.V2_4,
            },
        )
        if item.get("runtime", _MISSING_VALUE) is not _MISSING_VALUE
        else None,
        producer=_parse_analyzer(item["producer"], "producer")
        if item.get("producer", _MISSING_VALUE) is not _MISSING_VALUE
        else None,
    )


def _parse_analyzer(raw: RawJson, label: str) -> AnalyzerInfo:
    item = _exact(raw, {"name", "version", "code_digest"}, label)
    return AnalyzerInfo(
        *(
            _known_identity(item[key], f"{label}.{key}")
            for key in ("name", "version", "code_digest")
        )
    )


def _known_identity(raw: RawJson, label: str) -> str:
    value = _string(raw, label)
    if not identity_is_known(value):
        raise ValueError(f"{label} must identify a known producer/runtime")
    return value


def _parse_runtime(raw: RawJson, *, allow_requirement_state: bool) -> RuntimeInfo:
    item = _object(raw, "runtime")
    if (
        not allow_requirement_state
        and item.get("requirement_state", _MISSING_VALUE) is not _MISSING_VALUE
    ):
        raise ValueError("runtime.requirement_state requires observation/Delta schema 2.0.0")
    if set(item) - {"name", "version", "required", "requirement_state"} or not {
        "name",
        "version",
    }.issubset(item):
        raise ValueError("runtime fields mismatch")
    requirement_state_raw = _string(
        item.get("requirement_state", "declared"), "runtime.requirement_state"
    )
    requirement_state = parse_runtime_requirement_state(requirement_state_raw)
    return RuntimeInfo(
        _known_identity(item["name"], "runtime.name"),
        _known_identity(item["version"], "runtime.version"),
        _nonempty(item["required"], "runtime.required")
        if item.get("required") is not None
        else None,
        requirement_state,
    )


def _parse_coverage(
    coverage: dict[str, RawJson], profile: Profile, *, calls_measured: bool = True
) -> Coverage:
    if set(coverage) - _COVERAGE_KEYS or not _COVERAGE_REQUIRED_KEYS.issubset(coverage):
        raise ValueError("coverage fields mismatch")
    status = _parse_verdict(coverage["status"], "coverage status/rules")
    raw_rules = coverage.get("rules")
    rules = _parse_verdict(raw_rules, "coverage status/rules") if raw_rules is not None else None
    file_counts = (
        "files_discovered",
        "files_read",
        "files_parsed",
    )
    call_counts = (
        "calls_analyzed",
        "calls_resolved",
        "calls_partially_resolved",
        "calls_unresolved",
    )
    count_values = {k: _count(coverage[k], f"coverage.{k}") for k in file_counts}
    call_values = {
        key: None if coverage[key] is None else _count(coverage[key], f"coverage.{key}")
        for key in call_counts
    }
    call_percent = coverage["call_resolution_percent"]
    if ObservedSection.CALLS in profile.all_optional_sections:
        if not calls_measured:
            if any(value is not None for value in call_values.values()) or call_percent is not None:
                raise ValueError("TypeScript call measurements must be null")
        elif any(value is None for value in call_values.values()) or call_percent is None:
            raise ValueError("TypeScript call measurements are required with a calls section")
    elif UnmeasurableScalar.CALLS_UNRESOLVED not in profile.unmeasured:
        if any(value is None for value in call_values.values()) or call_percent is None:
            raise ValueError("coverage call measurements are required for this profile")
    else:
        # Dart snapshots written before AD-97 used numeric zeros. Read those while new
        # observations use a fully null call group.
        all_null = all(value is None for value in call_values.values()) and call_percent is None
        all_numeric = (
            all(value is not None for value in call_values.values()) and call_percent is not None
        )
        if not (all_null or all_numeric):
            raise ValueError("Dart call measurements must be all null or legacy numeric")
    ast_coverage_percent = _percent(coverage["ast_coverage_percent"], "coverage")
    call_resolution_percent = (
        _percent(call_percent, "coverage") if call_percent is not None else None
    )
    failures_raw = coverage["failures"]
    if not isinstance(failures_raw, list):
        raise ValueError("coverage.failures and evidence must be arrays")
    return Coverage(
        status=status,
        files_discovered=count_values["files_discovered"],
        files_read=count_values["files_read"],
        files_parsed=count_values["files_parsed"],
        calls_analyzed=call_values["calls_analyzed"],
        calls_resolved=call_values["calls_resolved"],
        calls_partially_resolved=call_values["calls_partially_resolved"],
        calls_unresolved=call_values["calls_unresolved"],
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


def _observation_profile(model: Mapping[str, RawJson]) -> Profile:
    analyzer = _object(model.get("analyzer"), "analyzer")
    return profile_for(_string(analyzer.get("name"), "analyzer.name"))


def _validate_profile_sections(model: Mapping[str, RawJson], profile: Profile) -> None:
    for group in profile.optional_section_groups:
        values = [model.get(section, _MISSING_VALUE) for section in group]
        if any(value is None for value in values):
            for value in values:
                if isinstance(value, list):
                    raise ValueError("optional profile sections must be all null or all arrays")
    for section in CLASSIFIED_SECTIONS:
        raw = model.get(section, _MISSING_VALUE)
        if section in profile.absent_sections:
            if raw is None:
                continue
            raise ValueError(f"{section} must be null for analyzer {profile.analyzer}")
        if section in profile.all_optional_sections and raw is None:
            continue
        if not isinstance(raw, list):
            raise ValueError(f"{section} must be an array for analyzer {profile.analyzer}")


def observation_payload(observation: Observation) -> dict[str, RawJson]:
    if (
        _observation_version(observation.schema_version)
        not in {
            _ObservationVersion.V2,
            _ObservationVersion.V2_1,
            _ObservationVersion.V2_2,
            _ObservationVersion.V2_3,
        }
        and observation.runtime is not None
        and observation.runtime.requirement_state != RuntimeRequirementState.DECLARED
    ):
        raise ValueError("runtime.requirement_state requires observation schema 2.0.0")
    result = _raw_object(
        asdict(
            replace(observation, sections=(), coverage=replace(observation.coverage, failures=()))
        )
    )
    if observation.python_version is None:
        del result["python_version"]
    if observation.runtime is None:
        del result["runtime"]
    else:
        runtime = result["runtime"]
        if isinstance(runtime, dict):
            if observation.runtime.required is None:
                del runtime["required"]
            if observation.runtime.requirement_state == RuntimeRequirementState.DECLARED:
                del runtime["requirement_state"]
    if observation.producer is None:
        del result["producer"]
    del result["sections"]
    result["coverage"] = _coverage_payload(observation.coverage)
    profile = profile_for(observation.analyzer.name)
    for name in profile.absent_sections:
        result[name] = None
    for name in profile.all_optional_sections:
        result.setdefault(name, None)
    result.update(
        {
            section.name: [_record_payload(record) for record in section.records]
            for section in observation.sections
        }
    )
    _validate_versioned_records(
        _observation_version(observation.schema_version), observation.sections, profile
    )
    _validate_profile_sections(result, profile)
    return result


def _field_selected(name: str, excluded: set[str]) -> bool:
    """Apply an open JSON field grammar; field names do not select protocol states."""
    return name not in excluded


def encode_canonical_model(model: dict[str, RawJson]) -> dict[str, RawJson]:
    """Losslessly columnize and intern repeated IR strings for browser-safe reports."""
    profile = _observation_profile(model)
    _validate_profile_sections(model, profile)
    excluded = {*CLASSIFIED_SECTIONS, "evidence"}
    encoded = {key: value for key, value in model.items() if _field_selected(key, excluded)}
    section_data_fields: dict[str, list[str]] = {}
    # AD-2: rows hold the non-JSON _MISSING_VALUE sentinel until intern writes "$m".
    rows_by_section: dict[str, list[list[Any]]] = {}
    for section in CLASSIFIED_SECTIONS:
        raw_items = model[section]
        if raw_items is None:
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
        # Literal $$m would otherwise collide with historical $$$m escaping.
        if value == _StringSentinel.ESCAPED_MISSING
        or (count >= 2 and len(value) >= 8 and (count - 1) * len(value) - count * 8 > 100)
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
                _string_sentinel(value) is not None
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
        "kind": _EncodingKind.COLUMNAR.value,
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
    if not _is_columnar(encoding):
        _validate_profile_sections(encoded, _observation_profile(encoded))
        return encoded
    profile = _observation_profile(encoded)
    _validate_profile_sections(encoded, profile)
    string_table = _strings(encoded["string_table"], "string_table")

    def expand(value: Any) -> Any:
        # AD-2: expanded rows may hold the non-JSON _MISSING_VALUE sentinel at any depth.
        if isinstance(value, str):
            sentinel = _string_sentinel(value)
            if sentinel is _StringSentinel.MISSING:
                return _MISSING_VALUE
            if sentinel is _StringSentinel.ESCAPED_MISSING:
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

    excluded = {*CLASSIFIED_SECTIONS, "evidence", "encoding", "string_table"}
    model: dict[str, RawJson] = {
        key: value for key, value in encoded.items() if _field_selected(key, excluded)
    }
    record_fields = _strings(encoding["record_fields"], "record_fields")
    section_data_fields = _object(encoding["section_data_fields"], "section_data_fields")
    for section in CLASSIFIED_SECTIONS:
        if section not in section_data_fields:
            # An observation from an analyzer that predates this section: fail closed (AD-3).
            raise ValueError(f"observation has no section {section}")
        data_fields = _strings(section_data_fields[section], f"section_data_fields.{section}")
        encoded_rows = encoded[section]
        if encoded_rows is None:
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


def _coverage_payload(value: Coverage) -> dict[str, RawJson]:
    result = _raw_object(asdict(replace(value, failures=())))
    result["failures"] = [_record_payload(record) for record in value.failures]
    if value.rules is None:
        del result["rules"]
    return result
