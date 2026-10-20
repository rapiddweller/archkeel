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
    GUARDED_EFFECTS_FEATURE,
    MAX_NUMERIC_EVIDENCE_CHARS,
    MAX_STATIC_INTEGER,
    NATIVE_CALL_TARGETS,
    SOURCE_RESOLUTION_GAP_KIND,
    BuiltinTarget,
    CallArgument,
    CallArgumentKind,
    CallArgumentValueKind,
    CallBinding,
    CallBindingOrigin,
    ConstructSupport,
    ContextManagerSignature,
    Evidence,
    EvidenceClass,
    ExternalPackageTarget,
    GuardedEffectEvidence,
    GuardHelperArgument,
    JsonValue,
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
    guarded_effect,
    in_scope,
    member_inventories,
    parse_method_kind,
    parse_source_resolution,
    property_binding,
    python_identifier,
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
        "source_member_owner_static",
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
    if binding.get("source_binding_unique") is not True or binding.get("symbols_known") is not True:
        return None
    if isinstance(symbol, str):
        origin = binding.get("origin_definition")
        if (
            not isinstance(origin, str)
            or not _qualified_identifier(origin)
            or binding.get("origin_binding_unique") is not True
            or binding.get("reexport_candidate") is True
        ):
            return None
        return ".".join(part for part in (origin, suffix) if part)
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


def _provider_source_module(path: str) -> str | None:
    prefix = ".archkeel-providers/"
    if not _starts_with(path, prefix):
        return None
    relative = path[len(prefix) :]
    if _ends_with(relative, "/__init__.py"):
        relative = relative[: -len("/__init__.py")]
    elif _ends_with(relative, ".py"):
        relative = relative[:-3]
    else:
        return None
    parts: list[str] = []
    start = 0
    for index, character in enumerate(relative):
        if character == "/":
            parts.append(relative[start:index])
            start = index + 1
    parts.append(relative[start:])
    if not all(python_identifier(part) for part in parts):
        return None
    return ".".join(parts)


def _qualified_identifier(value: str) -> bool:
    if not value:
        return False
    start = 0
    for index, character in enumerate(value):
        if character == ".":
            if not python_identifier(value[start:index]):
                return False
            start = index + 1
    return python_identifier(value[start:])


def _last_segment(value: str) -> str:
    start = 0
    for index, character in enumerate(value):
        if character == ".":
            start = index + 1
    return value[start:]


def _evidence_column_index(evidence: Evidence) -> int | None:
    offset = 0
    for index, character in enumerate(evidence.excerpt):
        if offset == evidence.column:
            return index
        codepoint = ord(character)
        offset += (
            1 if codepoint < 0x80 else 2 if codepoint < 0x800 else 3 if codepoint < 0x10000 else 4
        )
        if offset > evidence.column:
            return None
    return len(evidence.excerpt) if offset == evidence.column else None


def _call_expression_matches_source(
    record: Record, expression: str, evidence: Mapping[str, Evidence]
) -> bool:
    if record.data.get("expression") != expression:
        return False
    for evidence_id in record.evidence_ids:
        item = evidence.get(evidence_id)
        if item is None or record.id != stable_id(
            "CALL", item.file, item.line, item.column, expression
        ):
            continue
        start = _evidence_column_index(item)
        if start is None or not _starts_with(item.excerpt[start:], expression):
            continue
        end = start + len(expression)
        while end < len(item.excerpt) and item.excerpt[end] in " \t":
            end += 1
        if end < len(item.excerpt) and item.excerpt[end] == "(":
            return True
    return False


def _stored_write_matches_source(item: Evidence, receiver: str, field: str, parameter: str) -> bool:
    parsed = _numeric_evidence_nodes(item)
    if parsed is None:
        return False
    statements, line_offset = parsed
    for statement in statements:
        for candidate in ast.walk(statement):
            if not isinstance(candidate, ast.Assign | ast.AnnAssign):
                continue
            span = _numeric_node_span(candidate, item.line, line_offset)
            if (
                span is None
                or span[0] != item.line
                or span[1] != item.column
                or span[2] != item.end_line
            ):
                continue
            if _stored_assignment_matches(candidate, receiver, field, parameter):
                return True
    return False


def _stored_assignment_matches(
    assignment: ast.Assign | ast.AnnAssign, receiver: str, field: str, parameter: str
) -> bool:
    target: ast.expr
    value: ast.expr | None
    if isinstance(assignment, ast.Assign):
        if len(assignment.targets) != 1:
            return False
        target = assignment.targets[0]
        value = assignment.value
    else:
        target = assignment.target
        value = assignment.value
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.ctx, ast.Store)
        and isinstance(target.value, ast.Name)
        and target.value.id == receiver
        and target.attr == field
        and isinstance(value, ast.Name)
        and value.id == parameter
    )


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


def _numeric_operand_alias(item: RecordData, evidence_ids: tuple[str, ...]) -> None:
    span_names = ("line", "column", "end_line", "end_column")
    origin_fields = {key for key, _ in item.entries}
    origin_value = item.get("value")
    origin_span = tuple(item.get(name) for name in span_names)
    base_fields = {
        "name",
        "value",
        "expression",
        "evidence_id",
        "line",
        "column",
        "end_line",
        "end_column",
    }
    scope_fields = {"scope_evidence_id", "scope_owner", "scope_symbol_id"}
    if (
        origin_fields not in (base_fields, base_fields | scope_fields)
        or not isinstance(item.get("name"), str)
        or not item.get("name")
        or not isinstance(origin_value, int)
        or isinstance(origin_value, bool)
        or origin_value < -MAX_STATIC_INTEGER
        or origin_value > MAX_STATIC_INTEGER
        or not isinstance(item.get("expression"), str)
        or not item.get("expression")
        or not isinstance(item.get("evidence_id"), str)
        or item.get("evidence_id") not in evidence_ids
        or origin_fields == base_fields | scope_fields
        and (
            not all(isinstance(item.get(name), str) and item.get(name) for name in scope_fields)
            or item.get("scope_evidence_id") not in evidence_ids
        )
        or not all(isinstance(field, int) and not isinstance(field, bool) for field in origin_span)
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


def _parse_numeric_scope_excerpt(excerpt: str) -> tuple[tuple[ast.stmt, ...], int] | None:
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS:
        return None
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    if not indentation:
        try:
            return tuple(ast.parse(excerpt).body), 0
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            return None
    try:
        parsed = ast.parse(f"if True:\n{excerpt}")
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.If):
        return None
    return tuple(parsed.body[0].body), 1


def _numeric_definition_nodes(
    nodes: tuple[ast.stmt, ...], parent_name: str
) -> Iterable[tuple[str, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]]:
    for root in nodes:
        pending: list[ast.AST] = [root]
        while pending:
            node = pending.pop()
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                qualified = f"{parent_name}.{node.name}"
                yield qualified, node
                pending.extend(reversed(node.body))
            else:
                pending.extend(reversed(tuple(ast.iter_child_nodes(node))))


def _numeric_scope_owner(
    scope_evidence: Evidence, owner_name: str, module_name: str
) -> tuple[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, int] | None:
    parsed = _parse_numeric_scope_excerpt(scope_evidence.excerpt)
    if parsed is None:
        return None
    nodes, line_offset = parsed
    owner_span = (scope_evidence.line, scope_evidence.column, scope_evidence.end_line)
    if not owner_name.startswith(module_name + "."):
        return None
    owner_leaf = owner_name.rpartition(".")[2]
    owners = [
        node
        for _, node in _numeric_definition_nodes(nodes, module_name)
        if node.name == owner_leaf
        and node.end_lineno is not None
        and (
            node.lineno - line_offset + scope_evidence.line - 1,
            node.col_offset,
            node.end_lineno - line_offset + scope_evidence.line - 1,
        )
        == owner_span
    ]
    return (owners[0], line_offset) if len(owners) == 1 else None


def _numeric_operation_in_owner(
    owner: ast.AST,
    operation: Record,
    evidence: Evidence,
    line_offset: int,
    scope_owner: str,
) -> ast.BinOp | ast.AugAssign | None:
    operation_span = tuple(
        operation.data.get(name) for name in ("line", "column", "end_line", "end_column")
    )
    matches = [
        node
        for node in ast.walk(owner)
        if isinstance(node, ast.BinOp | ast.AugAssign)
        and _numeric_node_span(node, evidence.line, line_offset) == operation_span
        and (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Mod)
            or isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Mod)
        )
    ]
    if len(matches) != 1 or not _numeric_operation_owner_matches(
        owner, matches[0], operation, scope_owner
    ):
        return None
    return matches[0]


