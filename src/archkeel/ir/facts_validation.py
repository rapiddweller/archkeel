# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Cross-reference and source-payload invariants of the collection protocol."""

import ast
from collections.abc import Collection, Iterable, Mapping
from functools import lru_cache
from pathlib import PurePosixPath

from .facts import (
    CALL_ARGUMENTS_FEATURE,
    CALL_BINDINGS_FEATURE,
    EXTENDED_CALL_BINDINGS_FEATURE,
    MAX_NUMERIC_EVIDENCE_CHARS,
    MAX_STATIC_INTEGER,
    NATIVE_CALL_TARGETS,
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
    call_arguments,
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
        "selector_role",
        "operation",
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
        "receiver_type",
        "receiver_parameter",
        "member",
        "literal",
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


def _annotation_class_origin(
    initializer: Record,
    parameter: RecordData,
    facts: SourceFacts,
    declarations: Mapping[str, list[Record]],
) -> str | None:
    annotation = parameter.get("annotation")
    module = initializer.data.get("module")
    if not isinstance(annotation, str) or not annotation or not isinstance(module, str):
        return None
    records = [record for section in facts.sections for record in section.records]
    imported = _signature_origin(initializer.data, annotation, records, facts)
    candidates = (imported,) if imported is not None else (f"{module}.{annotation}",)
    matches = [
        target
        for target in candidates
        if target is not None
        and len(declarations.get(target, ())) == 1
        and declarations[target][0].kind == "class"
    ]
    return matches[0] if len(matches) == 1 else None


# Shared with bounded numeric source validation: selector ingress uses the same
# single-line, size-limited excerpt parser and AST span mapping rather than a scanner.
@lru_cache(maxsize=256)
def _parse_numeric_evidence_excerpt(
    excerpt: str,
) -> tuple[tuple[ast.stmt, ...], int] | None:
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS or "\n" in excerpt:
        return None
    try:
        return tuple(ast.parse(excerpt).body), 0
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        try:
            wrapper = ast.parse(f"if True:\n{excerpt}\n")
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            return None
        if not wrapper.body or not isinstance(wrapper.body[0], ast.If):
            return None
        return tuple(wrapper.body[0].body), 1


def _numeric_node_span(
    node: ast.AST, source_line: int, line_offset: int
) -> tuple[int, int, int, int] | None:
    if not isinstance(node, ast.stmt | ast.expr):
        return None
    if node.end_lineno is None or node.end_col_offset is None:
        return None
    return (
        node.lineno - line_offset + source_line - 1,
        node.col_offset,
        node.end_lineno - line_offset + source_line - 1,
        node.end_col_offset,
    )


def _selector_evidence_excerpt(
    item: Evidence, role: object
) -> tuple[tuple[ast.stmt, ...], int] | None:
    parsed = _parse_numeric_evidence_excerpt(item.excerpt)
    if parsed is not None or role != "match" or not item.excerpt.rstrip().endswith(":"):
        return parsed
    indentation = len(item.excerpt) - len(item.excerpt.lstrip(" "))
    body = " " * (indentation + 4) + "case _: pass"
    try:
        wrapper = ast.parse(f"if True:\n{item.excerpt}\n{body}\n")
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    if not wrapper.body or not isinstance(wrapper.body[0], ast.If):
        return None
    return tuple(wrapper.body[0].body), 1


def _selector_source_receiver(
    record: Record, binding: CallBinding, evidence: Mapping[str, Evidence]
) -> ast.expr | None:
    site_ids = set(record.evidence_ids) - set(binding.evidence_ids)
    for identifier in site_ids:
        item = evidence.get(identifier)
        if item is None:
            continue
        parsed = _selector_evidence_excerpt(item, record.data.get("selector_role"))
        if parsed is None:
            continue
        roots, offset = parsed
        nodes = [node for root in roots for node in ast.walk(root)]
        anchored = [
            node
            for node in nodes
            if (span := _numeric_node_span(node, item.line, offset)) is not None
            and span[0] == item.line
            and span[1] == item.column
        ]
        role, member = record.data.get("selector_role"), record.data.get("member")
        selected: ast.expr | None = None
        if role == "match":
            selected = next(
                (
                    node.subject.value
                    for node in anchored
                    if isinstance(node, ast.Match) and isinstance(node.subject, ast.Attribute)
                ),
                None,
            )
        elif role == "reflect":
            selected = next(
                (node.args[0] for node in anchored if isinstance(node, ast.Call) and node.args),
                None,
            )
        elif role in {"startswith", "endswith"}:
            selected = next(
                (
                    node.func.value.value
                    if isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Attribute)
                    else node.func.value
                    for node in anchored
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                ),
                None,
            )
        elif role in {"read", "write", "call", "equality", "membership"}:
            attribute = next(
                (
                    node
                    for node in nodes
                    if isinstance(node, ast.Attribute)
                    and node.attr == member
                    and (span := _numeric_node_span(node, item.line, offset)) is not None
                    and span[0] == item.line
                    and span[1] >= item.column
                ),
                None,
            )
            if attribute is None:
                attribute = next(
                    (node for node in anchored if isinstance(node, ast.Attribute)), None
                )
            selected = attribute.value if attribute is not None else None
        if selected is not None:
            return selected
    return None


