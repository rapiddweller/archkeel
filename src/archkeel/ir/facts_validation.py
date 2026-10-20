# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Cross-reference and source-payload invariants of the collection protocol."""

from collections.abc import Collection, Iterable, Mapping
from pathlib import PurePosixPath

from .facts import (
    CALL_BINDINGS_FEATURE,
    MAX_STATIC_INTEGER,
    SOURCE_RESOLUTION_GAP_KIND,
    BuiltinTarget,
    CallBinding,
    CallBindingOrigin,
    ConstructSupport,
    ContextManagerSignature,
    Evidence,
    EvidenceClass,
    ExternalPackageTarget,
    LocalTarget,
    MethodKind,
    PropertyOrigin,
    ProviderBinding,
    ProviderBindingKind,
    Record,
    RecordData,
    ResolutionInput,
    SourceFacts,
    SourceProfile,
    SourceResolution,
    SourceSectionName,
    UnresolvedTarget,
    call_binding,
    contextmanager_signature,
    in_scope,
    member_inventories,
    parse_method_kind,
    parse_source_resolution,
    property_binding,
    stable_id,
)
from .facts import MemberKind as _MemberKind
from .facts import ResolutionRole as _ResolutionRole
from .state_facts import ArgumentPass, AttributeAccess
from .type_shapes import TypeApplication, TypeShape

