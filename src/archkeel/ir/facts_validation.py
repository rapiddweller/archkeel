# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Cross-reference and source-payload invariants of the collection protocol."""

from collections.abc import Iterable
from pathlib import PurePosixPath

from .facts import EvidenceClass, JsonValue, LocalTarget, Record, RecordData, SourceFacts
from .state_facts import ArgumentPass, AttributeAccess

_REQUIRED = {
    "symbols": ("qualified_name", "module", "name", "parent"),
    "imports": (
        "source_module",
        "source_package",
        "target_module",
        "target_package",
        "symbol",
        "binding",
        "symbols_known",
    ),
    "calls": ("source_scope", "source_module", "expression", "status", "targets"),
    "references": ("source_scope", "source_module", "expression", "status", "targets", "use"),
    "bindings": ("module",),
    "typing_signals": (),
    "constructs": ("owner", "construct"),
    "unknowns": (),
}
_STRING_FIELDS = frozenset(
    {
        "source_module",
        "source_package",
        "target_module",
        "target_package",
        "source_scope",
        "module",
        "qualified_name",
        "name",
        "status",
        "visibility",
        "record_kind",
        "class_kind",
        "expression",
        "use",
        "signal",
        "construct",
        "file",
        "reason",
        "message",
        "function",
        "parameter",
        "attribute",
        "path",
    }
)
_OPTIONAL_STRINGS = frozenset(
    {
        "annotation",
        "parent",
        "symbol",
        "binding",
        "return_annotation",
        "alias_expression",
    }
)
_BOOLEAN_FIELDS = frozenset(
    {
        "under_type_checking",
        "ordinary_module",
        "module_level_import",
        "reexport",
        "reexport_candidate",
        "symbols_known",
        "origin_binding_unique",
        "frozen_object",
        "candidates_truncated",
        "conditional",
        "is_async",
    }
)
_STRING_ARRAYS = frozenset(
    {"targets", "evidence_ids", "target_evidence_ids", "bases", "decorators", "handled"}
)
_POLICY_FIELDS = frozenset(
    {"contract", "baseline", "verdict", "rule_id", "rule_ids", "violations", "declared_root"}
)


def _unique(values: Iterable[str], label: str) -> set[str]:
    sequence = tuple(values)
    if len(set(sequence)) != len(sequence):
        raise ValueError(f"duplicate {label}")
    if any(not value for value in sequence):
        raise ValueError(f"empty {label}")
    return set(sequence)


def _payload(value: JsonValue) -> None:
    if isinstance(value, tuple):
        for child in value:
            _payload(child)
    elif isinstance(value, RecordData):
        for key, child in value.entries:
            if key in _POLICY_FIELDS:
                raise ValueError(f"policy field {key} is not a source fact")
            if key in _STRING_FIELDS and not isinstance(child, str):
                raise ValueError(f"source payload {key} must be a string")
            if key in _OPTIONAL_STRINGS and child is not None and not isinstance(child, str):
                raise ValueError(f"source payload {key} must be a string or null")
            if key in _BOOLEAN_FIELDS and child is not None and not isinstance(child, bool):
                raise ValueError(f"source payload {key} must be a boolean")
            if key in _STRING_ARRAYS and (
                not isinstance(child, tuple) or any(not isinstance(item, str) for item in child)
            ):
                raise ValueError(f"source payload {key} must be a string array")
            _payload(child)


def _source_record(record: Record, section: str) -> None:
    if record.evidence_class not in (EvidenceClass.FACT, EvidenceClass.UNKNOWN):
        raise ValueError("source records cannot carry governance decisions")
    if section == "unknowns" and record.evidence_class != EvidenceClass.UNKNOWN:
        raise ValueError("source unknowns must be UNKNOWN")
    if section != "unknowns" and record.evidence_class != EvidenceClass.FACT:
        raise ValueError("measured source sections must contain FACT records")
    if record.rule_ids or record.provenance:
        raise ValueError("source records cannot carry rules or contract provenance")
    fields = {key for key, _ in record.data.entries}
    if not set(_REQUIRED[section]).issubset(fields):
        raise ValueError(f"{section} source payload is missing required fields")
    _payload(record.data)