def _selector_source_class(
    record: Record, binding: CallBinding, evidence: Mapping[str, Evidence]
) -> ast.expr | None:
    for identifier in set(record.evidence_ids) - set(binding.evidence_ids):
        item = evidence.get(identifier)
        parsed = (
            _selector_evidence_excerpt(item, record.data.get("selector_role"))
            if item is not None
            else None
        )
        if item is None or parsed is None:
            continue
        roots, offset = parsed
        for root in roots:
            for node in ast.walk(root):
                span = _numeric_node_span(node, item.line, offset)
                if span is None or span[:2] != (item.line, item.column):
                    continue
                if record.data.get("selector_role") == "constructor" and isinstance(node, ast.Call):
                    return node.func
                if (
                    record.data.get("selector_role") == "type_probe"
                    and isinstance(node, ast.Call)
                    and len(node.args) > 1
                ):
                    return node.args[1]
    return None


def _selector_receiver_site_matches(
    record: Record,
    binding: CallBinding,
    receiver_parameter: str | None,
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> bool:
    if binding.origin is CallBindingOrigin.DIRECT:
        target = _selector_source_class(record, binding, evidence)
        return (
            target is not None
            and ast.unparse(target).split(".")[-1] == binding.target.split(".")[-1]
        )
    expression = _selector_source_receiver(record, binding, evidence)
    if binding.origin is CallBindingOrigin.DECLARED_RECEIVER:
        return isinstance(expression, ast.Name) and expression.id == receiver_parameter
    proof = binding.proof
    if binding.origin is CallBindingOrigin.STORED_RECEIVER and proof is not None:
        owner = proof.get("owner")
        selector_owner = record.data.get("owner")
        initializers = declarations.get(f"{owner}.__init__", []) if isinstance(owner, str) else []
        receiver = (
            initializers[0].data.get("receiver_parameter") if len(initializers) == 1 else None
        )
        return (
            isinstance(owner, str)
            and isinstance(selector_owner, str)
            and selector_owner.startswith(f"{owner}.")
            and isinstance(expression, ast.Attribute)
            and expression.attr == proof.get("field")
            and isinstance(expression.value, ast.Name)
            and isinstance(receiver, str)
            and expression.value.id == receiver
        )
    if binding.origin is CallBindingOrigin.CONSTRUCTED_RECEIVER and proof is not None:
        assignment_name = proof.get("assignment_name")
        if isinstance(assignment_name, str):
            return isinstance(expression, ast.Name) and expression.id == assignment_name
        constructor_id = proof.get("constructor_evidence_id")
        constructor = evidence.get(constructor_id) if isinstance(constructor_id, str) else None
        return (
            isinstance(expression, ast.Call)
            and constructor is not None
            and expression.lineno == constructor.line
            and expression.col_offset == constructor.column
        )
    return expression is not None


def _selector_receiver_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding | None,
    receiver_parameter: str | None,
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> None:
    receiver_type = record.data.get("receiver_type")
    if binding is None:
        if receiver_type is not None:
            raise ValueError("known selector receiver needs its typed source binding")
        return
    if (
        binding.target != receiver_type
        or not set(binding.evidence_ids) <= set(record.evidence_ids)
        or not set(binding.evidence_ids) <= set(evidence)
    ):
        raise ValueError("selector receiver binding evidence disagrees with its source fact")
    if binding.origin in {
        CallBindingOrigin.DIRECT,
        CallBindingOrigin.DECLARED_RECEIVER,
        CallBindingOrigin.STORED_RECEIVER,
        CallBindingOrigin.CONSTRUCTED_RECEIVER,
    } and not _selector_receiver_site_matches(
        record, binding, receiver_parameter, declarations, evidence
    ):
        raise ValueError("selector receiver proof does not match its source expression")
    targets = declarations.get(binding.target, [])
    if binding.origin is CallBindingOrigin.DIRECT:
        _selector_direct_receiver_proof(binding, receiver_parameter, targets)
        return
    if binding.origin is CallBindingOrigin.DECLARED_RECEIVER:
        _selector_declared_receiver_proof(
            facts, record, binding, receiver_parameter, declarations, targets
        )
        return
    proof = binding.proof
    if proof is None:
        raise ValueError("extended selector receiver needs its typed origin proof")
    if binding.origin is CallBindingOrigin.STORED_RECEIVER:
        _selector_stored_receiver_proof(facts, binding, declarations, targets)
        return
    if binding.origin is CallBindingOrigin.CONSTRUCTED_RECEIVER:
        _selector_constructed_receiver_proof(facts, record, binding, proof, targets, evidence)
        return
    raise ValueError("selector receiver origin is unsupported")


def _selector_direct_receiver_proof(
    binding: CallBinding, receiver_parameter: str | None, targets: list[Record]
) -> None:
    if (
        receiver_parameter is not None
        or len(targets) != 1
        or targets[0].kind != "class"
        or targets[0].data.get("source_binding_unique") is not True
        or not set(targets[0].evidence_ids) <= set(binding.evidence_ids)
    ):
        raise ValueError("selector class receiver needs its stable declaration")


def _selector_declared_receiver_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    receiver_parameter: str | None,
    declarations: Mapping[str, list[Record]],
    targets: list[Record],
) -> None:
    owner_name = record.data.get("owner")
    owners = declarations.get(owner_name, []) if isinstance(owner_name, str) else []
    parameters = owners[0].data.get("parameters") if len(owners) == 1 else None
    selected = (
        [
            item
            for item in parameters
            if isinstance(item, RecordData) and item.get("name") == receiver_parameter
        ]
        if isinstance(parameters, tuple)
        else []
    )
    annotation_target = (
        _annotation_class_origin(owners[0], selected[0], facts, declarations)
        if len(owners) == 1 and len(selected) == 1
        else None
    )
    if (
        len(owners) != 1
        or owners[0].kind not in {"function", "method"}
        or receiver_parameter is None
        or len(selected) != 1
        or annotation_target != binding.target
        or len(targets) != 1
        or targets[0].kind != "class"
        or targets[0].data.get("source_binding_unique") is not True
        or not set(owners[0].evidence_ids) <= set(binding.evidence_ids)
        or not set(targets[0].evidence_ids) <= set(binding.evidence_ids)
    ):
        raise ValueError("declared selector receiver needs its exact typed parameter proof")