_REQUIRED = {
    SourceSectionName.SYMBOLS: ("qualified_name", "module", "name", "parent"),
    SourceSectionName.IMPORTS: (
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
    SourceSectionName.CALLS: ("source_scope", "source_module", "expression", "status", "targets"),
    SourceSectionName.REFERENCES: (
        "source_scope",
        "source_module",
        "expression",
        "status",
        "targets",
        "use",
    ),
    SourceSectionName.BINDINGS: ("module",),
    SourceSectionName.TYPING_SIGNALS: ("owner", "signal"),
    SourceSectionName.CONSTRUCTS: ("owner", "construct"),
    SourceSectionName.UNKNOWNS: (),
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
        "source_file",
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
        "mixin_capable",
        "candidates_truncated",
        "conditional",
        "is_async",
        "signature_complete",
    }
)
_PROOF_FLAGS = frozenset(
    {
        "origin_binding_unique",
        "source_binding_unique",
        "source_binding_static",
        "source_member_binding_static",
        "origin_member_binding_static",
        "class_header_static",
        "source_class_header_static",
        "typed_dict_header_static",
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


def _signature_origin(
    data: RecordData, spelling: str, records: list[Record], facts: SourceFacts
) -> str | None:
    root, _, suffix = spelling.partition(".")
    module = data.get("module")
    files = [file for file in facts.files if file.module == module]
    matches = [
        record
        for record in records
        if record.kind == "import"
        and record.data.get("source_module") == module
        and record.data.get("binding") == root
        and record.data.get("module_level_import") is True
        and record.data.get("under_type_checking") is False
    ]
    if len(files) != 1 or root not in files[0].stable_bindings or len(matches) != 1:
        return None
    binding = matches[0].data
    target, symbol = binding.get("target_module"), binding.get("symbol")
    if not isinstance(target, str) or symbol is not None and not isinstance(symbol, str):
        return None
    return ".".join(part for part in (target, symbol, suffix) if part)


def _signature_terminal(name: str, bindings: dict[str, ProviderBinding]) -> ProviderBinding | None:
    seen: set[str] = set()
    while name not in seen:
        seen.add(name)
        binding = bindings.get(name)
        if binding is None or binding.kind is not ProviderBindingKind.ALIAS:
            return binding
        if binding.target is None:
            return None
        name = binding.target
    return None


def _signature_shapes(
    data: RecordData, signature: ContextManagerSignature, shapes: dict[str, TypeShape]
) -> TypeApplication:
    source = data.get("returns")
    original = shapes.get(source) if isinstance(source, str) else None
    effective = signature.effective_return
    result = shapes.get(f"{effective.wrapper}[{effective.payload}]")
    if (
        not isinstance(original, TypeApplication)
        or len(original.arguments) != 1
        or original.arguments[0].text != effective.payload
        or not isinstance(result, TypeApplication)
        or result.head.text != effective.wrapper
        or len(result.arguments) != 1
        or result.arguments[0].text != effective.payload
        or effective.payload not in shapes
    ):
        raise ValueError("contextmanager source/effective type shapes disagree")
    return original


def _signature_support(
    facts: SourceFacts,
    record: Record,
    signature: ContextManagerSignature,
    evidence: dict[str, Evidence],
    inputs: Mapping[str, ResolutionInput],
) -> None:
    own = set(record.evidence_ids)
    source = [file for file in facts.files if file.module == record.data.get("module")]
    if not own or not own <= set(signature.support_evidence_ids) or len(source) != 1:
        raise ValueError("contextmanager signature needs its own source evidence")
    for reference in own:
        item = evidence.get(reference)
        if (
            item is None
            or item.file != source[0].rel_path
            or item.file not in inputs
            or inputs[item.file].role is not _ResolutionRole.SELECTED
        ):
            raise ValueError("contextmanager signature needs its own selected source evidence")
    support = [
        evidence.get(reference)
        for reference in signature.support_evidence_ids
        if reference not in own
    ]
    if any(
        item is None
        or item.file not in inputs
        or inputs[item.file].role is not _ResolutionRole.RESOLUTION
        or not item.file.startswith(".archkeel-providers/")
        for item in support
    ):
        raise ValueError("contextmanager signature needs captured provider support")
    if not any(item is not None and item.file == ".archkeel-providers/abc.py" for item in support):
        raise ValueError("contextmanager signature needs its bound ABC branch")


def _contextmanager_signatures(
    facts: SourceFacts,
    records: list[Record],
    evidence: dict[str, Evidence],
    inputs: Mapping[str, ResolutionInput],
) -> None:
    bindings = {binding.qualified_name: binding for binding in facts.provider_bindings}
    for record in records:
        if "contextmanager_signature" not in dict(record.data.entries):
            continue
        data = record.data
        signature = contextmanager_signature(data.get("contextmanager_signature"))
        decorators = data.get("decorators")
        if (
            facts.profile is not SourceProfile.PYTHON
            or facts.runtime.name != "python"
            or signature.partial.version != facts.runtime.version
            or data.get("source_binding_unique") is not True
            or data.get("namespace_bound") is not True
            or data.get("parent") is not None
            or data.get("async") is not False
            or data.get("signature_decorators_proven") is not False
            or not isinstance(decorators, tuple)
            or len(decorators) != 1
            or not isinstance(decorators[0], str)
        ):
            raise ValueError("contextmanager signature source/runtime identity mismatch")
        source = _signature_shapes(data, signature, dict(facts.type_shapes))
        decorated = _signature_origin(data, decorators[0], records, facts)
        iterator = _signature_origin(data, source.head.text, records, facts)
        factory = _signature_terminal(decorated, bindings) if decorated is not None else None
        payload = _signature_terminal(iterator, bindings) if iterator is not None else None
        wrapper = bindings.get(signature.effective_return.wrapper)
        if (
            factory is None
            or factory.kind is not ProviderBindingKind.FUNCTION
            or factory.qualified_name != signature.factory
            or payload is None
            or payload.kind is not ProviderBindingKind.CLASS
            or payload.qualified_name != "_collections_abc.Iterator"
            or wrapper is None
            or wrapper.kind is not ProviderBindingKind.CLASS
            or wrapper.qualified_name.rpartition(".")[0] != signature.factory.rpartition(".")[0]
            or not {factory.evidence_id, wrapper.evidence_id, payload.evidence_id}
            <= set(signature.support_evidence_ids)
        ):
            raise ValueError(
                "contextmanager signature needs bound factory/wrapper/iterator declarations"
            )
        _signature_support(facts, record, signature, evidence, inputs)


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
        raw_binding = record.data.get("property_binding")
        binding = None
        if any(key == "property_binding" for key, _ in record.data.entries):
            if not isinstance(raw_binding, RecordData):
                raise ValueError("invalid property binding fields")
            binding = property_binding(raw_binding)
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
            or parse_method_kind(record.data.get("method_kind")) is not MethodKind.INSTANCE
            or record.data.get("async") is not False
            or not isinstance(parent, str)
            or not isinstance(name, str)
            or owner is None
            or record.data.get("qualified_name") != f"{parent}.{name}"
            or owner.data.get("module") != record.data.get("module")
        ):
            raise ValueError("property binding needs its defining class and method")
        line, source_line = binding.line, binding.source_line
        group = ordered.get((parent, name), {})
        if not isinstance(line, int) or group.get(line) != record:
            raise ValueError("property order disagrees with method evidence")
        if binding.source is PropertyOrigin.LOCAL:
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


def _call_declaration(binding: CallBinding, declarations: Mapping[str, list[Record]]) -> Record:
    targets = declarations.get(binding.target, [])
    if len(targets) != 1:
        raise ValueError("call binding needs one target declaration")
    [target] = targets
    if binding.origin is CallBindingOrigin.DIRECT:
        if (
            target.kind != "function"
            or target.data.get("source_binding_unique") is not True
            or target.data.get("source_binding_static") is not True
            or target.data.get("decorators")
        ):
            raise ValueError("direct call needs a stable plain function declaration")
    else:
        parent = target.data.get("parent")
        owners = declarations.get(parent, []) if isinstance(parent, str) else []
        if target.kind != "method" or len(owners) != 1 or target.data.get("decorators"):
            raise ValueError("declared receiver needs a plain method and class owner")
        [owner] = owners
        if (
            owner.kind != "class"
            or owner.data.get("source_binding_unique") is not True
            or owner.data.get("source_member_binding_static") is not True
            or not set(owner.evidence_ids) <= set(binding.evidence_ids)
        ):
            raise ValueError("declared receiver needs a stable class binding")
    return target


def _source_record(record: Record, section: SourceSectionName) -> None:
    if record.evidence_class not in (EvidenceClass.FACT, EvidenceClass.UNKNOWN):
        raise ValueError("source records cannot carry governance decisions")
    if section == SourceSectionName.UNKNOWNS and record.evidence_class != EvidenceClass.UNKNOWN:
        raise ValueError("source unknowns must be UNKNOWN")
    if section != SourceSectionName.UNKNOWNS and record.evidence_class != EvidenceClass.FACT:
        raise ValueError("measured source sections must contain FACT records")
    if record.rule_ids or record.provenance:
        raise ValueError("source records cannot carry rules or contract provenance")
    fields = {key for key, _ in record.data.entries}
    declaration = {"declaration_scope", "declaration_definition_id"}
    if fields & declaration and (
        section != SourceSectionName.REFERENCES or not declaration <= fields
    ):
        raise ValueError("reference declaration needs both identity fields")
    if fields & declaration and any(record.data.get(key) == "" for key in declaration):
        raise ValueError("reference declaration identities must be nonempty")
    required = _REQUIRED[section]
    if section is SourceSectionName.CONSTRUCTS and record.kind == "numeric_operand":
        required = (
            "owner",
            "module",
            "operation",
            "form",
            "line",
            "column",
            "end_line",
            "end_column",
            "subject",
            "proof",
            "value",
            "derivation",
        )
        data = record.data
        span_names = ("line", "column", "end_line", "end_column")
        span = tuple(data.get(name) for name in span_names)
        value = data.get("value")
        derivation = data.get("derivation")
        if (
            fields != set(required)
            or data.get("operation") != "modulo"
            or data.get("form") not in {"binary", "augmented"}
            or data.get("proof") not in {"known", "unknown"}
            or not record.evidence_ids
            or not isinstance(data.get("owner"), str)
            or not data.get("owner")
            or not isinstance(data.get("module"), str)
            or not data.get("module")
            or data.get("subject") is not None
            and (not isinstance(data.get("subject"), str) or not data.get("subject"))
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in span)
            or not isinstance(span[0], int)
            or not isinstance(span[1], int)
            or not isinstance(span[2], int)
            or not isinstance(span[3], int)
            or span[0] < 1
            or span[1] < 0
            or span[2] < span[0]
            or span[3] < 0
            or span[2] == span[0]
            and span[3] <= span[1]
            or data.get("proof") == "known"
            and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < -MAX_STATIC_INTEGER
                or value > MAX_STATIC_INTEGER
            )
            or data.get("proof") == "unknown"
            and value is not None
            or not isinstance(derivation, tuple)
        ):
            raise ValueError("invalid numeric operand source proof")
        for item in derivation:
            if not isinstance(item, RecordData):
                raise ValueError("invalid numeric operand alias proof")
            origin_fields = {key for key, _ in item.entries}
            origin_value = item.get("value")
            origin_span = tuple(item.get(name) for name in span_names)
            if (
                origin_fields
                != {
                    "name",
                    "value",
                    "expression",
                    "evidence_id",
                    "line",
                    "column",
                    "end_line",
                    "end_column",
                }
                or not isinstance(item.get("name"), str)
                or not item.get("name")
                or not isinstance(origin_value, int)
                or isinstance(origin_value, bool)
                or origin_value < -MAX_STATIC_INTEGER
                or origin_value > MAX_STATIC_INTEGER
                or not isinstance(item.get("expression"), str)
                or not item.get("expression")
                or not isinstance(item.get("evidence_id"), str)
                or item.get("evidence_id") not in record.evidence_ids
                or not all(
                    isinstance(field, int) and not isinstance(field, bool) for field in origin_span
                )
                or not isinstance(origin_span[0], int)
                or not isinstance(origin_span[1], int)
                or not isinstance(origin_span[2], int)
                or not isinstance(origin_span[3], int)
                or origin_span[0] < 1
                or origin_span[1] < 0
                or origin_span[2] < origin_span[0]
                or origin_span[3] < 0
            ):
                raise ValueError("invalid numeric operand alias proof")
        if data.get("proof") == "unknown" and derivation:
            raise ValueError("invalid numeric operand source proof")
    if not set(required).issubset(fields):
        raise ValueError(f"{section} source payload is missing required fields")
    if record.data.get("member_inventories") is not None:
        if section != SourceSectionName.SYMBOLS or record.kind != "class":
            raise ValueError("member inventory needs its class owner")
        member_inventories(record.data.get("member_inventories"))
    if "contextmanager_signature" in fields:
        if section is not SourceSectionName.SYMBOLS or record.kind != "function":
            raise ValueError("contextmanager signature needs a function owner")
        contextmanager_signature(record.data.get("contextmanager_signature"))
    if "base_declarations" in fields:
        _base_declarations(record, section)
    if "call_binding" in fields:
        if section is not SourceSectionName.CALLS:
            raise ValueError("call binding needs its call owner")
        call_binding(record.data.get("call_binding"))
    _payload(record.data)