def _numeric_operation_owner_matches(
    scope: ast.AST, operation_node: ast.AST, operation: Record, scope_owner: str
) -> bool:
    parents = {
        child: parent for parent in ast.walk(scope) for child in ast.iter_child_nodes(parent)
    }
    definitions: list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = []
    node = operation_node
    while node is not scope:
        parent = parents.get(node)
        if parent is None:
            return False
        node = parent
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            definitions.append(node)
    qualified_owner = scope_owner
    for definition in reversed(
        definitions[:-1] if definitions and definitions[-1] is scope else definitions
    ):
        qualified_owner = f"{qualified_owner}.{definition.name}"
    return operation.data.get("owner") == qualified_owner


def _numeric_unique_local_assignment(
    owner: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    origin: RecordData,
    evidence: Evidence,
    line_offset: int,
    use: ast.BinOp | ast.AugAssign,
) -> ast.expr | None:
    name = origin.get("name")
    if not isinstance(name, str):
        return None
    parents = {
        child: parent for parent in ast.walk(owner) for child in ast.iter_child_nodes(parent)
    }
    stores = [
        node
        for node in ast.walk(owner)
        if isinstance(node, ast.Name)
        and node.id == name
        and isinstance(node.ctx, ast.Store | ast.Del)
    ]
    if len(stores) != 1:
        return None
    target = stores[0]
    assignment = parents.get(target)
    if not isinstance(assignment, ast.Assign | ast.AnnAssign) or assignment.value is None:
        return None
    if isinstance(assignment, ast.Assign):
        if not any(target is item for root in assignment.targets for item in ast.walk(root)):
            return None
    elif assignment.target is not target:
        return None
    if assignment not in owner.body:
        return None
    parameters = (
        [
            argument.arg
            for argument in (
                *owner.args.posonlyargs,
                *owner.args.args,
                *owner.args.kwonlyargs,
            )
        ]
        if isinstance(owner, ast.FunctionDef | ast.AsyncFunctionDef)
        else []
    )
    if name in parameters or _numeric_other_binding(owner, name):
        return None
    assignment_span = tuple(origin.get(key) for key in ("line", "column", "end_line", "end_column"))
    if _numeric_node_span(assignment, evidence.line, line_offset) != assignment_span:
        return None
    if (assignment.lineno, assignment.col_offset) >= (use.lineno, use.col_offset):
        return None
    try:
        expression = ast.unparse(assignment.value)
    except (RecursionError, ValueError):
        return None
    return assignment.value if expression == origin.get("expression") else None


def _numeric_other_binding(owner: ast.AST, name: str) -> bool:
    for node in ast.walk(owner):
        if isinstance(node, ast.arg) and node.arg == name:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
        if isinstance(node, ast.alias):
            alias_name: str = node.name
            alias_asname: str | None = node.asname
            if alias_asname == name or (
                alias_asname is None
                and (alias_name == name or alias_name[: len(name) + 1] == name + ".")
            ):
                return True
        if isinstance(node, ast.Global | ast.Nonlocal) and name in node.names:
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == name:
            return True
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name == name:
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == name:
            return True
    return False


def _numeric_local_alias_assignment(
    origin: RecordData,
    operation: Record,
    evidence_by_id: Mapping[str, Evidence],
    declarations_by_id: Mapping[str, Record],
    expected_file: str,
    module_name: str,
) -> ast.expr | None:
    evidence_id = origin.get("scope_evidence_id")
    owner_name = origin.get("scope_owner")
    symbol_id = origin.get("scope_symbol_id")
    if (
        not isinstance(evidence_id, str)
        or not isinstance(owner_name, str)
        or not isinstance(symbol_id, str)
    ):
        return None
    scope_evidence = evidence_by_id.get(evidence_id)
    symbol_record = declarations_by_id.get(symbol_id)
    if (
        scope_evidence is None
        or symbol_record is None
        or scope_evidence.file != expected_file
        or symbol_record.data.get("qualified_name") != owner_name
        or not _numeric_owner_evidence_matches(symbol_record, scope_evidence, evidence_by_id)
    ):
        return None
    owner_result = _numeric_scope_owner(scope_evidence, owner_name, module_name)
    if owner_result is None:
        return None
    owner, line_offset = owner_result
    use = _numeric_operation_in_owner(owner, operation, scope_evidence, line_offset, owner_name)
    return (
        _numeric_unique_local_assignment(owner, origin, scope_evidence, line_offset, use)
        if use is not None
        else None
    )


def _numeric_module_alias_supported(
    origin: RecordData,
    operation: Record,
    declarations_by_name: Mapping[str, tuple[Record, ...]],
    declarations_by_id: Mapping[str, Record],
    evidence_by_id: Mapping[str, Evidence],
    expected_file: str,
    module_name: str,
) -> bool:
    name = origin.get("name")
    evidence_id = origin.get("evidence_id")
    if not isinstance(name, str) or not isinstance(evidence_id, str):
        return False
    declarations = declarations_by_name.get(f"{module_name}.{name}", ())
    if len(declarations) != 1:
        return False
    declaration = declarations[0]
    if (
        declaration.kind not in {"static_constant", "dynamic_binding"}
        or evidence_id not in declaration.evidence_ids
        or declaration.data.get("source_binding_unique") is not True
        or not _numeric_module_use_chain_supported(
            operation,
            name,
            declarations_by_id,
            evidence_by_id,
            expected_file,
            module_name,
        )
    ):
        return False
    assignment = (origin.get("line"), origin.get("column"))
    use = (operation.data.get("line"), operation.data.get("column"))
    return (
        all(isinstance(part, int) and not isinstance(part, bool) for part in (*assignment, *use))
        and assignment < use
    )


def _numeric_module_use_chain_supported(
    operation: Record,
    name: str,
    declarations_by_id: Mapping[str, Record],
    evidence_by_id: Mapping[str, Evidence],
    expected_file: str,
    module_name: str,
) -> bool:
    chain = operation.data.get("binding_scopes")
    operation_owner = operation.data.get("owner")
    if not isinstance(chain, tuple) or not isinstance(operation_owner, str):
        return False
    if operation_owner == module_name:
        return not chain
    if not chain:
        return False
    first_scope = chain[0]
    if not isinstance(first_scope, RecordData):
        return False
    owner_id: JsonValue = first_scope.get("scope_symbol_id")
    owner = declarations_by_id.get(owner_id) if isinstance(owner_id, str) else None
    if owner is None or owner.data.get("qualified_name") != operation_owner:
        return False
    expected_ids: list[str] = []
    while owner.kind in {"function", "method", "class"}:
        expected_ids.append(owner.id)
        parent, valid = _numeric_lexical_parent(owner, declarations_by_id, module_name)
        if not valid:
            return False
        if parent is None:
            break
        owner = parent
    if (
        any(not isinstance(item, RecordData) for item in chain)
        or [item.get("scope_symbol_id") for item in chain if isinstance(item, RecordData)]
        != expected_ids
    ):
        return False
    for item in chain:
        if not isinstance(item, RecordData):
            return False
        if not _numeric_module_use_scope(
            item,
            operation,
            name,
            evidence_by_id,
            declarations_by_id,
            expected_file,
        ):
            return False
    return True


def _numeric_lexical_parent(
    owner: Record, declarations_by_id: Mapping[str, Record], module_name: str
) -> tuple[Record | None, bool]:
    qualified_name_value: JsonValue = owner.data.get("qualified_name")
    name_value: JsonValue = owner.data.get("name")
    parent_name_value: JsonValue = owner.data.get("parent")
    parent_id = owner.data.get("lexical_parent_id")
    if not isinstance(qualified_name_value, str) or not isinstance(name_value, str):
        return None, False
    qualified_name: str = qualified_name_value
    name: str = name_value
    if parent_name_value is None:
        return None, qualified_name == module_name + "." + name and parent_id is None
    if not isinstance(parent_name_value, str):
        return None, False
    parent_name: str = parent_name_value
    if qualified_name != parent_name + "." + name or not isinstance(parent_id, str):
        return None, False
    parent = declarations_by_id.get(parent_id)
    if parent is None or parent.data.get("qualified_name") != parent_name:
        return None, False
    return parent, True


def _numeric_module_use_scope(
    item: RecordData,
    operation: Record,
    name: str,
    evidence_by_id: Mapping[str, Evidence],
    declarations_by_id: Mapping[str, Record],
    expected_file: str,
) -> bool:
    evidence_id = item.get("scope_evidence_id")
    owner_name = item.get("scope_owner")
    symbol_id = item.get("scope_symbol_id")
    if (
        not isinstance(evidence_id, str)
        or not isinstance(owner_name, str)
        or not isinstance(symbol_id, str)
    ):
        return False
    scope_evidence = evidence_by_id.get(evidence_id)
    symbol = declarations_by_id.get(symbol_id)
    if (
        scope_evidence is None
        or symbol is None
        or scope_evidence.file != expected_file
        or symbol.data.get("qualified_name") != owner_name
        or not _numeric_owner_evidence_matches(symbol, scope_evidence, evidence_by_id)
    ):
        return False
    module_name = symbol.data.get("module")
    if not isinstance(module_name, str):
        return False
    owner_result = _numeric_scope_owner(scope_evidence, owner_name, module_name)
    if owner_result is None:
        return False
    owner, line_offset = owner_result
    if (
        _numeric_operation_in_owner(owner, operation, scope_evidence, line_offset, owner_name)
        is None
    ):
        return False
    is_method_scope = operation.data.get("owner") != owner_name and symbol.kind == "class"
    if is_method_scope:
        return True
    return not _numeric_other_binding(owner, name) and not any(
        isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store | ast.Del)
        for node in ast.walk(owner)
    )