def _selector_stored_receiver_proof(
    facts: SourceFacts,
    binding: CallBinding,
    declarations: Mapping[str, list[Record]],
    targets: list[Record],
) -> None:
    proof = binding.proof
    if proof is None:
        raise ValueError("stored selector receiver needs its typed origin proof")
    owner_name, field = proof.get("owner"), proof.get("field")
    parameter_name, witnesses = proof.get("parameter"), proof.get("witness_evidence_ids")
    owners = declarations.get(owner_name, []) if isinstance(owner_name, str) else []
    initializers = (
        declarations.get(f"{owner_name}.__init__", []) if isinstance(owner_name, str) else []
    )
    writes = initializers[0].data.get("stored_field_writes") if len(initializers) == 1 else None
    witness_ids = witnesses if isinstance(witnesses, tuple) else ()
    linked = (
        [
            item
            for item in writes
            if isinstance(item, RecordData)
            and item.get("field") == field
            and item.get("parameter") == parameter_name
            and item.get("evidence_id") == (witness_ids[0] if witness_ids else None)
            and len(witness_ids) == 2
            and item.get("annotation_evidence_id") == witness_ids[1]
            and item.get("receiver") == initializers[0].data.get("receiver_parameter")
            and item.get("annotation_target") == binding.target
        ]
        if isinstance(writes, tuple)
        else []
    )
    parameters = initializers[0].data.get("parameters") if len(initializers) == 1 else None
    typed = (
        [
            item
            for item in parameters
            if isinstance(item, RecordData)
            and item.get("name") == parameter_name
            and isinstance(item.get("annotation"), str)
        ]
        if isinstance(parameters, tuple)
        else []
    )
    annotation_target = (
        _annotation_class_origin(initializers[0], typed[0], facts, declarations)
        if len(initializers) == 1 and len(typed) == 1
        else None
    )
    if (
        proof.get("kind") != "stored_field"
        or proof.get("target") != binding.target
        or len(owners) != 1
        or owners[0].kind != "class"
        or owners[0].data.get("source_binding_unique") is not True
        or len(initializers) != 1
        or len(linked) != 1
        or len(typed) != 1
        or annotation_target != binding.target
        or not isinstance(witnesses, tuple)
        or len(witnesses) != 2
        or not set(witnesses) <= set(binding.evidence_ids)
        or len(targets) != 1
        or targets[0].kind != "class"
        or targets[0].data.get("source_binding_unique") is not True
        or not set(owners[0].evidence_ids) <= set(binding.evidence_ids)
        or not set(targets[0].evidence_ids) <= set(binding.evidence_ids)
    ):
        raise ValueError("stored selector receiver needs a linked initializer annotation")