def _base_declarations(record: Record, section: SourceSectionName) -> None:
    value = record.data.get("base_declarations")
    if (
        section != SourceSectionName.SYMBOLS
        or record.kind != "class"
        or not isinstance(value, tuple)
        or any(not isinstance(item, RecordData) for item in value)
    ):
        raise ValueError("base declarations need a class symbol and typed base records")
    bases = tuple(item for item in value if isinstance(item, RecordData))
    required = {
        "id",
        "relationship_kind",
        "status",
        "targets",
        "candidate_count",
        "expression",
        "evidence_ids",
    }
    optional = {"candidates_truncated", "reason"}
    for base in bases:
        fields = {key for key, _ in base.entries}
        relation = base.get("relationship_kind")
        status = parse_source_resolution(base.get("status"))
        targets = base.get("targets")
        count = base.get("candidate_count")
        evidence_ids = base.get("evidence_ids")
        truncated = base.get("candidates_truncated", False)
        if (
            not required <= fields
            or fields - required - optional
            or not isinstance(base.get("id"), str)
            or not base.get("id")
            or relation not in {"inherits", "realizes", "mixes_in"}
            or status is None
            or not isinstance(base.get("expression"), str)
            or not base.get("expression")
            or not isinstance(targets, tuple)
            or any(not isinstance(target, str) or not target for target in targets)
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < len(targets)
            or not isinstance(truncated, bool)
            or status is SourceResolution.RESOLVED
            and len(targets) != 1
            or status is SourceResolution.UNRESOLVED
            and targets
            or truncated
            and (status is not SourceResolution.PARTIALLY_RESOLVED or count <= len(targets))
            or not isinstance(evidence_ids, tuple)
            or any(not isinstance(identity, str) or not identity for identity in evidence_ids)
            or base.get("reason") is not None
            and not isinstance(base.get("reason"), str)
        ):
            raise ValueError("invalid typed base declaration")