def _numeric_owner_evidence_matches(
    symbol: Record, scope_evidence: Evidence, evidence_by_id: Mapping[str, Evidence]
) -> bool:
    return any(
        (owner_evidence := evidence_by_id.get(owner_evidence_id)) is not None
        and (
            owner_evidence.file,
            owner_evidence.line,
            owner_evidence.end_line,
            owner_evidence.column,
        )
        == (
            scope_evidence.file,
            scope_evidence.line,
            scope_evidence.end_line,
            scope_evidence.column,
        )
        for owner_evidence_id in symbol.evidence_ids
    )


@lru_cache(maxsize=256)
def _parse_numeric_evidence_excerpt(
    excerpt: str,
) -> tuple[tuple[ast.stmt, ...], int] | None:
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS or "\n" in excerpt:
        return None
    if _numeric_elif_start(excerpt) is not None:
        return _parse_numeric_elif_excerpt(excerpt)
    try:
        return tuple(ast.parse(excerpt).body), 0
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
        parsed = _parse_indented_numeric_excerpt(excerpt, indentation, synthetic_body=False)
        if parsed is not None:
            return parsed
        parsed = _parse_indented_numeric_excerpt(excerpt, indentation, synthetic_body=True)
        if parsed is None or len(parsed[0]) != 1:
            return None
        return parsed if _numeric_header_has_synthetic_body(parsed[0][0]) else None


def _numeric_elif_start(excerpt: str) -> int | None:
    for index, character in enumerate(excerpt):
        if character not in " \t":
            if excerpt[index : index + 4] != "elif":
                return None
            if index + 4 < len(excerpt) and excerpt[index + 4] not in " \t(":
                return None
            return index
    return None


def _parse_indented_numeric_excerpt(
    excerpt: str, indentation: str, *, synthetic_body: bool
) -> tuple[tuple[ast.stmt, ...], int] | None:
    unit = "\t" if "\t" in indentation else "    "
    depth = 1 if indentation else 0
    wrappers = "if True:\n" if indentation else ""
    suffix = f"\n{indentation}{unit}pass" if synthetic_body else ""
    try:
        parsed = ast.parse(wrappers + excerpt + suffix)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots = tuple(parsed.body)
    for _ in range(depth):
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return None
        roots = tuple(roots[0].body)
    return roots, depth