def _selector_constructed_receiver_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    proof: RecordData,
    targets: list[Record],
    evidence: Mapping[str, Evidence],
) -> None:
    constructor_id = proof.get("constructor_evidence_id")
    assignment_id, assignment_name = (
        proof.get("assignment_evidence_id"),
        proof.get("assignment_name"),
    )
    target_calls = [
        candidate
        for section in facts.sections
        if section.name is SourceSectionName.CALLS
        for candidate in section.records
        if isinstance(constructor_id, str)
        and constructor_id in candidate.evidence_ids
        and candidate.kind.endswith("_call")
        and isinstance(candidate_targets := candidate.data.get("targets"), tuple)
        and binding.target in candidate_targets
    ]
    selector_evidence = [
        evidence[item]
        for item in record.evidence_ids
        if item not in binding.evidence_ids and item in evidence
    ]
    linked_assignments = _selector_linked_assignments(
        facts, constructor_id, assignment_id, assignment_name
    )
    assignment_evidence = evidence.get(assignment_id) if isinstance(assignment_id, str) else None
    if (
        proof.get("kind") != "construction"
        or proof.get("target") != binding.target
        or len(targets) != 1
        or targets[0].kind != "class"
        or targets[0].data.get("default_instance_result") is not True
        or not isinstance(constructor_id, str)
        or len(target_calls) != 1
        or not selector_evidence
        or assignment_id is not None
        and (
            not isinstance(assignment_name, str)
            or len(linked_assignments) != 1
            or linked_assignments[0][0].data.get("source_scope") != record.data.get("owner")
            or assignment_evidence is None
            or assignment_evidence.line >= max(item.line for item in selector_evidence)
            or not isinstance(assignment_id, str)
            or assignment_id not in binding.evidence_ids
        )
        or assignment_id is None
        and assignment_name is not None
        or not set(targets[0].evidence_ids) <= set(binding.evidence_ids)
    ):
        raise ValueError("constructed selector receiver needs its linked allocation witness")


def _selector_linked_assignments(
    facts: SourceFacts, constructor_id: object, assignment_id: object, assignment_name: object
) -> list[tuple[Record, RecordData]]:
    linked: list[tuple[Record, RecordData]] = []
    if not isinstance(constructor_id, str) or not isinstance(assignment_id, str):
        return linked
    for section in facts.sections:
        if section.name is not SourceSectionName.CALLS:
            continue
        for candidate in section.records:
            if constructor_id not in candidate.evidence_ids:
                continue
            bindings = candidate.data.get("result_bindings")
            if not isinstance(bindings, tuple):
                continue
            for item in bindings:
                ids = item.get("evidence_ids") if isinstance(item, RecordData) else None
                if (
                    isinstance(item, RecordData)
                    and item.get("name") == assignment_name
                    and item.get("target_kind") == "name"
                    and isinstance(ids, tuple)
                    and assignment_id in ids
                ):
                    linked.append((candidate, item))
    return linked


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


def _call_declaration(
    binding: CallBinding, declarations: Mapping[str, list[Record]]
) -> Record | None:
    if binding.origin in {CallBindingOrigin.NATIVE, CallBindingOrigin.NATIVE_RECEIVER}:
        if binding.target not in NATIVE_CALL_TARGETS:
            raise ValueError("native call needs an admitted runtime identity")
        return None
    if binding.origin is CallBindingOrigin.CONSTRUCTOR and binding.target == "random.Random":
        if len(binding.evidence_ids) < 2:
            raise ValueError("native constructor needs an import witness")
        return None
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
    elif binding.origin is CallBindingOrigin.CONSTRUCTOR:
        if (
            target.kind != "class"
            or target.data.get("source_binding_unique") is not True
            or target.data.get("class_header_static") is not True
            or target.data.get("default_instance_result") is not True
        ):
            raise ValueError("constructor call needs a stable default instance identity")
    else:
        parent = target.data.get("parent")
        owners = declarations.get(parent, []) if isinstance(parent, str) else []
        if target.kind != "method" or len(owners) != 1 or target.data.get("decorators"):
            raise ValueError("declared receiver needs a plain method and class owner")
        [owner] = owners
        stable_owner = owner.data.get("source_binding_unique") is True and (
            owner.data.get("source_member_binding_static") is True
            if binding.origin
            in {
                CallBindingOrigin.DECLARED_RECEIVER,
                CallBindingOrigin.STORED_RECEIVER,
            }
            else owner.data.get("class_header_static") is True
            and owner.data.get("default_instance_result") is True
        )
        if (
            owner.kind != "class"
            or not stable_owner
            or not set(owner.evidence_ids) <= set(binding.evidence_ids)
        ):
            raise ValueError("declared receiver needs a stable class binding")
    return target