def _member_inventory_bindings(records: list[Record]) -> None:
    methods: dict[str, set[str]] = {}
    for record in records:
        if record.kind == "method":
            parent = record.data.get("lexical_parent_id")
            if isinstance(parent, str):
                direct_methods: set[str] = methods.setdefault(parent, set())
                direct_methods.add(record.id)
    for owner in records:
        for inventory in member_inventories(owner.data.get("member_inventories")):
            if inventory.kind == _MemberKind.METHOD:
                actual = methods.get(owner.id, set())
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


def validate_source_bindings(
    records: Iterable[Record],
    module_paths: Mapping[str, str],
    module_packages: Mapping[str, str],
    evidence: Mapping[str, Evidence],
    *,
    import_ids: Collection[str],
    selected_inputs: Collection[str],
    allow_part_evidence: bool = False,
    source_records: Mapping[str, Record] | None = None,
    allow_script_effects: bool = False,
) -> None:
    """Bind source records and their evidence to the same observed module."""
    _unique(module_paths.values(), "module path")
    modules_by_path = {path: module for module, path in module_paths.items()}
    for record in records:
        if record.kind == SOURCE_RESOLUTION_GAP_KIND:
            if (
                _resolution_gap_module(
                    record, module_paths, evidence, source_records or {}, allow_script_effects
                )
                is None
            ):
                raise ValueError("source resolution gap has no bound resolution dimension")
            continue
        source_module = (
            record.data.get("qualified_name")
            if record.kind == "module"
            else record.data.get("source_module", record.data.get("module"))
        )
        owner = record.data.get("owner")
        if source_module is None and isinstance(owner, str) and record.evidence_ids:
            source_module = modules_by_path.get(evidence[record.evidence_ids[0]].file)
        if not isinstance(source_module, str):
            raise ValueError("source record needs an observed module or owner")
        source_path = module_paths.get(source_module)
        if source_path is None:
            raise ValueError("source record names an unobserved module")
        if (
            record.id in import_ids
            and record.data.get("source_package") != module_packages[source_module]
        ):
            raise ValueError("import source package disagrees with its module")
        for field in ("owner", "source_scope", "qualified_name", "declaration_scope"):
            identity = record.data.get(field)
            if identity is not None and (
                not isinstance(identity, str)
                or not in_scope(identity.split(":", 1)[0], source_module)
            ):
                raise ValueError(f"source record {field} disagrees with its module")
        if not record.evidence_ids or any(
            evidence[item].file != source_path
            and not (
                allow_part_evidence
                and record.data.get("source_file") == evidence[item].file
                and evidence[item].file in selected_inputs
                and evidence[item].file not in modules_by_path
            )
            for item in record.evidence_ids
        ):
            raise ValueError("source record evidence disagrees with its module")


