# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Cross-reference and source-payload invariants of the collection protocol."""

from collections.abc import Iterable
from pathlib import PurePosixPath

from .facts import (
    BuiltinTarget,
    ConstructSupport,
    Evidence,
    EvidenceClass,
    ExternalPackageTarget,
    JsonValue,
    LocalTarget,
    Record,
    RecordData,
    SourceFacts,
    UnresolvedTarget,
    in_scope,
    member_inventories,
)
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
        "relative_level",
        "under_type_checking",
    ),
    "calls": ("source_scope", "source_module", "expression", "status", "targets"),
    "references": ("source_scope", "source_module", "expression", "status", "targets", "use"),
    "bindings": ("module",),
    "typing_signals": ("owner", "signal"),
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
        "declaration_scope",
        "declaration_definition_id",
        "owner",
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
        "type_only",
        "ordinary_module",
        "module_level_import",
        "reexport",
        "reexport_candidate",
        "symbols_known",
        "frozen_object",
        "candidates_truncated",
        "conditional",
        "is_async",
    }
)
_PROOF_FLAGS = frozenset(
    {
        "origin_binding_unique",
        "source_binding_unique",
        "source_member_binding_static",
        "origin_member_binding_static",
        "class_header_static",
        "class_body_control_flow",
        "signature_decorators_proven",
        "source_final_method_binding",
        "overload_signature",
        "overloaded",
    }
)
_STRING_ARRAYS = frozenset(
    {
        "targets",
        "evidence_ids",
        "target_evidence_ids",
        "bases",
        "decorators",
        "handled",
        "property_members",
    }
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


def _payload(value: RecordData) -> None:
    # Nested mappings may use source-defined names such as `status` or `contract`.
    # Only the record envelope's own fields have protocol meaning.
    for key, child in value.entries:
        if key == "property_binding":
            _property_payload(child)
        if key in _POLICY_FIELDS:
            raise ValueError(f"policy field {key} is not a source fact")
        if key in _STRING_FIELDS and not isinstance(child, str):
            raise ValueError(f"source payload {key} must be a string")
        if key in _OPTIONAL_STRINGS and child is not None and not isinstance(child, str):
            raise ValueError(f"source payload {key} must be a string or null")
        if key in _BOOLEAN_FIELDS and child is not None and not isinstance(child, bool):
            raise ValueError(f"source payload {key} must be a boolean")
        if key in _PROOF_FLAGS and not isinstance(child, bool):
            raise ValueError(f"source payload {key} must be a boolean")
        if key == "reexport_candidates" and (
            not isinstance(child, tuple)
            or any(not isinstance(item, str) or not item for item in child)
        ):
            raise ValueError("source payload reexport_candidates must be a nonempty-string array")
        if key in _STRING_ARRAYS and (
            not isinstance(child, tuple) or any(not isinstance(item, str) for item in child)
        ):
            raise ValueError(f"source payload {key} must be a string array")


def _property_payload(value: JsonValue) -> None:
    if not isinstance(value, RecordData) or {key for key, _ in value.entries} != {
        "operation",
        "source",
        "line",
        "source_line",
    }:
        raise ValueError("invalid property binding fields")
    operation, source = value.get("operation"), value.get("source")
    line, source_line = value.get("line"), value.get("source_line")
    if (
        operation not in ("create", "getter", "setter")
        or source not in ("new", "local", "base")
        or type(line) is not int
        or type(source_line) is not int
        or line < 1
        or source_line < 0
        or source_line >= line
        or (operation == "create") != (source == "new")
        or (source == "local") != (source_line > 0)
    ):
        raise ValueError("invalid property binding operation or order")


def _property_bindings(records: list[Record], evidence: dict[str, Evidence]) -> None:
    classes = {
        name: record
        for record in records
        if record.kind == "class" and isinstance(name := record.data.get("qualified_name"), str)
    }
    members: dict[str, set[str]] = {}
    ordered: dict[tuple[str, str], dict[int, Record]] = {}
    for record in records:
        parent, name = record.data.get("parent"), record.data.get("name")
        if record.kind == "method" and isinstance(parent, str) and isinstance(name, str):
            for reference in record.evidence_ids:
                if reference in evidence:
                    ordered.setdefault((parent, name), {})[evidence[reference].line] = record
    for record in records:
        if record.data.get("property_members") is not None and record.kind != "class":
            raise ValueError("property members need a class owner")
        binding = record.data.get("property_binding")
        if record.data.get("source_final_method_binding") is True:
            parent, name = record.data.get("parent"), record.data.get("name")
            owner = classes.get(parent) if isinstance(parent, str) else None
            group = (
                ordered.get((parent, name), {})
                if isinstance(parent, str) and isinstance(name, str)
                else {}
            )
            if (
                record.kind != "method"
                or owner is None
                or owner.data.get("source_binding_unique") is not True
                or record.data.get("qualified_name") != f"{parent}.{name}"
                or owner.data.get("module") != record.data.get("module")
                or record.data.get("decorators") != ()
                or binding is not None
                or group.get(max(group, default=0)) != record
            ):
                raise ValueError("final method binding needs its last undecorated definition")
        if binding is None:
            continue
        parent, name = record.data.get("parent"), record.data.get("name")
        owner = classes.get(parent) if isinstance(parent, str) else None
        if (
            record.kind != "method"
            or record.data.get("symbol_category") != "method"
            or record.data.get("method_kind") != "instance"
            or record.data.get("async") is not False
            or not isinstance(binding, RecordData)
            or not isinstance(parent, str)
            or not isinstance(name, str)
            or owner is None
            or record.data.get("qualified_name") != f"{parent}.{name}"
            or owner.data.get("module") != record.data.get("module")
        ):
            raise ValueError("property binding needs its defining class and method")
        line, source_line = binding.get("line"), binding.get("source_line")
        group = ordered.get((parent, name), {})
        if not isinstance(line, int) or group.get(line) != record:
            raise ValueError("property order disagrees with method evidence")
        if binding.get("source") == "local":
            previous = max((position for position in group if position < line), default=0)
            previous_record = group.get(previous)
            if (
                previous != source_line
                or previous_record is None
                or previous_record.data.get("property_binding") is None
            ):
                raise ValueError("property source must be the previous binding in its class")
        member_names: set[str] = members.setdefault(parent, set())
        member_names.add(name)
    for parent, record in classes.items():
        names = record.data.get("property_members", ())
        if not isinstance(names, tuple) or _unique(
            (name for name in names if isinstance(name, str)), "property member"
        ) != members.get(parent, set()):
            raise ValueError("property members disagree with method binding proofs")


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
    declaration = {"declaration_scope", "declaration_definition_id"}
    if fields & declaration and (section != "references" or not declaration <= fields):
        raise ValueError("reference declaration needs both identity fields")
    if fields & declaration and any(record.data.get(key) == "" for key in declaration):
        raise ValueError("reference declaration identities must be nonempty")
    if not set(_REQUIRED[section]).issubset(fields):
        raise ValueError(f"{section} source payload is missing required fields")
    if record.data.get("member_inventories") is not None:
        if section != "symbols" or record.kind != "class":
            raise ValueError("member inventory needs its class owner")
        member_inventories(record.data.get("member_inventories"))
    _payload(record.data)


def _member_inventory_bindings(records: list[Record]) -> None:
    for owner in records:
        for inventory in member_inventories(owner.data.get("member_inventories")):
            if inventory.kind == "method":
                actual = {
                    item.id
                    for item in records
                    if item.kind == "method" and item.data.get("lexical_parent_id") == owner.id
                }
            else:
                attributes = owner.data.get("attribute_declarations")
                if not isinstance(attributes, tuple) or any(
                    not isinstance(item, RecordData) for item in attributes
                ):
                    raise ValueError("member inventory needs explicit attribute declarations")
                ids: list[str] = []
                for item in attributes:
                    identifier = item.get("definition_id") if isinstance(item, RecordData) else None
                    if not isinstance(identifier, str) or not identifier:
                        raise ValueError("member inventory needs explicit attribute identities")
                    if isinstance(item, RecordData) and item.get("static") is not None:
                        if not isinstance(item.get("static"), bool):
                            raise ValueError("attribute static modifier must be boolean")
                    ids.append(identifier)
                actual = _unique(ids, "member inventory attribute")
            if actual != set(inventory.definition_ids):
                raise ValueError("member inventory identities disagree with their owner")


def validate_source_facts(facts: SourceFacts) -> None:
    """Reject claims that cannot be replayed by Core against a separate contract."""
    selected = _unique(facts.coverage.selected_files, "selected file")
    if not 0 <= facts.coverage.files_parsed <= facts.coverage.files_read <= len(selected):
        raise ValueError("impossible collection coverage counts")
    if facts.coverage.files_parsed < len(selected) and not facts.coverage.gaps:
        raise ValueError("unobserved selected files require coverage gaps")
    if not facts.coverage.full_scope and not facts.coverage.gaps:
        raise ValueError("partial collection requires coverage gaps")
    if facts.coverage.full_scope and (
        facts.coverage.gaps or facts.coverage.files_parsed != len(selected)
    ):
        raise ValueError("complete collection contradicts coverage gaps or counts")
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
    if (
        facts.profile != "archkeel-dart-directives"
        and len(facts.files) != facts.coverage.files_parsed
    ):
        raise ValueError("each parsed source file needs an observed module")
    if facts.coverage.full_scope and facts.coverage.files_parsed and not facts.files:
        raise ValueError("complete parsed source needs an observed module")
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
    if any(base_by_id[item.evidence_id].file != item.rel_path for item in facts.files):
        raise ValueError("module evidence disagrees with source file")
    names = _unique((section.name for section in facts.sections), "section")
    declared = _unique(facts.capabilities.sections, "capability section")
    _unique((entry.name for entry in facts.capabilities.constructs), "construct capability")
    if names != declared:
        raise ValueError("source sections disagree with declared capabilities")
    records = [record for section in facts.sections for record in section.records]
    record_ids = _unique((record.id for record in records), "source record id")
    if file_ids & record_ids:
        raise ValueError("file and record ids collide")
    for section in facts.sections:
        for record in section.records:
            _source_record(record, section.name)
            construct = record.data.get("construct")
            if construct is not None and not any(
                entry.name == construct and entry.status != ConstructSupport.UNSUPPORTED
                for entry in facts.capabilities.constructs
            ):
                raise ValueError("source construct disagrees with declared capabilities")
    for record in records:
        if not set(record.evidence_ids).issubset(evidence_ids):
            raise ValueError("dangling source evidence reference")
        if not set(record.fact_ids).issubset(record_ids | file_ids):
            raise ValueError("dangling source fact reference")
    record_by_id = {record.id: record for record in records}
    _property_bindings(records, base_by_id)
    _member_inventory_bindings(records)
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
    file_by_path = {item.rel_path: item for item in facts.files}
    for section in facts.sections:
        if section.name == "unknowns":
            continue
        for record in section.records:
            source_module = record.data.get("source_module", record.data.get("module"))
            owner = record.data.get("owner")
            if source_module is None and isinstance(owner, str) and record.evidence_ids:
                source = file_by_path.get(base_by_id[record.evidence_ids[0]].file)
                source_module = source.module if source is not None else None
            if not isinstance(source_module, str):
                raise ValueError("source record needs an observed module or owner")
            source = file_by_module.get(source_module)
            if source is None:
                raise ValueError("source record names an unobserved module")
            for field in ("owner", "source_scope", "qualified_name", "declaration_scope"):
                identity = record.data.get(field)
                if identity is not None and (
                    not isinstance(identity, str)
                    or not in_scope(identity.split(":", 1)[0], source.module)
                ):
                    raise ValueError(f"source record {field} disagrees with its module")
            if not record.evidence_ids or any(
                base_by_id[item].file != source.rel_path for item in record.evidence_ids
            ):
                raise ValueError("source record evidence disagrees with its module")
            if section.name == "imports" and record.data.get("source_package") != source.package:
                raise ValueError("import source package disagrees with its module")
    for target in facts.imports:
        data = record_by_id[target.import_id].data
        if isinstance(target, LocalTarget):
            observed = file_by_module.get(target.module)
            if observed is None and facts.coverage.full_scope:
                raise ValueError("unobserved local target requires incomplete coverage")
            if observed is not None and observed.rel_path != target.file:
                raise ValueError("local import target disagrees with observed module")
            if observed is not None and data.get("target_package") != observed.package:
                raise ValueError("local import package disagrees with observed module")
            for target_path in (target.file, target.runtime_file, target.declaration_file):
                if target_path is not None and target_path not in inputs:
                    raise ValueError("local import target needs a digested input")
            if data.get("target_module") != target.module:
                raise ValueError("local import target disagrees with import payload")
        elif isinstance(target, ExternalPackageTarget):
            if data.get("target_module") in file_by_module:
                raise ValueError("observed local module cannot be an external target")
            if data.get("target_package") != target.package:
                raise ValueError("external import target disagrees with import payload")
        elif isinstance(target, BuiltinTarget):
            if data.get("target_module") in file_by_module:
                raise ValueError("observed local module cannot be a builtin target")
            if data.get("target_module") != target.name:
                raise ValueError("builtin import target disagrees with import payload")
        elif isinstance(target, UnresolvedTarget):
            if data.get("target_module") != target.specifier:
                raise ValueError("unresolved import target disagrees with import payload")
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