def _native_call_witness(facts: SourceFacts, binding: CallBinding) -> None:
    """Require a canonical import and captured provider/runtime witness for native calls."""
    if (
        binding.origin
        not in {
            CallBindingOrigin.NATIVE,
            CallBindingOrigin.NATIVE_RECEIVER,
            CallBindingOrigin.CONSTRUCTOR,
        }
        or binding.target not in NATIVE_CALL_TARGETS
    ):
        return
    evidence = set(binding.evidence_ids)
    proof = binding.proof
    if proof is None:
        raise ValueError("native call needs its typed witness")
    if proof.get("target") != binding.target:
        raise ValueError("native witness target disagrees with its call")
    if (
        proof.get("runtime_name") != facts.runtime.name
        or proof.get("runtime_version") != facts.runtime.version
    ):
        raise ValueError("native witness runtime identity disagrees with the source snapshot")
    imported_targets: set[str] = set()
    for section in facts.sections:
        if section.name is not SourceSectionName.IMPORTS:
            continue
        for imported in section.records:
            if not evidence.intersection(imported.evidence_ids):
                continue
            module = imported.data.get("target_module")
            symbol = imported.data.get("symbol")
            if isinstance(module, str):
                imported_targets.add(module + (f".{symbol}" if isinstance(symbol, str) else ""))
    if not any(
        binding.target == target
        or binding.target.startswith(target + ".")
        or target.startswith(binding.target + ".")
        for target in imported_targets
    ):
        raise ValueError("native call needs its matching stable import evidence")
    if binding.target.startswith(("random.", "secrets.")):
        provider = next(
            (item for item in facts.provider_bindings if item.qualified_name == binding.target),
            None,
        )
        provider_reference = proof.get("provider_evidence_id")
        if (
            provider is None
            or provider.evidence_id not in evidence
            or provider_reference != provider.evidence_id
        ):
            raise ValueError("native call needs its exact captured provider member declaration")
    elif binding.target == "datetime.datetime.now":
        module_digest = proof.get("stdlib_source_digest")
        source_inputs = [
            item
            for item in facts.inputs
            if item.path == ".archkeel-providers/datetime.py"
            and item.role is _ResolutionRole.RESOLUTION
        ]
        if (
            facts.runtime.name != "python"
            or not facts.runtime.version
            or proof.get("runtime_implementation") != "cpython"
            or proof.get("descriptor_owner_module") != "datetime"
            or proof.get("descriptor_owner_qualname") != "datetime"
            or proof.get("descriptor_member") != "now"
            or proof.get("descriptor_kind") != "classmethod_descriptor"
            or not isinstance(module_digest, str)
            or len(source_inputs) != 1
            or source_inputs[0].digest != module_digest
        ):
            raise ValueError("datetime native call needs its observed stdlib descriptor witness")


def _stored_method_path(
    receiver_type: str,
    target: str,
    declarations: Mapping[str, list[Record]],
) -> tuple[bool, tuple[str, ...]]:
    method_name = target.rpartition(".")[2]
    current = receiver_type
    seen: set[str] = set()
    path_evidence: set[str] = set()
    while current not in seen:
        seen.add(current)
        owners = declarations.get(current, [])
        if len(owners) != 1 or owners[0].kind != "class":
            return False, ()
        owner = owners[0]
        path_evidence.update(owner.evidence_ids)
        if declarations.get(f"{current}.__getattribute__") or declarations.get(
            f"{current}.__getattr__"
        ):
            return False, ()
        methods = declarations.get(f"{current}.{method_name}", [])
        if methods:
            if (
                len(methods) != 1
                or methods[0].kind != "method"
                or methods[0].data.get("parent") != current
                or methods[0].data.get("decorators")
                or methods[0].data.get("qualified_name") != target
            ):
                return False, ()
            return True, tuple(sorted(path_evidence | set(methods[0].evidence_ids)))
        if owner.data.get("class_header_static") is not True:
            return False, ()
        attributes = owner.data.get("attribute_declarations")
        if isinstance(attributes, tuple) and any(
            isinstance(attribute, RecordData) and attribute.get("name") == method_name
            for attribute in attributes
        ):
            return False, ()
        bases = owner.data.get("base_declarations")
        if not isinstance(bases, tuple) or len(bases) != 1 or not isinstance(bases[0], RecordData):
            return False, ()
        base = bases[0]
        base_targets = base.get("targets")
        base_evidence = base.get("evidence_ids")
        if (
            base.get("status") != SourceResolution.RESOLVED
            or not isinstance(base_targets, tuple)
            or len(base_targets) != 1
            or not isinstance(base_targets[0], str)
            or not isinstance(base_evidence, tuple)
            or any(not isinstance(item, str) for item in base_evidence)
        ):
            return False, ()
        path_evidence.update(item for item in base_evidence if isinstance(item, str))
        current = base_targets[0]
    return False, ()