def _resolution_gap_module(
    gap: Record,
    module_paths: Mapping[str, str],
    evidence: Mapping[str, Evidence],
    records: Mapping[str, Record],
    allow_script_effects: bool,
) -> str | None:
    """Read only witnessed uncertainty; a dimension label alone proves no scope."""
    module = gap.data.get("source_module", gap.data.get("module"))
    dimension = gap.data.get("resolution_dimension")
    if (
        gap.kind != SOURCE_RESOLUTION_GAP_KIND
        or gap.evidence_class != EvidenceClass.UNKNOWN
        or dimension not in {"imports", "signature", "runtime_effects"}
        or not isinstance(module, str)
        or gap.data.get("source_module", module) != module
        or gap.data.get("module", module) != module
        or gap.subjects != (module,)
        or module not in module_paths
        or not gap.evidence_ids
        or any(
            identity not in evidence or evidence[identity].file != module_paths[module]
            for identity in gap.evidence_ids
        )
        or gap.data.get("file", module_paths[module]) != module_paths[module]
    ):
        return None
    if dimension == "runtime_effects" and not (
        allow_script_effects
        and _script_effect_binding(gap, records, evidence, module, module_paths[module])
    ):
        return None
    if dimension == "signature":
        if len(gap.fact_ids) != 1:
            return None
        method = records.get(gap.fact_ids[0])
        if (
            method is None
            or method.kind != "method"
            or method.data.get("module") != module
            or method.data.get("signature_complete") is not False
            or parse_method_kind(method.data.get("method_kind")) is not MethodKind.CONSTRUCTOR
            or module_paths[module][-5:] != ".dart"
            or not isinstance(parameters := method.data.get("parameters"), tuple)
            or not any(
                isinstance(parameter, RecordData)
                and parameter.get("super_formal") is True
                and parameter.get("annotation") is None
                and parameter.get("default_known") is False
                and parameter.get("evidence_ids") == gap.evidence_ids
                for parameter in parameters
            )
        ):
            return None
    return module