def _numeric_header_has_synthetic_body(node: ast.stmt) -> bool:
    header_types = (
        ast.If,
        ast.While,
        ast.For,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    return (
        isinstance(node, header_types)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def _parse_numeric_elif_excerpt(excerpt: str) -> tuple[tuple[ast.stmt, ...], int] | None:
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    unit = "\t" if "\t" in indentation else "    "
    source = f"{indentation}if True:\n{indentation}{unit}pass\n{excerpt}"
    for synthetic_body in (False, True):
        parsed = _parse_indented_numeric_excerpt(source, indentation, synthetic_body=synthetic_body)
        if parsed is None:
            continue
        roots, depth = parsed
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return None
        preceding = roots[0]
        if len(preceding.body) != 1 or not isinstance(preceding.body[0], ast.Pass):
            return None
        if len(preceding.orelse) != 1 or not isinstance(preceding.orelse[0], ast.If):
            return None
        alternate = preceding.orelse[0]
        if not synthetic_body or _numeric_header_has_synthetic_body(alternate):
            return roots, depth + 2
    return None


def _numeric_evidence_nodes(evidence: Evidence) -> tuple[tuple[ast.stmt, ...], int] | None:
    return _parse_numeric_evidence_excerpt(evidence.excerpt)


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


def _call_arguments_match_source(
    record: Record,
    arguments: tuple[CallArgument, ...],
    evidence_by_id: Mapping[str, Evidence],
    expected_file: str,
) -> bool:
    """Tie the complete argument inventory and literal facts to one captured call."""
    expression = record.data.get("expression")
    if not isinstance(expression, str) or not _call_expression_matches_source(
        record, expression, evidence_by_id
    ):
        return False
    for evidence_id in record.evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None or evidence.file != expected_file:
            continue
        parsed = _call_evidence_nodes(evidence.excerpt)
        if parsed is None:
            continue
        roots, line_offset = parsed
        calls = [
            node
            for root in roots
            for node in ast.walk(root)
            if isinstance(node, ast.Call)
            and _numeric_node_span(node, evidence.line, line_offset)
            == (evidence.line, evidence.column, evidence.end_line, node.end_col_offset)
            and _call_expression(node) == expression
        ]
        if len(calls) != 1 or not _call_actuals_match(
            calls[0], arguments, evidence_by_id, expected_file, evidence.line, line_offset
        ):
            continue
        return True
    return False


@lru_cache(maxsize=256)
def _call_evidence_nodes(excerpt: str) -> tuple[tuple[ast.stmt, ...], int] | None:
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS or "\n" in excerpt:
        return None
    parsed = _parse_numeric_evidence_excerpt(excerpt)
    if parsed is not None:
        return parsed
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    if indentation and len(indentation) <= 4:
        try:
            parsed_module = ast.parse("async def _archkeel_call():\n" + excerpt)
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            return None
        if len(parsed_module.body) == 1 and isinstance(parsed_module.body[0], ast.AsyncFunctionDef):
            return tuple(parsed_module.body[0].body), 1
    unit = "\t" if "\t" in indentation else "    "
    if len(indentation) % len(unit):
        return None
    depth = len(indentation) // len(unit)
    wrappers = "async def _archkeel_call():\n"
    wrappers += "".join(f"{unit * level}if True:\n" for level in range(1, depth))
    try:
        parsed_module = ast.parse(wrappers + excerpt)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots: tuple[ast.stmt, ...] = tuple(parsed_module.body)
    for _ in range(depth):
        if len(roots) != 1 or not isinstance(roots[0], (ast.AsyncFunctionDef, ast.If)):
            return None
        roots = tuple(roots[0].body)
    return roots, depth + 1


def _call_expression(node: ast.Call) -> str | None:
    try:
        return ast.unparse(node.func)
    except (RecursionError, ValueError):
        return None


def _call_excerpt_matches(
    expression: str, excerpt: str, line: int, column: int, end_line: int
) -> bool:
    parsed = _call_evidence_nodes(excerpt)
    if parsed is None:
        return False
    roots, line_offset = parsed
    matches = [
        node
        for root in roots
        for node in ast.walk(root)
        if isinstance(node, ast.Call)
        and _call_expression(node) == expression
        and (span := _call_actual_span(node, line, line_offset)) is not None
        and span[:3] == (line, column, end_line)
    ]
    return len(matches) == 1


def _call_actuals_match(
    node: ast.Call,
    arguments: tuple[CallArgument, ...],
    evidence_by_id: Mapping[str, Evidence],
    expected_file: str,
    source_line: int,
    line_offset: int,
) -> bool:
    actuals: list[tuple[ast.AST, CallArgumentKind, str | None, ast.expr]] = []
    for actual in node.args:
        value = actual.value if isinstance(actual, ast.Starred) else actual
        kind = (
            CallArgumentKind.STARRED_POSITIONAL
            if isinstance(actual, ast.Starred)
            else CallArgumentKind.POSITIONAL
        )
        actuals.append((actual, kind, None, value))
    for keyword in node.keywords:
        kind = (
            CallArgumentKind.KEYWORD
            if keyword.arg is not None
            else CallArgumentKind.STARRED_KEYWORD
        )
        actuals.append((keyword, kind, keyword.arg, keyword.value))
    if len(actuals) != len(arguments):
        return False
    used_evidence: set[str] = set()
    for (node_actual, kind, keyword_name, value), argument in zip(actuals, arguments, strict=True):
        if (
            argument.kind is not kind
            or argument.keyword != keyword_name
            or len(argument.evidence_ids) != 1
        ):
            return False
        evidence_id = argument.evidence_ids[0]
        evidence = evidence_by_id.get(evidence_id)
        if evidence_id in used_evidence or evidence is None or evidence.file != expected_file:
            return False
        used_evidence.add(evidence_id)
        span = _call_actual_span(node_actual, source_line, line_offset)
        if span is None or span[:3] != (evidence.line, evidence.column, evidence.end_line):
            return False
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            expected_value = value.value
            expected_kind = CallArgumentValueKind.STRING_LITERAL
        else:
            expected_value = None
            expected_kind = CallArgumentValueKind.OTHER
        if argument.value_kind is not expected_kind or argument.value != expected_value:
            return False
    return True


def _call_actual_span(
    node: ast.AST, source_line: int, line_offset: int
) -> tuple[int, int, int, int] | None:
    if not isinstance(node, ast.stmt | ast.expr | ast.keyword):
        return None
    end_line = node.end_lineno
    end_column = node.end_col_offset
    if end_line is None or end_column is None:
        return None
    return (
        node.lineno - line_offset + source_line - 1,
        node.col_offset,
        end_line - line_offset + source_line - 1,
        end_column,
    )


def _numeric_assignment_expression(
    origin: RecordData, evidence_by_id: Mapping[str, Evidence], expected_file: str
) -> ast.expr | None:
    evidence_id = origin.get("evidence_id")
    if not isinstance(evidence_id, str):
        return None
    evidence = evidence_by_id.get(evidence_id)
    if evidence is None or evidence.file != expected_file:
        return None
    parsed = _numeric_evidence_nodes(evidence)
    if parsed is None:
        return None
    nodes, line_offset = parsed
    expected = tuple(origin.get(name) for name in ("line", "column", "end_line", "end_column"))
    matches: list[ast.expr] = []
    for root in nodes:
        for node in ast.walk(root):
            if _numeric_node_span(node, evidence.line, line_offset) != expected:
                continue
            value: ast.expr | None = None
            targets: tuple[ast.expr, ...] = ()
            if isinstance(node, ast.Assign):
                value, targets = node.value, tuple(node.targets)
            elif isinstance(node, ast.AnnAssign):
                value, targets = node.value, (node.target,)
            if value is not None and any(
                isinstance(target, ast.Name) and target.id == origin.get("name")
                for target in targets
            ):
                matches.append(value)
    if len(matches) != 1:
        return None
    try:
        expression = ast.unparse(matches[0])
    except (RecursionError, ValueError):
        return None
    if expression != origin.get("expression"):
        return None
    return matches[0]


def _numeric_operation_expression(
    record: Record, evidence_by_id: Mapping[str, Evidence], expected_file: str
) -> ast.BinOp | ast.AugAssign | None:
    data = record.data
    expected = tuple(data.get(name) for name in ("line", "column", "end_line", "end_column"))
    matches: list[ast.BinOp | ast.AugAssign] = []
    for evidence_id in record.evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if (
            evidence is None
            or evidence.file != expected_file
            or (evidence.line, evidence.column, evidence.end_line)
            != (expected[0], expected[1], expected[2])
        ):
            continue
        parsed = _numeric_evidence_nodes(evidence)
        if parsed is None:
            continue
        nodes, line_offset = parsed
        for root in nodes:
            for node in ast.walk(root):
                if _numeric_node_span(node, evidence.line, line_offset) != expected:
                    continue
                if (
                    data.get("form") == "binary"
                    and isinstance(node, ast.BinOp)
                    and isinstance(node.op, ast.Mod)
                ):
                    matches.append(node)
                elif (
                    data.get("form") == "augmented"
                    and isinstance(node, ast.AugAssign)
                    and isinstance(node.op, ast.Mod)
                ):
                    matches.append(node)
    return matches[0] if len(matches) == 1 else None


def _bounded_numeric_value(
    node: ast.expr,
    aliases: Mapping[str, ast.expr],
    seen: frozenset[str] = frozenset(),
    depth: int = 0,
) -> int | None:
    if depth > 12:
        return None
    if isinstance(node, ast.Constant):
        if type(node.value) is int:
            constant_value = node.value
            return (
                constant_value
                if -MAX_STATIC_INTEGER <= constant_value <= MAX_STATIC_INTEGER
                else None
            )
        if type(node.value) is bool:
            return int(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        unary_value = _bounded_numeric_value(node.operand, aliases, seen, depth + 1)
        if unary_value is None:
            return None
        return unary_value if isinstance(node.op, ast.UAdd) else -unary_value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        base = _bounded_numeric_value(node.left, aliases, seen, depth + 1)
        exponent = _bounded_numeric_value(node.right, aliases, seen, depth + 1)
        if base is None or exponent is None or exponent < 0 or exponent > 256:
            return None
        magnitude = -base if base < 0 else base
        result = 1
        for _ in range(exponent):
            if magnitude and result > MAX_STATIC_INTEGER // magnitude:
                return None
            result *= magnitude
        return -result if base < 0 and exponent % 2 else result
    if isinstance(node, ast.Name) and node.id in aliases and node.id not in seen:
        return _bounded_numeric_value(aliases[node.id], aliases, seen | {node.id}, depth + 1)
    return None


def _validate_numeric_operand_witness(
    record: Record,
    evidence_by_id: Mapping[str, Evidence],
    declarations_by_id: Mapping[str, Record],
    declarations_by_name: Mapping[str, tuple[Record, ...]],
    expected_file: str,
) -> None:
    data = record.data
    expression = _numeric_operation_expression(record, evidence_by_id, expected_file)
    if expression is None:
        if data.get("proof") == "known":
            raise ValueError("known numeric operand lacks a complete source witness")
        return
    left = expression.left if isinstance(expression, ast.BinOp) else expression.target
    subject = (
        left.id
        if isinstance(left, ast.Name)
        else left.attr
        if isinstance(left, ast.Attribute)
        else None
    )
    if data.get("subject") != subject:
        raise ValueError("numeric operand subject disagrees with its source expression")
    if data.get("proof") != "known":
        return
    operand = expression.right if isinstance(expression, ast.BinOp) else expression.value
    derivation = data.get("derivation")
    if not isinstance(derivation, tuple):
        raise ValueError("invalid numeric operand derivation")
    aliases: dict[str, ast.expr] = {}
    origins: dict[str, RecordData] = {}
    for origin in derivation:
        if not isinstance(origin, RecordData):
            raise ValueError("invalid numeric operand derivation")
        name = origin.get("name")
        if not isinstance(name, str):
            raise ValueError("numeric operand alias name is invalid")
        if origin.get("scope_evidence_id") is not None:
            alias_expression = _numeric_local_alias_assignment(
                origin,
                record,
                evidence_by_id,
                declarations_by_id,
                expected_file,
                str(data.get("module")),
            )
        else:
            alias_expression = _numeric_assignment_expression(origin, evidence_by_id, expected_file)
            if not _numeric_module_alias_supported(
                origin,
                record,
                declarations_by_name,
                declarations_by_id,
                evidence_by_id,
                expected_file,
                str(data.get("module")),
            ):
                raise ValueError("numeric module alias lacks a unique preceding declaration")
        if alias_expression is None:
            raise ValueError("numeric alias lacks a complete source witness")
        if name in origins:
            if origins[name] != origin:
                raise ValueError("numeric operand alias has conflicting source origins")
            continue
        aliases[name] = alias_expression
        origins[name] = origin
    for name, origin in origins.items():
        value = _bounded_numeric_value(aliases[name], aliases, frozenset({name}))
        if value is None or value != origin.get("value"):
            raise ValueError("numeric alias value disagrees with its expression")
    value = _bounded_numeric_value(operand, aliases)
    if value is None or value != data.get("value"):
        raise ValueError("numeric operand value disagrees with its expression")


def _numeric_operand_record(record: Record, fields: set[str]) -> tuple[str, ...]:
    base_fields = (
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
    scoped_fields = (
        *base_fields,
        "binding_scopes",
    )
    required = scoped_fields if "binding_scopes" in fields else base_fields
    data = record.data
    span_names = ("line", "column", "end_line", "end_column")
    span = tuple(data.get(name) for name in span_names)
    value = data.get("value")
    derivation = data.get("derivation")
    if (
        fields not in (set(base_fields), set(scoped_fields))
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
        or "binding_scopes" in fields
        and not _numeric_binding_scopes(record.data.get("binding_scopes"), record.evidence_ids)
    ):
        raise ValueError("invalid numeric operand source proof")
    for item in derivation:
        if not isinstance(item, RecordData):
            raise ValueError("invalid numeric operand alias proof")
        _numeric_operand_alias(item, record.evidence_ids)
    if data.get("proof") == "unknown" and derivation:
        raise ValueError("invalid numeric operand source proof")
    return required


def _native_call_witness(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    evidence: Mapping[str, Evidence],
) -> None:
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
    evidence_ids = set(binding.evidence_ids)
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
    expression = record.data.get("expression")
    if not isinstance(expression, str) or not _call_expression_matches_source(
        record, expression, evidence
    ):
        raise ValueError("native call expression disagrees with its source evidence")
    if binding.origin is CallBindingOrigin.NATIVE_RECEIVER:
        _native_receiver_witness(facts, record, binding, evidence)
        provider = next(
            (item for item in facts.provider_bindings if item.qualified_name == binding.target),
            None,
        )
        provider_reference = proof.get("provider_evidence_id")
        if (
            provider is None
            or provider.evidence_id not in evidence_ids
            or provider_reference != provider.evidence_id
        ):
            raise ValueError("native receiver needs its exact captured provider member declaration")
        return
    root, suffix = _expression_root(expression)
    imported_targets = _native_imported_targets(facts, record, evidence_ids, root, suffix)
    if binding.target not in imported_targets:
        raise ValueError("native call needs its matching stable import evidence")
    _native_provider_witness(facts, binding, proof, evidence_ids)


def _native_imported_targets(
    facts: SourceFacts,
    record: Record,
    evidence_ids: set[str],
    root: str,
    suffix: str,
) -> set[str]:
    targets: set[str] = set()
    for section in facts.sections:
        if section.name is not SourceSectionName.IMPORTS:
            continue
        for imported in section.records:
            if (
                not evidence_ids.intersection(imported.evidence_ids)
                or imported.data.get("source_module") != record.data.get("source_module")
                or imported.data.get("source_binding_unique") is not True
                or imported.data.get("binding") != root
            ):
                continue
            module = imported.data.get("target_module")
            symbol = imported.data.get("symbol")
            if isinstance(module, str):
                imported_target = module + (f".{symbol}" if isinstance(symbol, str) else "")
                targets.add(imported_target + suffix)
    return targets


def _native_provider_witness(
    facts: SourceFacts,
    binding: CallBinding,
    proof: RecordData,
    evidence_ids: set[str],
) -> None:
    if _starts_with(binding.target, "random.") or _starts_with(binding.target, "secrets."):
        provider = next(
            (item for item in facts.provider_bindings if item.qualified_name == binding.target),
            None,
        )
        provider_reference = proof.get("provider_evidence_id")
        if (
            provider is None
            or provider.evidence_id not in evidence_ids
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


def _expression_root(expression: str) -> tuple[str, str]:
    for index, character in enumerate(expression):
        if character == ".":
            return expression[:index], expression[index:]
    return expression, ""


def _native_receiver_witness(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    evidence: Mapping[str, Evidence],
) -> None:
    target_method = _last_segment(binding.target)
    expression = record.data.get("expression")
    if not isinstance(expression, str) or _last_segment(expression) != target_method:
        raise ValueError("native receiver method disagrees with its written callee")
    receiver, _ = _expression_root(expression)
    witnesses = set(binding.evidence_ids)
    for section in facts.sections:
        if section.name is not SourceSectionName.CALLS:
            continue
        for constructor in section.records:
            constructor_binding = call_binding(constructor.data.get("call_binding"))
            constructor_expression = constructor.data.get("expression")
            if (
                constructor_binding is None
                or constructor_binding.origin is not CallBindingOrigin.CONSTRUCTOR
                or constructor_binding.target != "random.Random"
                or not witnesses.intersection(constructor.evidence_ids)
                or not isinstance(constructor_expression, str)
                or not _call_expression_matches_source(
                    constructor, constructor_expression, evidence
                )
                or constructor.data.get("source_scope") != record.data.get("source_scope")
            ):
                continue
            result_bindings = constructor.data.get("result_bindings")
            if not isinstance(result_bindings, tuple):
                continue
            for result in result_bindings:
                if not isinstance(result, RecordData) or result.get("target_kind") != "name":
                    continue
                assignment_name = result.get("name")
                references = result.get("evidence_ids")
                if (
                    assignment_name == receiver
                    and isinstance(references, tuple)
                    and witnesses.intersection(item for item in references if isinstance(item, str))
                    and any(
                        item in evidence and evidence[item].line < _record_line(record, evidence)
                        for item in references
                        if isinstance(item, str)
                    )
                ):
                    return
            if expression == f"{constructor_expression}().{target_method}":
                return
    raise ValueError("native receiver needs its exact captured Random construction")


def _record_line(record: Record, evidence: Mapping[str, Evidence]) -> int:
    lines = [evidence[item].line for item in record.evidence_ids if item in evidence]
    return min(lines) if lines else 0


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
                or _record_data_value(methods[0].data, "parent") != current
                or _record_data_value(methods[0].data, "decorators")
                or _record_data_value(methods[0].data, "qualified_name") != target
            ):
                return False, ()
            return True, tuple(sorted(path_evidence | set(methods[0].evidence_ids)))
        if _record_data_value(owner.data, "class_header_static") is not True:
            return False, ()
        attributes = _record_data_value(owner.data, "attribute_declarations")
        if isinstance(attributes, tuple) and any(
            isinstance(attribute, RecordData)
            and _record_data_value(attribute, "name") == method_name
            for attribute in attributes
        ):
            return False, ()
        bases = _record_data_value(owner.data, "base_declarations")
        if not isinstance(bases, tuple) or len(bases) != 1 or not isinstance(bases[0], RecordData):
            return False, ()
        base = bases[0]
        base_targets = _record_data_value(base, "targets")
        base_evidence = _record_data_value(base, "evidence_ids")
        if (
            _record_data_value(base, "status") != SourceResolution.RESOLVED
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
    _validate_call_proof_runtime(facts, proof)
    if binding.origin is CallBindingOrigin.STORED_RECEIVER:
        _stored_receiver_proof(facts, record, binding, proof, declarations, evidence)
    elif binding.origin is CallBindingOrigin.CONSTRUCTED_RECEIVER:
        _constructed_receiver_proof(facts, record, binding, proof, declarations, evidence)
    elif binding.origin is CallBindingOrigin.CONSTRUCTOR:
        _constructor_origin_proof(record, proof, declarations)
    if binding.origin in {
        CallBindingOrigin.NATIVE,
        CallBindingOrigin.NATIVE_RECEIVER,
        CallBindingOrigin.CONSTRUCTOR,
    }:
        _native_call_witness(facts, record, binding, evidence)


def _validate_call_proof_runtime(facts: SourceFacts, proof: RecordData) -> None:
    if proof.get("runtime_name") is not None and (
        proof.get("runtime_name") != facts.runtime.name
        or proof.get("runtime_version") != facts.runtime.version
    ):
        raise ValueError("call proof runtime identity disagrees with the source snapshot")


def _stored_receiver_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    proof: RecordData,
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> None:
    owner_name, field, parameter, target = (
        proof.get("owner"),
        proof.get("field"),
        proof.get("parameter"),
        proof.get("target"),
    )
    witnesses = proof.get("witness_evidence_ids")
    linked = _stored_receiver_links(
        facts,
        binding,
        declarations,
        owner_name,
        field,
        parameter,
        target,
        witnesses,
    )
    if linked is None:
        raise ValueError("stored receiver needs a linked initializer and annotation witness")
    owners, initializers, typed_writes, typed_parameters, stored_types, path_evidence = linked
    if (
        not isinstance(field, str)
        or not isinstance(parameter, str)
        or not isinstance(witnesses, tuple)
        or len(witnesses) != 2
        or any(
            not isinstance(item, str)
            or item not in evidence
            or evidence[item].file not in facts.coverage.selected_files
            for item in witnesses
        )
    ):
        raise ValueError("stored receiver needs selected initializer witnesses")
    if not _qualified_identifier(field) or not _qualified_identifier(parameter):
        raise ValueError("stored receiver field and parameter must be identifiers")
    if len(typed_writes) != 1 or len(typed_parameters) != 1 or len(stored_types) != 1:
        raise ValueError("stored receiver needs unique typed field and parameter declarations")
    if _record_data_value(typed_writes[0], "annotation_target") != target:
        raise ValueError("stored receiver annotation does not prove its claimed target")
    if not set(path_evidence) <= set(binding.evidence_ids):
        raise ValueError("stored receiver method path is missing evidence")
    target_declarations = declarations.get(binding.target, [])
    if len(target_declarations) != 1 or target_declarations[0].kind != "method":
        raise ValueError("stored receiver needs one canonical method declaration")
    if len(owners) != 1 or len(initializers) != 1:
        raise ValueError("stored receiver needs one canonical owner and initializer")
    receiver = _record_data_value(initializers[0].data, "receiver_parameter")
    write_id = _record_data_value(typed_writes[0], "evidence_id")
    write_evidence = evidence.get(write_id) if isinstance(write_id, str) else None
    expression = f"{receiver}.{field}.{_last_segment(binding.target)}"
    if (
        not isinstance(receiver, str)
        or write_evidence is None
        or not _stored_write_matches_source(write_evidence, receiver, field, parameter)
        or not _call_expression_matches_source(record, expression, evidence)
    ):
        raise ValueError("stored receiver proof disagrees with its source expressions")


def _stored_receiver_links(
    facts: SourceFacts,
    binding: CallBinding,
    declarations: Mapping[str, list[Record]],
    owner_name: JsonValue,
    field: JsonValue,
    parameter: JsonValue,
    target: JsonValue,
    witnesses: JsonValue,
) -> (
    tuple[
        list[Record],
        list[Record],
        list[RecordData],
        list[RecordData],
        list[Record],
        tuple[str, ...],
    ]
    | None
):
    if not isinstance(owner_name, str):
        return None
    owners = declarations.get(owner_name, [])
    initializers = declarations.get(f"{owner_name}.__init__", [])
    stored_types = declarations.get(target, []) if isinstance(target, str) else []
    if len(owners) != 1 or len(initializers) != 1 or owners[0].kind != "class":
        return None
    if (
        _record_data_value(owners[0].data, "source_binding_unique") is not True
        or _record_data_value(owners[0].data, "source_member_binding_static") is not True
        or initializers[0].kind != "method"
    ):
        return None
    writes = _record_data_value(initializers[0].data, "stored_field_writes")
    receiver = _record_data_value(initializers[0].data, "receiver_parameter")
    write_id = witnesses[0] if isinstance(witnesses, tuple) and witnesses else None
    write_entries = writes if isinstance(writes, tuple) else ()
    linked_writes = [
        item
        for item in write_entries
        if isinstance(item, RecordData)
        and _record_data_value(item, "field") == field
        and _record_data_value(item, "parameter") == parameter
        and _record_data_value(item, "evidence_id") == write_id
        and isinstance(witnesses, tuple)
        and len(witnesses) == 2
        and _record_data_value(item, "annotation_evidence_id") == witnesses[1]
        and _record_data_value(item, "receiver") == receiver
    ]
    parameters = _record_data_value(initializers[0].data, "parameters")
    parameter_entries = parameters if isinstance(parameters, tuple) else ()
    typed_parameters = [
        item
        for item in parameter_entries
        if isinstance(item, RecordData)
        and _record_data_value(item, "name") == parameter
        and isinstance(_record_data_value(item, "annotation"), str)
    ]
    if isinstance(target, str):
        path_matches, path_evidence = _stored_method_path(target, binding.target, declarations)
    else:
        path_matches, path_evidence = False, ()
    annotation_target = (
        _annotation_class_origin(initializers[0], typed_parameters[0], facts, declarations)
        if len(typed_parameters) == 1
        else None
    )
    if not path_matches or annotation_target != target:
        return None
    if len(stored_types) != 1 or stored_types[0].kind != "class":
        return None
    if (
        _record_data_value(stored_types[0].data, "source_binding_unique") is not True
        or _record_data_value(stored_types[0].data, "source_member_binding_static") is not True
    ):
        return None
    return owners, initializers, linked_writes, typed_parameters, stored_types, path_evidence


def _constructed_receiver_proof(
    facts: SourceFacts,
    record: Record,
    binding: CallBinding,
    proof: RecordData,
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> None:
    target = proof.get("target")
    constructor_id = proof.get("constructor_evidence_id")
    assignment_id = proof.get("assignment_evidence_id")
    assignment_name = proof.get("assignment_name")
    targets = declarations.get(target, []) if isinstance(target, str) else []
    calls, assignments = _constructed_receiver_links(
        facts, target, constructor_id, assignment_id, assignment_name
    )
    call_evidence = evidence.get(record.evidence_ids[0]) if record.evidence_ids else None
    assignment_evidence = evidence.get(assignment_id) if isinstance(assignment_id, str) else None
    if (
        len(targets) != 1
        or targets[0].kind != "class"
        or _record_data_value(targets[0].data, "default_instance_result") is not True
        or not _constructed_member_owners_static(target, binding, declarations)
        or not isinstance(constructor_id, str)
        or len(calls) != 1
        or not _constructed_assignment_is_earlier(
            assignment_id,
            assignment_name,
            assignments,
            record,
            call_evidence,
            assignment_evidence,
        )
        or not _constructed_call_matches_source(
            record, binding, target, assignment_name, calls, declarations, evidence
        )
    ):
        raise ValueError("constructed receiver needs a linked earlier allocation witness")


def _constructed_member_owners_static(
    target: JsonValue,
    binding: CallBinding,
    declarations: Mapping[str, list[Record]],
) -> bool:
    if not isinstance(target, str):
        return False
    constructed = declarations.get(target, [])
    method_owner_name = binding.target.rpartition(".")[0]
    method_owners = declarations.get(method_owner_name, [])
    return (
        len(constructed) == 1
        and constructed[0].kind == "class"
        and _record_data_value(constructed[0].data, "source_member_owner_static") is True
        and len(method_owners) == 1
        and method_owners[0].kind == "class"
        and _record_data_value(method_owners[0].data, "source_member_owner_static") is True
    )


def _constructed_call_matches_source(
    record: Record,
    binding: CallBinding,
    target: JsonValue,
    assignment_name: JsonValue,
    constructors: list[Record],
    declarations: Mapping[str, list[Record]],
    evidence: Mapping[str, Evidence],
) -> bool:
    if not isinstance(target, str):
        return False
    if isinstance(assignment_name, str):
        expression = f"{assignment_name}.{_last_segment(binding.target)}"
    elif assignment_name is None and len(constructors) == 1:
        constructor = constructors[0]
        constructor_data = constructor.data
        constructor_expression = constructor_data.get("expression")
        if not isinstance(constructor_expression, str):
            return False
        expression = f"{constructor_expression}().{_last_segment(binding.target)}"
    else:
        return False
    if not _call_expression_matches_source(record, expression, evidence):
        return False
    path_matches, path_evidence = _stored_method_path(target, binding.target, declarations)
    return path_matches and set(path_evidence) <= set(binding.evidence_ids)


def _constructed_receiver_links(
    facts: SourceFacts,
    target: JsonValue,
    constructor_id: JsonValue,
    assignment_id: JsonValue,
    assignment_name: JsonValue,
) -> tuple[list[Record], list[tuple[Record, RecordData]]]:
    target_name = target if isinstance(target, str) else ""
    constructor = constructor_id if isinstance(constructor_id, str) else ""
    assignment = assignment_id if isinstance(assignment_id, str) else ""
    calls: list[Record] = []
    assignments: list[tuple[Record, RecordData]] = []
    for section in facts.sections:
        if section.name is not SourceSectionName.CALLS:
            continue
        for candidate in section.records:
            result = _record_data_value(candidate.data, "result_bindings")
            items = (
                tuple(item for item in result if isinstance(item, RecordData))
                if isinstance(result, tuple)
                else ()
            )
            if constructor in candidate.evidence_ids and _ends_with(candidate.kind, "_call"):
                targets = _record_data_value(candidate.data, "targets")
                if isinstance(targets, tuple) and target_name in targets:
                    calls.append(candidate)
            if constructor not in candidate.evidence_ids:
                continue
            for item in items:
                references = _record_data_value(item, "evidence_ids")
                if (
                    _record_data_value(item, "name") == assignment_name
                    and _record_data_value(item, "target_kind") == "name"
                    and isinstance(references, tuple)
                    and assignment in references
                ):
                    assignments.append((candidate, item))
    return calls, assignments


def _constructed_assignment_is_earlier(
    assignment_id: JsonValue,
    assignment_name: JsonValue,
    assignments: list[tuple[Record, RecordData]],
    record: Record,
    call_evidence: Evidence | None,
    assignment_evidence: Evidence | None,
) -> bool:
    if assignment_id is None:
        return assignment_name is None
    return (
        isinstance(assignment_id, str)
        and isinstance(assignment_name, str)
        and len(assignments) == 1
        and _record_data_value(assignments[0][0].data, "source_scope")
        == _record_data_value(record.data, "source_scope")
        and call_evidence is not None
        and assignment_evidence is not None
        and assignment_evidence.line < call_evidence.line
    )


def _constructor_origin_proof(
    record: Record,
    proof: RecordData,
    declarations: Mapping[str, list[Record]],
) -> None:
    if proof.get("kind") == "provider_member":
        return
    target = proof.get("target")
    constructor_evidence = proof.get("constructor_evidence_id")
    targets = declarations.get(target, []) if isinstance(target, str) else []
    if (
        len(targets) != 1
        or targets[0].kind != "class"
        or _record_data_value(targets[0].data, "default_instance_result") is not True
        or not isinstance(constructor_evidence, str)
        or constructor_evidence not in record.evidence_ids
    ):
        raise ValueError("constructor needs its default-instance declaration and call witness")


def _record_data_value(data: RecordData, key: str) -> JsonValue:
    for name, value in data.entries:
        if name == key:
            return value
    return None


def _starts_with(value: str, prefix: str) -> bool:
    length = len(prefix)
    return len(value) >= length and value[:length] == prefix


def _ends_with(value: str, suffix: str) -> bool:
    length = len(suffix)
    return len(value) >= length and value[len(value) - length :] == suffix


def _source_guard_boolean_members(record: Record, section: SourceSectionName) -> None:
    value = record.data.get("guard_boolean_members")
    if (
        section is not SourceSectionName.SYMBOLS
        or record.kind != "class"
        or not isinstance(value, tuple)
        or any(
            not isinstance(item, RecordData)
            or {key for key, _ in item.entries} != {"name", "evidence_ids"}
            or not isinstance(item.get("name"), str)
            or not item.get("name")
            for item in value
        )
    ):
        raise ValueError("guard Boolean member declarations need a class symbol")
    if len({item.get("name") for item in value if isinstance(item, RecordData)}) != len(value):
        raise ValueError("guard Boolean member declarations must have unique names")
    for item in value:
        if not isinstance(item, RecordData):
            continue
        evidence_ids = item.get("evidence_ids")
        if (
            not isinstance(evidence_ids, tuple)
            or not evidence_ids
            or any(not isinstance(identifier, str) or not identifier for identifier in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            raise ValueError("guard Boolean member evidence_ids must be unique and nonempty")


def _source_guarded_effect(
    record: Record,
    section: SourceSectionName,
    evidence: Mapping[str, Evidence],
    imports: tuple[Record, ...],
) -> None:
    if section is not SourceSectionName.CALLS:
        raise ValueError("guarded effect evidence needs its call owner")
    raw_guarded = record.data.get("guarded_effect")
    if not isinstance(raw_guarded, tuple):
        raise ValueError("guarded effect evidence must be an array")
    binding = call_binding(record.data.get("call_binding"))
    for raw_item in raw_guarded:
        proof = guarded_effect(raw_item)
        if proof.condition_value is not None and not _guard_path_matches_condition(
            record,
            proof.condition.name,
            proof.condition.kind.value,
            proof.condition_value,
            proof.path_evidence_ids,
            evidence,
        ):
            raise ValueError("guarded-effect condition value disagrees with its source path")
        arguments = call_arguments(record.data.get("call_arguments"))
        call_evidence = next(
            (evidence[identifier] for identifier in record.evidence_ids if identifier in evidence),
            None,
        )
        if proof.helper_bindings and not _guarded_helper_arguments_match_source(
            record, proof, arguments, call_evidence, evidence
        ):
            raise ValueError("guarded-effect helper argument disagrees with its source")
        if proof.complete and (
            binding is None or proof.effect_binding_evidence_ids != binding.evidence_ids
        ):
            raise ValueError("guarded effect must reference its canonical call binding")
        if proof.helper_bindings and not _source_helper_target_matches_call(
            record, binding, evidence, imports
        ):
            raise ValueError("guarded-effect helper target disagrees with its written callee")
        if any(
            binding is None or helper.call_id != record.id or helper.target != binding.target
            for helper in proof.helper_bindings
        ):
            raise ValueError("guarded-effect helper identity disagrees with its call binding")


def _source_helper_target_matches_call(
    record: Record,
    binding: CallBinding | None,
    evidence: Mapping[str, Evidence],
    imports: tuple[Record, ...],
) -> bool:
    expression = record.data.get("expression")
    target = binding.target if binding is not None else ""
    source_module = record.data.get("source_module")
    if (
        binding is None
        or binding.origin is not CallBindingOrigin.DIRECT
        or not isinstance(expression, str)
        or not _call_expression_matches_source(record, expression, evidence)
    ):
        return False
    target_module, _, target_name = target.rpartition(".")
    expression_name = expression.rpartition(".")[-1]
    if target_module == source_module:
        return target_name == expression_name
    for imported in imports:
        module = imported.data.get("target_module")
        symbol = imported.data.get("symbol")
        if (
            imported.data.get("source_module") == source_module
            and imported.data.get("binding") == expression
            and imported.data.get("source_binding_unique") is True
            and isinstance(module, str)
            and module + (f".{symbol}" if isinstance(symbol, str) else "") == target
        ):
            return True
    return False


def _guarded_helper_arguments_match_source(
    record: Record,
    proof: GuardedEffectEvidence,
    arguments: tuple[CallArgument, ...] | None,
    call_evidence: Evidence | None,
    evidence: Mapping[str, Evidence],
) -> bool:
    helpers = proof.helper_bindings
    if arguments is None:
        return all(
            actual.token_kind.value == "unknown"
            for helper in helpers
            for actual in helper.arguments
        )
    if call_evidence is None or not _call_arguments_match_source(
        record, arguments, evidence, call_evidence.file
    ):
        return False
    actuals = _source_call_actuals(record, call_evidence)
    if actuals is None:
        return False
    for helper in helpers:
        if len(helper.arguments) != len(arguments):
            return False
        for actual in helper.arguments:
            index = actual.argument_index
            if (
                index >= len(arguments)
                or actual.evidence_ids != arguments[index].evidence_ids
                or actual.condition is not None
                and (
                    actual.condition.kind is not proof.condition.kind
                    or actual.condition.owner != proof.condition.owner
                )
                or not _guarded_actual_matches_condition(actual, actuals[index])
            ):
                return False
    return True


def _source_call_actuals(record: Record, evidence: Evidence) -> tuple[ast.expr, ...] | None:
    parsed = _call_evidence_nodes(evidence.excerpt)
    if parsed is None:
        return None
    roots, line_offset = parsed
    expression = record.data.get("expression")
    calls = [
        node
        for root in roots
        for node in ast.walk(root)
        if isinstance(node, ast.Call)
        and _source_node_starts_at(node, evidence.line, evidence.column, line_offset)
        and _call_expression(node) == expression
    ]
    if len(calls) != 1:
        return None
    node = calls[0]
    positional = [
        argument.value if isinstance(argument, ast.Starred) else argument for argument in node.args
    ]
    return tuple(positional + [keyword.value for keyword in node.keywords])


def _source_node_starts_at(node: ast.AST, line: int, column: int, line_offset: int) -> bool:
    span = _numeric_node_span(node, line, line_offset)
    return span is not None and span[:2] == (line, column)


def _guarded_actual_matches_condition(actual: GuardHelperArgument, expression: ast.expr) -> bool:
    token_kind = actual.token_kind.value
    if token_kind == "unknown":
        return True
    selector = actual.condition
    if token_kind == "boolean_literal":
        return isinstance(expression, ast.Constant) and expression.value is actual.token_value
    if selector is None:
        return False
    candidate = expression
    negated = False
    if isinstance(candidate, ast.UnaryOp) and isinstance(candidate.op, ast.Not):
        candidate = candidate.operand
        negated = True
    matches = (
        isinstance(candidate, ast.Name) and candidate.id == selector.name
        if selector.kind.value == "parameter"
        else isinstance(candidate, ast.Attribute)
        and candidate.attr == selector.name
        and isinstance(candidate.value, ast.Name)
        and candidate.value.id == "self"
    )
    return matches and (token_kind == "not_condition") == negated


def _guard_path_matches_condition(
    record: Record,
    name: str,
    kind: str,
    expected_value: bool,
    path_evidence_ids: tuple[str, ...],
    evidence: Mapping[str, Evidence],
) -> bool:
    call_source = next(
        (evidence[identifier].file for identifier in record.evidence_ids if identifier in evidence),
        None,
    )
    call_evidence = next(
        (evidence[identifier] for identifier in record.evidence_ids if identifier in evidence),
        None,
    )
    call_node = _source_call_node(record, call_evidence)
    for identifier in path_evidence_ids:
        item = evidence.get(identifier)
        if item is None or item.file != call_source:
            continue
        parsed = _parse_numeric_evidence_excerpt(item.excerpt)
        if parsed is None:
            continue
        roots, line_offset = parsed
        for root in roots:
            for node in ast.walk(root):
                if not isinstance(node, ast.If | ast.IfExp):
                    continue
                if not _source_node_starts_at(node.test, item.line, item.column, line_offset):
                    continue
                guard_value = _guard_test_value(node.test, name, kind)
                if (
                    call_evidence is not None
                    and call_evidence.line == item.line
                    and call_evidence.excerpt == item.excerpt
                ):
                    call_node = _source_call_node_in_tree(record, call_evidence, root, line_offset)
                value = _source_guard_branch_value(
                    node, item, guard_value, call_evidence, call_node
                )
                if value is expected_value:
                    return True
    return False


def _source_call_node_in_tree(
    record: Record, item: Evidence | None, root: ast.AST, line_offset: int
) -> ast.Call | None:
    expression = record.data.get("expression")
    if item is None or not isinstance(expression, str):
        return None
    for node in ast.walk(root):
        if (
            isinstance(node, ast.Call)
            and _source_node_starts_at(node, item.line, item.column, line_offset)
            and ast.unparse(node.func) == expression
        ):
            return node
    return None


def _source_call_node(record: Record, item: Evidence | None) -> ast.Call | None:
    if item is None:
        return None
    parsed = _parse_numeric_evidence_excerpt(item.excerpt)
    if parsed is None:
        return None
    roots, line_offset = parsed
    expression = record.data.get("expression")
    if not isinstance(expression, str):
        return None
    for root in roots:
        for node in ast.walk(root):
            if (
                isinstance(node, ast.Call)
                and _source_node_starts_at(node, item.line, item.column, line_offset)
                and ast.unparse(node.func) == expression
            ):
                return node
    return None


def _source_guard_branch_value(
    guard: ast.If | ast.IfExp,
    guard_evidence: Evidence,
    guard_value: bool | None,
    call_evidence: Evidence | None,
    call_node: ast.Call | None,
) -> bool | None:
    if guard_value is None or call_evidence is None:
        return None
    if (
        call_evidence.line == guard_evidence.line
        and call_evidence.excerpt == guard_evidence.excerpt
    ):
        body = guard.body if isinstance(guard, ast.If) else (guard.body,)
        alternate = guard.orelse if isinstance(guard, ast.If) else (guard.orelse,)
        if call_node is not None and any(
            child is call_node for statement in body for child in ast.walk(statement)
        ):
            return guard_value
        if call_node is not None and any(
            child is call_node for statement in alternate for child in ast.walk(statement)
        ):
            return not guard_value
        return None
    guard_indent = len(guard_evidence.excerpt) - len(guard_evidence.excerpt.lstrip(" \t"))
    call_indent = len(call_evidence.excerpt) - len(call_evidence.excerpt.lstrip(" \t"))
    return guard_value if call_indent > guard_indent else not guard_value


def _guard_test_value(expression: ast.expr, name: str, kind: str) -> bool | None:
    candidate = expression
    negated = False
    if isinstance(candidate, ast.UnaryOp) and isinstance(candidate.op, ast.Not):
        candidate = candidate.operand
        negated = True
    matches = (
        isinstance(candidate, ast.Name) and candidate.id == name
        if kind == "parameter"
        else isinstance(candidate, ast.Attribute)
        and candidate.attr == name
        and isinstance(candidate.value, ast.Name)
    )
    return not negated if matches else None


def _numeric_binding_scopes(value: JsonValue, evidence_ids: tuple[str, ...]) -> bool:
    if not isinstance(value, tuple):
        return False
    fields = {"scope_owner", "scope_evidence_id", "scope_symbol_id"}
    return all(
        isinstance(scope, RecordData)
        and {key for key, _ in scope.entries} == fields
        and all(isinstance(scope.get(key), str) and scope.get(key) for key in fields)
        and scope.get("scope_evidence_id") in evidence_ids
        for scope in value
    )


def _source_record(
    record: Record,
    section: SourceSectionName,
    evidence: Mapping[str, Evidence] | None = None,
    imports: tuple[Record, ...] = (),
) -> None:
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
        required = _numeric_operand_record(record, fields)
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
    if "guard_boolean_members" in fields:
        _source_guard_boolean_members(record, section)
    if "call_binding" in fields:
        if section is not SourceSectionName.CALLS:
            raise ValueError("call binding needs its call owner")
        call_binding(record.data.get("call_binding"))
    if any(key == "call_arguments" for key in fields):
        if section is not SourceSectionName.CALLS:
            raise ValueError("call arguments need their call owner")
        call_arguments(record.data.get("call_arguments"))
    if "guarded_effect" in fields:
        _source_guarded_effect(record, section, evidence or {}, imports)
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
    module_files = {item.module: item.rel_path for item in facts.files}
    input_by_path = {item.path: item for item in facts.inputs}
    for binding in facts.provider_bindings:
        _unique(binding.supporting_evidence_ids, "provider alias support")
        evidence = base_by_id.get(binding.evidence_id)
        qualified_name: str = binding.qualified_name
        parts = qualified_name.rpartition(".")
        module: str = qualified_name if binding.kind is ProviderBindingKind.MODULE else parts[0]
        name: str = parts[2]
        source_module = _provider_source_module(evidence.file) if evidence is not None else None
        source_matches = (
            source_module == qualified_name
            if binding.kind is ProviderBindingKind.MODULE
            else qualified_name.startswith(source_module + ".")
            if binding.kind is not ProviderBindingKind.ALIAS and source_module is not None
            else module == source_module
        )
        if (
            binding.kind is ProviderBindingKind.ALIAS
            and (binding.target is None or not _qualified_identifier(binding.target))
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
            not _qualified_identifier(module)
            or not _qualified_identifier(name)
            or module in {item.module for item in facts.files}
            or evidence is None
            or source_module is None
            or not source_matches
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
    resolution_features = _unique(facts.capabilities.resolution_features, "resolution feature")
    _unique((entry.name for entry in facts.capabilities.constructs), "construct capability")
    if names != declared:
        raise ValueError("source sections disagree with declared capabilities")
    records = [record for section in facts.sections for record in section.records]
    declarations_by_id = {
        record.id: record
        for section in facts.sections
        if section.name is SourceSectionName.SYMBOLS
        for record in section.records
    }
    declaration_groups: dict[str, list[Record]] = {}
    for symbol_record in declarations_by_id.values():
        qualified_name_value = symbol_record.data.get("qualified_name")
        if isinstance(qualified_name_value, str):
            group: list[Record] = declaration_groups.setdefault(qualified_name_value, [])
            group.append(symbol_record)
    declarations_by_name = {
        name: tuple(declarations) for name, declarations in declaration_groups.items()
    }
    record_ids = _unique((record.id for record in records), "source record id")
    if file_ids & record_ids:
        raise ValueError("file and record ids collide")
    for record in records:
        if not set(record.evidence_ids).issubset(evidence_ids):
            raise ValueError("dangling source evidence reference")
    source_imports = tuple(
        item
        for imported_section in facts.sections
        if imported_section.name is SourceSectionName.IMPORTS
        for item in imported_section.records
    )
    for section in facts.sections:
        for record in section.records:
            _source_record(record, section.name, base_by_id, source_imports)
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
                    alias_evidence = base_by_id[evidence_id]
                    if (
                        alias_evidence.line,
                        alias_evidence.column,
                        alias_evidence.end_line,
                    ) != (line, column, end_line):
                        raise ValueError("numeric alias derivation disagrees with its evidence")
                numeric_module = record.data.get("module")
                expected_file = (
                    module_files.get(numeric_module) if isinstance(numeric_module, str) else None
                )
                if expected_file is None:
                    raise ValueError("numeric operand needs its source module")
                _validate_numeric_operand_witness(
                    record,
                    base_by_id,
                    declarations_by_id,
                    declarations_by_name,
                    expected_file,
                )
            construct = record.data.get("construct")
            if construct is not None and not any(
                entry.name == construct and entry.status != ConstructSupport.UNSUPPORTED
                for entry in facts.capabilities.constructs
            ):
                raise ValueError("source construct disagrees with declared capabilities")
    fact_ids = record_ids | file_ids
    for record in records:
        guard_members = record.data.get("guard_boolean_members")
        if isinstance(guard_members, tuple) and any(
            isinstance(member, RecordData)
            and isinstance((member_ids := member.get("evidence_ids")), tuple)
            and any(
                not isinstance(identifier, str) or identifier not in evidence_ids
                for identifier in member_ids
            )
            for member in guard_members
        ):
            raise ValueError("guard Boolean member references missing source evidence")
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
    typed_evidence = {item.id: item for item in facts.evidence}
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
            if arguments is not None and call_proof is None:
                raise ValueError("call arguments require the canonical call binding")
            if arguments is not None:
                call_source_module = record.data.get("source_module")
                expected_file = (
                    module_files.get(call_source_module)
                    if isinstance(call_source_module, str)
                    else None
                )
                if expected_file is None or not _call_arguments_match_source(
                    record, arguments, base_by_id, expected_file
                ):
                    raise ValueError("call arguments disagree with their source expression")
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
            guarded_raw = record.data.get("guarded_effect")
            if guarded_raw is not None and (
                facts.profile is not SourceProfile.PYTHON
                or GUARDED_EFFECTS_FEATURE not in resolution_features
            ):
                raise ValueError("guarded-effect facts need their declared Python capability")
            if guarded_raw is not None:
                for item in guarded_raw if isinstance(guarded_raw, tuple) else ():
                    proof = guarded_effect(item)
                    if (
                        not set(
                            (
                                *proof.condition_evidence_ids,
                                *proof.path_evidence_ids,
                                *proof.effect_binding_evidence_ids,
                                *(
                                    identifier
                                    for helper in proof.helper_bindings
                                    for identifier in helper.evidence_ids
                                ),
                                *(
                                    identifier
                                    for helper in proof.helper_bindings
                                    for argument in helper.arguments
                                    for identifier in argument.evidence_ids
                                ),
                            )
                        )
                        <= evidence_ids
                    ):
                        raise ValueError("guarded effect contains dangling evidence references")
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
            if call_proof is not None:
                _call_origin_proof(facts, record, call_proof, declarations, typed_evidence)
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