def _call_origin_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> None:
    proof = binding.proof
    if proof is None:
        if binding.origin in {
            CallBindingOrigin.STORED_RECEIVER,
            CallBindingOrigin.CONSTRUCTED_RECEIVER,
            CallBindingOrigin.CONSTRUCTOR,
            CallBindingOrigin.NATIVE,
            CallBindingOrigin.NATIVE_RECEIVER,
        }:
            raise ValueError("extended call binding needs its typed origin proof")
        return
    if proof.get("runtime_name") is not None and (
        proof.get("runtime_name") != facts.runtime.name
        or proof.get("runtime_version") != facts.runtime.version
    ):
        raise ValueError("call proof runtime identity disagrees with the source snapshot")
    if binding.origin is CallBindingOrigin.STORED_RECEIVER:
        owner_name = proof.get("owner")
        field = proof.get("field")
        parameter = proof.get("parameter")
        target = proof.get("target")
        witnesses = proof.get("witness_evidence_ids")
        owners = declarations.get(owner_name, []) if isinstance(owner_name, str) else []
        initializers = (
            declarations.get(f"{owner_name}.__init__", []) if isinstance(owner_name, str) else []
        )
        stored_types = declarations.get(target, []) if isinstance(target, str) else []
        target_declarations = declarations.get(binding.target, [])
        write_evidence = witnesses[0] if isinstance(witnesses, tuple) and witnesses else None
        typed_writes = (
            initializers[0].data.get("stored_field_writes")
            if len(initializers) == 1 and initializers[0].kind == "method"
            else None
        )
        linked_writes = (
            [
                item
                for item in typed_writes
                if isinstance(item, RecordData)
                and item.get("field") == field
                and item.get("parameter") == parameter
                and item.get("evidence_id") == write_evidence
                and isinstance(witnesses, tuple)
                and len(witnesses) == 2
                and item.get("annotation_evidence_id") == witnesses[1]
                and isinstance(owner_name, str)
                and item.get("receiver") == initializers[0].data.get("receiver_parameter")
            ]
            if isinstance(typed_writes, tuple)
            else []
        )
        parameters = initializers[0].data.get("parameters") if len(initializers) == 1 else None
        typed_parameters = (
            [
                item
                for item in parameters
                if isinstance(item, RecordData)
                and item.get("name") == parameter
                and isinstance(item.get("annotation"), str)
            ]
            if isinstance(parameters, tuple)
            else []
        )
        matches_receiver_path, receiver_path_evidence = (
            _stored_method_path(target, binding.target, declarations)
            if isinstance(target, str)
            else (False, ())
        )
        annotation_target = (
            _annotation_class_origin(initializers[0], typed_parameters[0], facts, declarations)
            if len(initializers) == 1 and len(typed_parameters) == 1
            else None
        )
        if (
            not isinstance(field, str)
            or not field.isidentifier()
            or not isinstance(parameter, str)
            or not parameter.isidentifier()
            or len(owners) != 1
            or owners[0].kind != "class"
            or owners[0].data.get("source_binding_unique") is not True
            or owners[0].data.get("source_member_binding_static") is not True
            or len(initializers) != 1
            or len(linked_writes) != 1
            or linked_writes[0].get("annotation_target") != target
            or annotation_target != target
            or len(typed_parameters) != 1
            or len(stored_types) != 1
            or stored_types[0].kind != "class"
            or stored_types[0].data.get("source_binding_unique") is not True
            or stored_types[0].data.get("source_member_binding_static") is not True
            or not matches_receiver_path
            or not set(receiver_path_evidence) <= set(binding.evidence_ids)
            or not isinstance(witnesses, tuple)
            or len(witnesses) != 2
            or any(
                not isinstance(item, str)
                or item not in evidence
                or evidence[item].file not in facts.coverage.selected_files
                for item in witnesses
            )
        ):
            raise ValueError("stored receiver needs a linked initializer and annotation witness")
        if len(target_declarations) != 1 or target_declarations[0].kind != "method":
            raise ValueError("stored receiver needs one canonical method declaration")
    elif binding.origin is CallBindingOrigin.CONSTRUCTED_RECEIVER:
        target = proof.get("target")
        constructors = proof.get("constructor_evidence_id")
        assignment = proof.get("assignment_evidence_id")
        targets = declarations.get(target, []) if isinstance(target, str) else []
        target_name = target if isinstance(target, str) else ""
        constructor_id = constructors if isinstance(constructors, str) else ""
        assignment_id = assignment if isinstance(assignment, str) else ""

        def result_bindings(candidate: Record) -> tuple[RecordData, ...]:
            value = candidate.data.get("result_bindings")
            return (
                tuple(item for item in value if isinstance(item, RecordData))
                if isinstance(value, tuple)
                else ()
            )

        def has_assignment_evidence(item: RecordData) -> bool:
            value = item.get("evidence_ids")
            return isinstance(value, tuple) and assignment_id in value

        def has_target(candidate: Record) -> bool:
            value = candidate.data.get("targets")
            return isinstance(value, tuple) and target_name in value

        constructor_calls = [
            candidate
            for section in facts.sections
            if section.name is SourceSectionName.CALLS
            for candidate in section.records
            if constructor_id in candidate.evidence_ids
            and candidate.kind.endswith("_call")
            and has_target(candidate)
        ]
        assignment_name = proof.get("assignment_name")
        linked_assignments = [
            (candidate, item)
            for section in facts.sections
            if section.name is SourceSectionName.CALLS
            for candidate in section.records
            if constructor_id in candidate.evidence_ids
            for item in result_bindings(candidate)
            if item.get("name") == assignment_name
            and item.get("target_kind") == "name"
            and has_assignment_evidence(item)
        ]
        call_evidence = evidence.get(record.evidence_ids[0]) if record.evidence_ids else None
        assignment_evidence = evidence.get(assignment_id) if assignment_id else None
        if (
            len(targets) != 1
            or targets[0].kind != "class"
            or targets[0].data.get("default_instance_result") is not True
            or not isinstance(constructors, str)
            or len(constructor_calls) != 1
            or assignment is not None
            and (
                not isinstance(assignment_name, str)
                or len(linked_assignments) != 1
                or linked_assignments[0][0].data.get("source_scope")
                != record.data.get("source_scope")
                or call_evidence is None
                or assignment_evidence is None
                or assignment_evidence.line >= call_evidence.line
            )
            or assignment is None
            and assignment_name is not None
            or assignment is not None
            and (
                not assignment_id
                or assignment_evidence is None
                or assignment_evidence.file not in facts.coverage.selected_files
            )
        ):
            raise ValueError("constructed receiver needs a linked earlier allocation witness")
    elif binding.origin is CallBindingOrigin.CONSTRUCTOR:
        if proof.get("kind") == "provider_member":
            return
        target = proof.get("target")
        constructor_evidence = proof.get("constructor_evidence_id")
        targets = declarations.get(target, []) if isinstance(target, str) else []
        if (
            len(targets) != 1
            or targets[0].kind != "class"
            or targets[0].data.get("default_instance_result") is not True
            or not isinstance(constructor_evidence, str)
            or constructor_evidence not in record.evidence_ids
        ):
            raise ValueError("constructor needs its default-instance declaration and call witness")


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
    if record.kind == "construct_selector":
        selector_required = {
            "owner",
            "construct",
            "selector_role",
            "receiver_type",
            "member",
            "literal",
            "status",
            "operation",
            "receiver_binding",
            "receiver_parameter",
        }
        if section is not SourceSectionName.CONSTRUCTS or fields != selector_required:
            raise ValueError("construct selector facts need the closed selector payload")
        if record.data.get("construct") != "selector":
            raise ValueError("construct selector facts need selector construct identity")
        if record.data.get("selector_role") not in {
            "read",
            "write",
            "call",
            "reflect",
            "constructor",
            "type_probe",
            "equality",
            "membership",
            "match",
            "startswith",
            "endswith",
        }:
            raise ValueError("construct selector role is unsupported")
        if record.data.get("status") not in {"decided", "unknown"}:
            raise ValueError("construct selector status is unsupported")
        if record.data.get("operation") not in {
            "read",
            "write",
            "call",
            "probe",
            "compare",
            "construct",
        }:
            raise ValueError("construct selector operation is unsupported")
        role = record.data.get("selector_role")
        operation = record.data.get("operation")
        if not isinstance(role, str) or not isinstance(operation, str):
            raise ValueError("construct selector role and operation must be strings")
        expected_operation = {
            "read": "read",
            "write": "write",
            "call": "call",
            "reflect": "probe",
            "constructor": "construct",
            "type_probe": "probe",
            "equality": "compare",
            "membership": "compare",
            "match": "compare",
            "startswith": "compare",
            "endswith": "compare",
        }[role]
        if operation != expected_operation:
            raise ValueError("construct selector role and operation disagree")
        member_roles = {
            "read",
            "write",
            "call",
            "reflect",
            "equality",
            "membership",
            "match",
            "startswith",
            "endswith",
        }
        if role in member_roles and record.data.get("member") is None:
            if record.data.get("status") != "unknown":
                raise ValueError("known construct selector needs a member")
        elif role not in member_roles and record.data.get("member") is not None:
            raise ValueError("construct selector role cannot carry a member")
        if role not in {"equality", "membership", "match", "startswith", "endswith"} and (
            record.data.get("literal") is not None
        ):
            raise ValueError("construct selector role cannot carry a literal")
        if record.data.get("status") == "decided" and record.data.get("receiver_type") is None:
            raise ValueError("decided construct selector needs a receiver type")
        receiver_binding = call_binding(record.data.get("receiver_binding"))
        receiver_type = record.data.get("receiver_type")
        receiver_parameter = record.data.get("receiver_parameter")
        if receiver_binding is not None and (
            receiver_binding.target != receiver_type
            or receiver_parameter is not None
            and receiver_binding.origin is not CallBindingOrigin.DECLARED_RECEIVER
        ):
            raise ValueError("construct selector receiver binding disagrees with its receiver")
        if receiver_parameter is not None and (
            not isinstance(receiver_parameter, str)
            or not receiver_parameter.isidentifier()
            or receiver_binding is None
            or receiver_binding.origin is not CallBindingOrigin.DECLARED_RECEIVER
        ):
            raise ValueError("declared selector receiver needs its parameter identity")
        if receiver_type is not None and receiver_binding is None:
            raise ValueError("known construct selector needs a linked receiver binding")
        if (
            role in {"equality", "membership", "match", "startswith", "endswith"}
            and record.data.get("status") == "decided"
            and record.data.get("literal") is None
        ):
            raise ValueError("decided comparison selector needs a literal")
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
    if any(key == "call_arguments" for key in fields):
        if section is not SourceSectionName.CALLS:
            raise ValueError("call arguments need their call owner")
        call_arguments(record.data.get("call_arguments"))
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
        native_member = qualified_name in NATIVE_CALL_TARGETS and qualified_name.count(".") > 1
        module: str = (
            qualified_name
            if binding.kind is ProviderBindingKind.MODULE
            else qualified_name.split(".", 1)[0]
            if native_member
            else parts[0]
        )
        name: str = qualified_name.split(".", 1)[1] if native_member else parts[2]
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
            or not all(part.isidentifier() for part in name.split("."))
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
            if (
                construct is not None
                and record.kind != "construct_selector"
                and not any(
                    entry.name == construct and entry.status != ConstructSupport.UNSUPPORTED
                    for entry in facts.capabilities.constructs
                )
            ):
                raise ValueError("source construct disagrees with declared capabilities")
    fact_ids = record_ids | file_ids
    for record in records:
        if not set(record.evidence_ids).issubset(evidence_ids):
            raise ValueError("dangling source evidence reference")
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
            argument_field = any(key == "call_arguments" for key, _ in record.data.entries)
            if (
                CALL_ARGUMENTS_FEATURE in facts.capabilities.resolution_features
                and not argument_field
            ):
                raise ValueError("complete call consideration needs explicit arguments")
            if (
                argument_field
                and CALL_ARGUMENTS_FEATURE not in facts.capabilities.resolution_features
            ):
                raise ValueError("call arguments require their declared capability")
            arguments = call_arguments(record.data.get("call_arguments"))
            if arguments is not None and not all(
                set(argument.evidence_ids) <= evidence_ids for argument in arguments
            ):
                raise ValueError("call argument evidence disagrees with its source")
            if CALL_BINDINGS_FEATURE in facts.capabilities.resolution_features and not any(
                key == "call_binding" for key, _ in record.data.entries
            ):
                raise ValueError("complete call consideration needs explicit binding or null")
            call_proof = call_binding(record.data.get("call_binding"))
            if (arguments is None) != (call_proof is None):
                raise ValueError("call arguments require the canonical call binding")
            if (
                call_proof is not None
                and call_proof.origin
                in {
                    CallBindingOrigin.STORED_RECEIVER,
                    CallBindingOrigin.CONSTRUCTED_RECEIVER,
                    CallBindingOrigin.CONSTRUCTOR,
                    CallBindingOrigin.NATIVE,
                    CallBindingOrigin.NATIVE_RECEIVER,
                }
                and EXTENDED_CALL_BINDINGS_FEATURE not in facts.capabilities.resolution_features
            ):
                raise ValueError("extended call binding needs its declared capability")
            if call_proof is not None and (
                not set(call_proof.evidence_ids) <= evidence_ids
                or not set(record.evidence_ids) <= set(call_proof.evidence_ids)
            ):
                raise ValueError("call binding evidence disagrees with its call")
            if call_proof is not None:
                _native_call_witness(facts, call_proof)
                _call_origin_proof(facts, record, call_proof, declarations, base_by_id)
            targets = record.data.get("targets")
            if call_proof is not None and (
                not isinstance(targets, tuple)
                or call_proof.target not in targets
                or call_proof.origin is CallBindingOrigin.DIRECT
                and record.data.get("status") != SourceResolution.RESOLVED
                or (
                    (call_declaration := _call_declaration(call_proof, declarations)) is not None
                    and not set(call_declaration.evidence_ids) <= set(call_proof.evidence_ids)
                )
            ):
                raise ValueError("call binding disagrees with its target declaration")
    for section in facts.sections:
        if section.name is not SourceSectionName.CONSTRUCTS:
            continue
        for record in section.records:
            if record.kind == "construct_selector":
                receiver_parameter = record.data.get("receiver_parameter")
                _selector_receiver_proof(
                    facts,
                    record,
                    call_binding(record.data.get("receiver_binding")),
                    receiver_parameter if isinstance(receiver_parameter, str) else None,
                    declarations,
                    base_by_id,
                )
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