def validate_source_facts(facts: SourceFacts) -> None:
    """Reject claims that cannot be replayed by Core against a separate contract."""
    selected = _unique(facts.coverage.selected_files, "selected file")
    if not 0 <= facts.coverage.files_parsed <= facts.coverage.files_read <= len(selected):
        raise ValueError("impossible collection coverage counts")
    if facts.coverage.files_parsed < len(selected) and not facts.coverage.gaps:
        raise ValueError("unobserved selected files require coverage gaps")
    inputs = _unique((item.path for item in facts.inputs), "resolution input")
    selected_inputs = {item.path for item in facts.inputs if item.role == "selected"}
    if not selected_inputs.issubset(selected):
        raise ValueError("selected input is outside selected coverage")
    file_ids = _unique((item.id for item in facts.files), "file id")
    _unique((item.module for item in facts.files), "module identity")
    paths = _unique((item.rel_path for item in facts.files), "module path")
    if not paths.issubset(selected_inputs):
        raise ValueError("observed module needs a selected input")
    if len(facts.files) > facts.coverage.files_parsed:
        raise ValueError("observed modules exceed parsed files")
    evidence_ids = _unique((item.id for item in facts.evidence), "evidence id")
    candidate_ids = _unique((item.id for item in facts.candidate_evidence), "candidate evidence id")
    base_by_id = {item.id: item for item in facts.evidence}
    if any(
        item.id in base_by_id and base_by_id[item.id] != item for item in facts.candidate_evidence
    ):
        raise ValueError("candidate evidence disagrees with source evidence")
    for evidence in (*facts.evidence, *facts.candidate_evidence):
        path = PurePosixPath(evidence.file)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in evidence.file
            or ":" in evidence.file
        ):
            raise ValueError("evidence path escapes source snapshot")
        if evidence.file not in inputs:
            raise ValueError("evidence needs a digested input")
        if evidence.line < 0 or evidence.end_line < evidence.line or evidence.column < 0:
            raise ValueError("invalid evidence range")
    if any(item.evidence_id not in evidence_ids for item in facts.files):
        raise ValueError("file has dangling evidence reference")
    names = _unique((section.name for section in facts.sections), "section")
    declared = _unique(facts.capabilities.sections, "capability section")
    if names != declared:
        raise ValueError("source sections disagree with declared capabilities")
    records = [record for section in facts.sections for record in section.records]
    record_ids = _unique((record.id for record in records), "source record id")
    if file_ids & record_ids:
        raise ValueError("file and record ids collide")
    for section in facts.sections:
        for record in section.records:
            _source_record(record, section.name)
    for record in records:
        if not set(record.evidence_ids).issubset(evidence_ids):
            raise ValueError("dangling source evidence reference")
        if not set(record.fact_ids).issubset(record_ids | file_ids):
            raise ValueError("dangling source fact reference")
    record_by_id = {record.id: record for record in records}
    for gap in facts.coverage.gaps:
        _source_record(gap, "unknowns")
        if gap.evidence_class != EvidenceClass.UNKNOWN:
            raise ValueError("coverage gap must be UNKNOWN")
        if gap.id not in record_by_id or record_by_id[gap.id] != gap:
            raise ValueError("coverage gap must reference its source UNKNOWN record")
    imports = {
        record.id
        for section in facts.sections
        if section.name == "imports"
        for record in section.records
    }
    target_ids = _unique((target.import_id for target in facts.imports), "import target")
    if target_ids != imports:
        raise ValueError("each import needs exactly one typed target")
    file_by_module = {item.module: item for item in facts.files}
    for target in facts.imports:
        if isinstance(target, LocalTarget):
            observed = file_by_module.get(target.module)
            if observed is not None and observed.rel_path != target.file:
                raise ValueError("local import target disagrees with observed module")
            for target_path in (target.file, target.runtime_file, target.declaration_file):
                if target_path is not None and target_path not in inputs:
                    raise ValueError("local import target needs a digested input")
            if record_by_id[target.import_id].data.get("target_module") != target.module:
                raise ValueError("local import target disagrees with import payload")
    _unique((binding for binding, _ in facts.uncertain_reexports), "reexport binding")
    _unique((expression for expression, _ in facts.type_shapes), "type expression")

    state_ids = evidence_ids | candidate_ids
    for class_state in facts.state.classes:
        used = {
            *class_state.evidence_ids,
            *(item for field in class_state.fields for item in field.evidence_ids),
        }
        if not used.issubset(state_ids):
            raise ValueError("class state has dangling candidate evidence")
    for function in facts.state.functions:
        for event in function.events:
            if (
                isinstance(event, AttributeAccess | ArgumentPass)
                and event.evidence_id not in state_ids
            ):
                raise ValueError("state trace has dangling candidate evidence")