def _script_effect_binding(
    gap: Record,
    records: Mapping[str, Record],
    evidence: Mapping[str, Evidence],
    module: str,
    path: str,
) -> bool:
    if (
        len(gap.fact_ids) != 1
        or len(gap.evidence_ids) != 1
        or not path.endswith((".js", ".ts", ".tsx"))
    ):
        return False
    effect = records.get(gap.fact_ids[0])
    location = evidence[gap.evidence_ids[0]]
    return (
        effect is not None
        and effect.id == stable_id("TS_RUNTIME_EFFECT", module, location.line, location.column)
        and gap.id == stable_id("UNKNOWN_RUNTIME_EFFECT", effect.id)
        and effect.kind == "script_namespace_effect"
        and effect.evidence_class == EvidenceClass.FACT
        and effect.subjects == (module,)
        and effect.data.get("source_module") == module
        and effect.data.get("source_scope") == module
        and effect.evidence_ids == gap.evidence_ids
        and effect.data.get("expression") == location.excerpt
        and effect.data.get("status") == SourceResolution.UNRESOLVED
        and effect.data.get("targets") == ()
    )


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
    selected_inputs = {item.path for item in facts.inputs if item.role == _ResolutionRole.SELECTED}
    if not selected_inputs.issubset(selected):
        raise ValueError("selected input is outside selected coverage")
    file_ids = _unique((item.id for item in facts.files), "file id")
    _unique((item.module for item in facts.files), "module identity")
    paths = {item.rel_path for item in facts.files}
    if not paths.issubset(selected_inputs):
        raise ValueError("observed module needs a selected input")
    if len(facts.files) > facts.coverage.files_parsed:
        raise ValueError("observed modules exceed parsed files")
    if facts.profile != SourceProfile.DART and len(facts.files) != facts.coverage.files_parsed:
        raise ValueError("each parsed source file needs an observed module")
    if facts.coverage.full_scope and facts.coverage.files_parsed and not facts.files:
        raise ValueError("complete parsed source needs an observed module")
    evidence_ids = _unique((item.id for item in facts.evidence), "evidence id")
    _unique((item.qualified_name for item in facts.provider_bindings), "provider binding")
    if facts.provider_bindings and facts.profile is not SourceProfile.PYTHON:
        raise ValueError("provider bindings require Python source facts")
    candidate_ids = _unique((item.id for item in facts.candidate_evidence), "candidate evidence id")
    base_by_id = {item.id: item for item in facts.evidence}
    input_by_path = {item.path: item for item in facts.inputs}
    for binding in facts.provider_bindings:
        _unique(binding.supporting_evidence_ids, "provider alias support")
        evidence = base_by_id.get(binding.evidence_id)
        qualified_name: str = binding.qualified_name
        parts = qualified_name.rpartition(".")
        module: str = qualified_name if binding.kind is ProviderBindingKind.MODULE else parts[0]
        name: str = parts[2]
        stem = ".archkeel-providers/" + module.replace(".", "/")
        if (
            binding.kind is ProviderBindingKind.ALIAS
            and (
                binding.target is None
                or not all(part.isidentifier() for part in binding.target.split("."))
            )
            or binding.kind is not ProviderBindingKind.ALIAS
            and (binding.target is not None or binding.supporting_evidence_ids)
        ):
            raise ValueError("provider alias needs a separate qualified target")
        for reference in binding.supporting_evidence_ids:
            support = base_by_id.get(reference)
            if (
                support is None
                or not support.file.startswith(".archkeel-providers/")
                or support.file not in input_by_path
                or input_by_path[support.file].role is not _ResolutionRole.RESOLUTION
            ):
                raise ValueError("provider alias support needs its resolution source")
        if (
            not all(part.isidentifier() for part in module.split("."))
            or not name.isidentifier()
            or module in {item.module for item in facts.files}
            or evidence is None
            or evidence.file not in {stem + ".py", stem + "/__init__.py"}
            or evidence.file not in input_by_path
            or input_by_path[evidence.file].role is not _ResolutionRole.RESOLUTION
        ):
            raise ValueError("provider binding needs its separate resolution source")
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
    for record in records:
        if not set(record.evidence_ids).issubset(evidence_ids):
            raise ValueError("dangling source evidence reference")
    for section in facts.sections:
        for record in section.records:
            _source_record(record, section.name)
            if section.name is SourceSectionName.CONSTRUCTS and record.kind == "numeric_operand":
                operation_span = (
                    record.data.get("line"),
                    record.data.get("column"),
                    record.data.get("end_line"),
                )
                if not all(
                    isinstance(item, int) and not isinstance(item, bool) for item in operation_span
                ):
                    raise ValueError("invalid numeric operand span")
                if not any(
                    (
                        base_by_id[evidence_id].line,
                        base_by_id[evidence_id].column,
                        base_by_id[evidence_id].end_line,
                    )
                    == operation_span
                    for evidence_id in record.evidence_ids
                ):
                    raise ValueError("numeric operand span disagrees with its evidence")
                derivation = record.data.get("derivation")
                if not isinstance(derivation, tuple):
                    raise ValueError("invalid numeric operand derivation")
                for origin in derivation:
                    if not isinstance(origin, RecordData):
                        raise ValueError("invalid numeric operand alias derivation")
                    evidence_id = origin.get("evidence_id")
                    line, column, end_line = (
                        origin.get("line"),
                        origin.get("column"),
                        origin.get("end_line"),
                    )
                    if not isinstance(evidence_id, str) or not all(
                        isinstance(item, int) and not isinstance(item, bool)
                        for item in (line, column, end_line)
                    ):
                        raise ValueError("invalid numeric operand alias derivation")
                    declaration = base_by_id[evidence_id]
                    if (
                        declaration.line,
                        declaration.column,
                        declaration.end_line,
                    ) != (line, column, end_line):
                        raise ValueError("numeric alias derivation disagrees with its evidence")
            construct = record.data.get("construct")
            if construct is not None and not any(
                entry.name == construct and entry.status != ConstructSupport.UNSUPPORTED
                for entry in facts.capabilities.constructs
            ):
                raise ValueError("source construct disagrees with declared capabilities")
    fact_ids = record_ids | file_ids
    for record in records:
        if not set(record.fact_ids).issubset(fact_ids):
            raise ValueError("dangling source fact reference")
    declarations: dict[str, list[Record]] = {}
    for symbol_section in facts.sections:
        if symbol_section.name is not SourceSectionName.SYMBOLS:
            continue
        for symbol in symbol_section.records:
            symbol_name = symbol.data.get("qualified_name")
            if symbol.kind in {"class", "function", "method"} and isinstance(symbol_name, str):
                symbol_declarations: list[Record] = declarations.setdefault(symbol_name, [])
                symbol_declarations.append(symbol)
    for section in facts.sections:
        if section.name is not SourceSectionName.CALLS:
            continue
        for record in section.records:
            if CALL_BINDINGS_FEATURE in facts.capabilities.resolution_features and not any(
                key == "call_binding" for key, _ in record.data.entries
            ):
                raise ValueError("complete call consideration needs explicit binding or null")
            call_proof = call_binding(record.data.get("call_binding"))
            if call_proof is not None and (
                not set(call_proof.evidence_ids) <= evidence_ids
                or not set(record.evidence_ids) <= set(call_proof.evidence_ids)
            ):
                raise ValueError("call binding evidence disagrees with its call")
            targets = record.data.get("targets")
            if call_proof is not None and (
                not isinstance(targets, tuple)
                or call_proof.target not in targets
                or call_proof.origin is CallBindingOrigin.DIRECT
                and record.data.get("status") != SourceResolution.RESOLVED
                or not set(_call_declaration(call_proof, declarations).evidence_ids)
                & set(call_proof.evidence_ids)
            ):
                raise ValueError("call binding disagrees with its target declaration")
    record_by_id = {record.id: record for record in records}
    effects = [record for record in records if record.kind == "script_namespace_effect"]
    effect_gaps = [
        gap
        for gap in facts.coverage.gaps
        if gap.data.get("resolution_dimension") == "runtime_effects"
    ]
    script_effects = (
        facts.profile == SourceProfile.TYPESCRIPT
        and "script-globals-v1" in facts.capabilities.resolution_features
    )
    if effects and not script_effects:
        raise ValueError("script effects require the registered TypeScript script profile")
    validate_source_bindings(
        effect_gaps,
        {item.module: item.rel_path for item in facts.files},
        {},
        base_by_id,
        import_ids=(),
        selected_inputs=selected_inputs,
        source_records=record_by_id,
        allow_script_effects=script_effects,
    )
    _property_bindings(records, base_by_id)
    _contextmanager_signatures(facts, records, base_by_id, input_by_path)
    _member_inventory_bindings(records)
    for gap in facts.coverage.gaps:
        _source_record(gap, SourceSectionName.UNKNOWNS)
        if gap.evidence_class != EvidenceClass.UNKNOWN:
            raise ValueError("coverage gap must be UNKNOWN")
        if gap.id not in record_by_id or record_by_id[gap.id] != gap:
            raise ValueError("coverage gap must reference its source UNKNOWN record")
    imports = {
        record.id
        for section in facts.sections
        if section.name == SourceSectionName.IMPORTS
        for record in section.records
    }
    target_ids = _unique((target.import_id for target in facts.imports), "import target")
    if target_ids != imports:
        raise ValueError("each import needs exactly one typed target")
    file_by_module = {item.module: item for item in facts.files}
    validate_source_bindings(
        (
            record
            for section in facts.sections
            if section.name != SourceSectionName.UNKNOWNS
            for record in section.records
        ),
        {item.module: item.rel_path for item in facts.files},
        {item.module: item.package for item in facts.files},
        base_by_id,
        import_ids=imports,
        selected_inputs=selected_inputs,
        allow_part_evidence=facts.profile == SourceProfile.DART,
    )
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
