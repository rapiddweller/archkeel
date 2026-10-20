# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call graph collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import builtins
import datetime as _datetime
import hashlib
import inspect
import sys
import sysconfig
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TypeVar

from archkeel.ir.facts import (
    NATIVE_CALL_TARGETS,
    CallBindingOrigin,
    EvidenceClass,
    ProviderBinding,
    RuntimeInfo,
    SourceResolution,
    python_identifier,
    stable_id,
)
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, call_excerpt_matches, classified

from .binding_types import BindingKind
from .receiver_types import (
    ReceiverOrigin,
    ReceiverType,
    annotation_receiver_type,
    literal_receiver_type,
)
from .resolve import (
    SymbolIndex,
    call_result_type,
    dotted_expression,
    iterated_call_result_type,
    resolve_name,
)
from .scopes import LexicalScopes, Scope
from .source import (
    FunctionNode,
    ParsedModule,
    add_evidence,
    annotation_text,
    call_id,
    control_flow_contexts,
    definition_id,
    lexical_binding_names,
    location,
    member_escape_references,
    own_scope,
    stable_direct_module_bindings,
)

_BUILTINS = frozenset(dir(builtins))
_ValueT = TypeVar("_ValueT")


def _mapping_value(
    mapping: Mapping[str, _ValueT], key: str, default: _ValueT | None = None
) -> _ValueT | None:
    if key not in mapping:
        return default
    return mapping[key]


def _starts_with(value: str, prefix: str) -> bool:
    length = len(prefix)
    return len(value) >= length and value[:length] == prefix


def _partition_first(value: str, separator: str) -> tuple[str, str, str]:
    for index in range(len(value)):
        if value[index] == separator:
            return value[:index], separator, value[index + 1 :]
    return value, "", ""


def _qualified_identifier(value: str) -> bool:
    start = 0
    for index in range(len(value)):
        if value[index] == ".":
            if not python_identifier(value[start:index]):
                return False
            start = index + 1
    return python_identifier(value[start:])


def _bind_receiver(
    receivers: dict[str, ReceiverType | None], name: str, candidate: ReceiverType | None
) -> None:
    """Merge one binding of `name` into the running receiver map.

    AD-37 requires every binding of a name to agree before a call on it resolves, so a
    conflicting or untyped binding is remembered as None — permanently voiding the name for
    this function — rather than letting whichever binding is merged first or last win.
    """
    if name not in receivers:
        receivers[name] = candidate
        return
    existing = receivers[name]
    if existing is None or candidate is None or existing.type_name != candidate.type_name:
        receivers[name] = None
        return
    if existing.origin is ReceiverOrigin.LITERAL:
        receivers[name] = candidate


def _void_targets(receivers: dict[str, ReceiverType | None], target: ast.expr) -> None:
    """Void every name a `for`, `with` or unpacking target binds (AD-37 case 3).

    None of these prove a single type the way a literal or an annotation does, and a target
    can nest names inside a tuple or list, so every `Name` under it is walked and voided.
    """
    for child in ast.walk(target):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            _bind_receiver(receivers, child.id, None)


def _value_receiver_type(
    value: ast.expr,
    receivers: dict[str, ReceiverType | None],
    scopes: LexicalScopes,
) -> ReceiverType | None:
    """Type an assigned value: a literal proves itself, a call result is documented (AD-40)."""
    literal_type = literal_receiver_type(value)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        if scopes.lookup(value.func, value.func.id).kind is not BindingKind.UNBOUND:
            literal_type = None
    if literal_type:
        return ReceiverType(literal_type, ReceiverOrigin.LITERAL)
    if isinstance(value, ast.Call):
        result_type = call_result_type(value, receiver_types=receivers, scopes=scopes)
        if result_type:
            return ReceiverType(result_type, ReceiverOrigin.DOCUMENTED)
    return None


def _local_receiver_types(node: FunctionNode, scopes: LexicalScopes) -> dict[str, ReceiverType]:
    """Map each name this function binds to its receiver type, where every binding agrees.

    Reuses the own-scope walk `bindings.py` already defines (via `source.own_scope`) instead
    of a second full traversal of the same body.
    """
    receivers: dict[str, ReceiverType | None] = {}
    arguments = node.args
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        type_name = annotation_receiver_type(annotation_text(argument.annotation))
        if type_name:
            _bind_receiver(
                receivers, argument.arg, ReceiverType(type_name, ReceiverOrigin.ANNOTATION)
            )
    for statement in own_scope(node):
        scope = scopes.by_node.get(statement)
        if scope is None or scope.node is not node:
            continue
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            candidate = (
                _value_receiver_type(statement.value, receivers, scopes)
                if statement.value
                else None
            )
            if candidate is None:
                annotated_type = annotation_receiver_type(annotation_text(statement.annotation))
                candidate = (
                    ReceiverType(annotated_type, ReceiverOrigin.ANNOTATION)
                    if annotated_type
                    else None
                )
            _bind_receiver(receivers, statement.target.id, candidate)
        elif isinstance(statement, ast.Assign):
            candidate = _value_receiver_type(statement.value, receivers, scopes)
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    _bind_receiver(receivers, target.id, candidate)
                else:
                    _void_targets(receivers, target)
        elif isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            _bind_receiver(receivers, statement.target.id, None)
        elif isinstance(statement, ast.For | ast.AsyncFor):
            _void_targets(receivers, statement.target)
        elif isinstance(statement, ast.withitem) and statement.optional_vars is not None:
            _void_targets(receivers, statement.optional_vars)
        elif isinstance(statement, ast.NamedExpr):
            _bind_receiver(receivers, statement.target.id, None)
        elif isinstance(statement, ast.ExceptHandler) and statement.name:
            _bind_receiver(receivers, statement.name, None)
    return {name: value for name, value in receivers.items() if value is not None}


class CallCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        index: SymbolIndex,
        evidence: dict[str, RawEvidence],
        provider_bindings: Sequence[ProviderBinding] = (),
        runtime: RuntimeInfo | None = None,
        imports: Sequence[RawRecord] = (),
    ) -> None:
        self.module = module
        self.index = index
        self.symbol_evidence = index.evidence
        self.evidence = evidence
        self.provider_bindings = {item.qualified_name: item for item in provider_bindings}
        self.runtime = runtime
        self.imports = tuple(
            item
            for item in imports
            if _mapping_value(item["data"], "source_module") == module.module
        )
        self.items: list[RawRecord] = []
        self.scopes = LexicalScopes.for_module(module)
        self.receivers = {
            node: _local_receiver_types(node, self.scopes)
            for node in module.all_nodes
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        self.parents = self.scopes.parents
        self.stable_bindings = stable_direct_module_bindings(module)
        self.escaped_bindings = {
            (binding.owner.node, reference.id)
            for reference in member_escape_references(
                module, module.all_nodes, member_surface=True, owner_exposure_only=True
            )
            if self._receiver_escape_reference(reference)
            if (binding := self.scopes.lookup(reference, reference.id)).owner is not None
        }
        self.escaped_native_targets = {
            target
            for call in module.all_nodes
            if isinstance(call, ast.Call) and not self._is_builtin_native_mutator(call)
            for argument in [*call.args, *(item.value for item in call.keywords)]
            for reference in ast.walk(argument)
            if isinstance(reference, ast.Name)
            for target in self._native_expression_targets(reference)
        }
        builtin_mutator_receivers = {
            call.args[0]
            for call in module.all_nodes
            if (
                isinstance(call, ast.Call)
                and self._is_builtin_native_mutator(call)
                and call.args
                and isinstance(call.args[0], ast.Name)
                and self._native_expression_targets(call.args[0])
            )
        }
        self.escaped_native_targets.update(
            target
            for reference in member_escape_references(
                module, module.all_nodes, member_surface=True, owner_exposure_only=True
            )
            if reference not in builtin_mutator_receivers
            for target in self._native_expression_targets(reference)
        )
        self.scope_bindings: dict[ast.ClassDef | FunctionNode, frozenset[str]] = {}

    def _construction(
        self,
        node: ast.Call,
        expression: str,
        status: SourceResolution,
        targets: list[str],
        truncated: bool,
    ) -> RecordData | None:
        classes = [target for target in targets if target in self.index.constructor_results]
        if not classes:
            return None
        if dotted_expression(node.func) is None:
            return None
        root = expression.split(".")[0]
        child: ast.AST = node
        while child in self.parents:
            parent = self.parents[child]
            if isinstance(
                parent, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
            ):
                return None
            if isinstance(parent, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if child not in parent.body:
                    return None
                shadowed = self.scope_bindings.get(parent)
                if shadowed is None:
                    shadowed = lexical_binding_names(parent)
                    self.scope_bindings[parent] = shadowed
                if root in shadowed:
                    return None
            child = parent
        proven = (
            isinstance(node.func, ast.Name)
            and status == SourceResolution.RESOLVED
            and len(classes) == 1
            and root in self.stable_bindings
            and self.index.constructor_results[classes[0]]
        )
        return {
            "status": SourceResolution.RESOLVED if proven else SourceResolution.PARTIALLY_RESOLVED,
            "targets": classes,
            "candidates_truncated": truncated,
            "reason": "Stable class with default allocation and initialization"
            if proven
            else "Class call recorded; constructor result type is not proven",
        }

    def _result_bindings(self, node: ast.Call, call_id: str) -> list[RecordData]:
        parent = self.parents.get(node)
        if not isinstance(parent, ast.Assign | ast.AnnAssign) or parent.value is not node:
            return []
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        contexts = [
            {
                "kind": context.kind,
                "branch": context.branch,
                "evidence_ids": [add_evidence(self.evidence, self.module, context.node)],
            }
            for context in control_flow_contexts(parent, self.parents)
        ]
        result: list[RecordData] = []
        for target in targets:
            if not isinstance(target, ast.Name | ast.Attribute | ast.Subscript):
                continue
            name = annotation_text(target) or "<unparseable>"
            line, _, column = location(target)
            legacy_id = definition_id(self.module, parent, f"{self.module.module}.{name}")
            identity = (
                legacy_id
                if (
                    self.scopes.by_node[node] is self.scopes.root
                    and isinstance(target, ast.Name)
                    and legacy_id in self.index.binding_ids
                )
                else stable_id("VALUEBIND", call_id, line, column, name)
            )
            result.append(
                {
                    "id": identity,
                    "name": name,
                    "target_kind": "name"
                    if isinstance(target, ast.Name)
                    else "attribute"
                    if isinstance(target, ast.Attribute)
                    else "subscript",
                    "annotation": annotation_text(parent.annotation)
                    if isinstance(parent, ast.AnnAssign)
                    else None,
                    "initializer": annotation_text(node),
                    "evidence_ids": [add_evidence(self.evidence, self.module, target)],
                    "definition_contexts": contexts,
                }
            )
        return result

    def _receiver(self, expression: ast.expr, name: str) -> ReceiverType | None:
        owner = self.scopes.lookup(expression, name).owner
        if owner is None:
            return None
        if isinstance(owner.node, ast.FunctionDef | ast.AsyncFunctionDef):
            return self.receivers.get(owner.node, {}).get(name)
        if not isinstance(owner.node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
            return None
        if len(owner.node.generators) != 1:
            return None
        generator = owner.node.generators[0]
        if (
            generator.is_async
            or not isinstance(generator.target, ast.Name)
            or generator.target.id != name
            or owner.bindings.get(name) != [generator.target]
            or not isinstance(generator.iter, ast.Call)
        ):
            return None
        receivers: dict[str, ReceiverType] = {}
        for child in ast.walk(generator.iter.func):
            if not isinstance(child, ast.Name):
                continue
            receiver = self._receiver(child, child.id)
            if receiver is not None:
                receivers[child.id] = receiver
        if any(value.origin is ReceiverOrigin.ANNOTATION for value in receivers.values()) and (
            self.scopes.lookup(generator.iter, "str").kind is not BindingKind.UNBOUND
        ):
            return None
        element = iterated_call_result_type(
            generator.iter, receiver_types=receivers, scopes=self.scopes
        )
        return ReceiverType(element, ReceiverOrigin.DOCUMENTED) if element is not None else None

    def _enclosing_class(self, node: ast.AST) -> ast.ClassDef | None:
        current = node
        while current in self.parents:
            current = self.parents[current]
            if isinstance(current, ast.ClassDef):
                return current
        return None

    def _stored_type(self, node: ast.Attribute) -> tuple[str, list[str], dict[str, object]] | None:
        """Prove a field copied once from one typed initializer parameter."""
        context = self._stored_initializer_context(node)
        if context is None:
            return None
        owner, initializer, receiver_name, reassigned = context
        write_parameter = self._stored_write_parameter(node, owner, initializer, reassigned)
        if write_parameter is None:
            return None
        write, parameter = write_parameter
        return self._stored_field_identity(node, owner, receiver_name, write, parameter)

    def _stored_initializer_context(
        self, node: ast.Attribute
    ) -> tuple[ast.ClassDef, ast.FunctionDef | ast.AsyncFunctionDef, str, set[str]] | None:
        if not isinstance(node.value, ast.Name):
            return None
        owner = self._enclosing_class(node)
        if owner is None:
            return None
        constructors = [
            child
            for child in owner.body
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            and child.name == "__init__"
        ]
        if len(constructors) != 1 or constructors[0].decorator_list:
            return None
        initializer = constructors[0]
        if control_flow_contexts(initializer, self.parents):
            return None
        parameters = [*initializer.args.posonlyargs, *initializer.args.args]
        if not parameters or parameters[0].arg != node.value.id:
            return None
        # The receiver and copied parameter must keep their entry values throughout __init__.
        receiver_name = parameters[0].arg
        reassigned: set[str] = set()
        for child in ast.walk(initializer):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                reassigned.add(child.id)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                reassigned.add(child.name)
        if receiver_name in reassigned or node.value.id != receiver_name:
            return None
        return owner, initializer, receiver_name, reassigned

    def _stored_write_parameter(
        self,
        node: ast.Attribute,
        owner: ast.ClassDef,
        initializer: ast.FunctionDef | ast.AsyncFunctionDef,
        reassigned: set[str],
    ) -> tuple[ast.Assign | ast.AnnAssign, ast.arg] | None:
        receiver = node.value
        if not isinstance(receiver, ast.Name):
            return None
        writes: list[ast.Assign | ast.AnnAssign] = []
        for statement in ast.walk(owner):
            if isinstance(statement, ast.Assign | ast.AnnAssign):
                targets = (
                    statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                )
                if any(
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == receiver.id
                    and target.attr == node.attr
                    for target in targets
                ):
                    writes.append(statement)
            elif isinstance(statement, ast.Delete) and any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == receiver.id
                and target.attr == node.attr
                for target in statement.targets
            ):
                return None
        if len(writes) != 1:
            return None
        write = writes[0]
        if control_flow_contexts(write, self.parents) or not self._in_direct_function_body(
            write, initializer
        ):
            return None
        value = write.value
        if not isinstance(value, ast.Name) or value.id == receiver.id:
            return None
        parameters = [*initializer.args.posonlyargs, *initializer.args.args]
        matching = [argument for argument in parameters[1:] if argument.arg == value.id]
        if len(matching) != 1:
            return None
        [parameter] = matching
        if parameter.arg in reassigned:
            return None
        return write, parameter

    def _stored_field_identity(
        self,
        node: ast.Attribute,
        owner: ast.ClassDef,
        receiver_name: str,
        write: ast.Assign | ast.AnnAssign,
        parameter: ast.arg,
    ) -> tuple[str, list[str], dict[str, object]] | None:
        if not isinstance(parameter.annotation, ast.Name | ast.Attribute):
            return None
        annotation = self._annotation_identity(parameter.annotation)
        if annotation is None:
            return None
        type_name, import_evidence = annotation
        class_name = f"{self.scopes.by_node[owner].qualified_name}.{owner.name}"
        declarations = self._stored_field_declarations(node, owner, class_name, type_name)
        if declarations is None:
            return None
        declaration, owner_declaration = declarations
        # Attribute writes through any receiver spelling, augmented writes, deletes, and
        # reflective mutation make this intentionally small proof inapplicable.
        if self._field_mutated_outside_write(owner, receiver_name, node.attr, write):
            return None
        current_method = self._stored_call_method(node)
        if current_method is None:
            return None
        write_evidence = add_evidence(self.evidence, self.module, write)
        annotation_evidence = add_evidence(self.evidence, self.module, parameter.annotation)
        initializer_declaration = self.index.binding_declarations.get(f"{class_name}.__init__")
        if initializer_declaration is not None:
            typed_writes = _mapping_value(
                initializer_declaration["data"], "stored_field_writes", []
            )
            if not isinstance(typed_writes, list):
                return None
            for typed_write in typed_writes:
                if (
                    typed_write.get("evidence_id") == write_evidence
                    and typed_write.get("annotation_evidence_id") == annotation_evidence
                    and typed_write.get("field") == node.attr
                    and typed_write.get("parameter") == parameter.arg
                ):
                    typed_write["annotation_target"] = type_name
        evidence = [
            *declaration["evidence_ids"],
            *owner_declaration["evidence_ids"],
            write_evidence,
            annotation_evidence,
            *import_evidence,
        ]
        return (
            type_name,
            evidence,
            {
                "kind": "stored_field",
                "owner": class_name,
                "field": node.attr,
                "parameter": parameter.arg,
                "target": type_name,
                "witness_evidence_ids": [write_evidence, annotation_evidence],
            },
        )

    def _annotation_identity(self, annotation: ast.expr) -> tuple[str, list[str]] | None:
        spelling = dotted_expression(annotation)
        if spelling is None:
            return None
        root, separator, suffix = _partition_first(spelling, ".")
        imported = [row for row in self.imports if _mapping_value(row["data"], "binding") == root]
        if imported:
            if len(imported) != 1 or root not in self.stable_bindings:
                return None
            data = imported[0]["data"]
            origin = _mapping_value(data, "origin_definition")
            if (
                _mapping_value(data, "module_level_import") is not True
                or _mapping_value(data, "under_type_checking") is not False
                or _mapping_value(data, "source_binding_unique") is not True
                or _mapping_value(data, "symbols_known") is not True
                or _mapping_value(data, "origin_binding_unique") is not True
                or _mapping_value(data, "reexport_candidate") is True
                or not isinstance(origin, str)
                or not _qualified_identifier(origin)
            ):
                return None
            target = origin + (f".{suffix}" if separator else "")
            return target, imported[0]["evidence_ids"]
        status, targets, _, _ = resolve_name(annotation, index=self.index, scopes=self.scopes)
        if status is SourceResolution.RESOLVED and len(targets) == 1:
            return targets[0], []
        return None

    def _stored_field_declarations(
        self, node: ast.Attribute, owner: ast.ClassDef, class_name: str, target: str
    ) -> tuple[RawRecord, RawRecord] | None:
        declaration = self.index.binding_declarations.get(class_name)
        if (
            declaration is None
            or declaration["kind"] != "class"
            or _mapping_value(declaration["data"], "source_binding_unique") is not True
            or _mapping_value(declaration["data"], "source_member_binding_static") is not True
            or _mapping_value(declaration["data"], "class_header_static") is not True
            or any(
                isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                and child.name in {"__getattribute__", "__getattr__", "__setattr__", node.attr}
                for child in owner.body
            )
        ):
            return None
        owner_declaration = self.index.binding_declarations.get(target)
        if (
            owner_declaration is None
            or owner_declaration["kind"] != "class"
            or _mapping_value(owner_declaration["data"], "source_binding_unique") is not True
            or _mapping_value(owner_declaration["data"], "source_member_binding_static") is not True
        ):
            return None

        return declaration, owner_declaration

    def _stored_call_method(
        self, node: ast.Attribute
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        receiver = node.value
        if not isinstance(receiver, ast.Name):
            return None
        current_method = next(
            (
                ancestor
                for ancestor in self._ancestors(node)
                if isinstance(ancestor, ast.FunctionDef | ast.AsyncFunctionDef)
            ),
            None,
        )
        if current_method is None or current_method.decorator_list:
            return None
        method_args = [*current_method.args.posonlyargs, *current_method.args.args]
        if not method_args or method_args[0].arg != receiver.id:
            return None
        if any(
            isinstance(child, ast.Name)
            and child.id == receiver.id
            and isinstance(child.ctx, ast.Store)
            for child in ast.walk(current_method)
        ):
            return None
        binding = self.scopes.lookup(receiver, receiver.id)
        if binding.owner is None or self._receiver_escaped(binding.owner, receiver.id):
            return None
        return current_method

    def _ancestors(self, node: ast.AST) -> Iterator[ast.AST]:
        current = node
        while current in self.parents:
            current = self.parents[current]
            yield current

    def _receiver_escaped(self, owner: Scope, name: str) -> bool:
        aliases = {name}
        while True:
            if any((owner.node, alias) in self.escaped_bindings for alias in aliases):
                return True
            expanded = set(aliases)
            for alias, sites in owner.bindings.items():
                for site in sites:
                    if not isinstance(site, ast.Name) or not isinstance(site.ctx, ast.Store):
                        continue
                    assignment = self.parents.get(site)
                    value = (
                        assignment.value
                        if isinstance(assignment, ast.Assign | ast.AnnAssign)
                        else None
                    )
                    if isinstance(value, ast.Name) and value.id in aliases:
                        source = self.scopes.lookup(value, value.id)
                        if source.owner is owner:
                            expanded.add(alias)
            if expanded == aliases:
                return False
            aliases = expanded

    def _receiver_escape_reference(self, reference: ast.Name) -> bool:
        current: ast.AST = reference
        while current in self.parents:
            parent = self.parents[current]
            if isinstance(parent, ast.Call):
                if current in parent.args or any(
                    keyword.value is current for keyword in parent.keywords
                ):
                    return True
                return False
            if isinstance(parent, ast.Attribute):
                if isinstance(parent.ctx, ast.Store | ast.Del):
                    return True
                current = parent
                continue
            if isinstance(parent, ast.Compare) and current in (
                parent.left,
                *parent.comparators,
            ):
                return False
            if isinstance(parent, ast.Assign | ast.AnnAssign):
                value = parent.value
                targets = parent.targets if isinstance(parent, ast.Assign) else (parent.target,)
                if (
                    value is current
                    and isinstance(value, ast.Name)
                    and all(isinstance(target, ast.Name) for target in targets)
                ):
                    return False
                return True
            if isinstance(
                parent, ast.AugAssign | ast.NamedExpr | ast.Return | ast.Yield | ast.YieldFrom
            ):
                return True
            if isinstance(
                parent, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
            ):
                return True
            current = parent
        return True

    def _in_direct_function_body(self, node: ast.AST, function: ast.AST) -> bool:
        current = node
        while current in self.parents and self.parents[current] is not function:
            current = self.parents[current]
        return (
            isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
            and current in function.body
        )

    def _field_mutated_outside_write(
        self, owner: ast.ClassDef, receiver: str, field: str, allowed: ast.AST
    ) -> bool:
        allowed_nodes = set(ast.walk(allowed))
        aliases = {receiver}
        for child in ast.walk(owner):
            if isinstance(child, ast.Assign) and isinstance(child.value, ast.Name):
                if child.value.id in aliases:
                    aliases.update(
                        target.id for target in child.targets if isinstance(target, ast.Name)
                    )
            elif isinstance(child, ast.AnnAssign) and isinstance(child.value, ast.Name):
                if child.value.id in aliases and isinstance(child.target, ast.Name):
                    aliases.add(child.target.id)
        for child in ast.walk(owner):
            if child in allowed_nodes:
                continue
            if isinstance(child, ast.Attribute) and child.attr == field:
                root: ast.expr = child
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in aliases:
                    if isinstance(child.ctx, (ast.Store, ast.Del)):
                        return True
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id in {"setattr", "delattr"}
            ):
                if (
                    len(child.args) >= 2
                    and isinstance(child.args[0], ast.Name)
                    and child.args[0].id in aliases
                ):
                    member = child.args[1]
                    if not isinstance(member, ast.Constant) or member.value == field:
                        return True
        return False

    def _constructed_type(
        self, expression: ast.expr, call_site: ast.expr
    ) -> tuple[str, list[str], dict[str, object]] | None:
        if isinstance(expression, ast.Name):
            binding = self.scopes.lookup(expression, expression.id)
            if (
                binding.uncertain
                or binding.owner is None
                or self._receiver_escaped(binding.owner, expression.id)
            ):
                return None
            sites = binding.owner.bindings.get(expression.id, ())
            if len(sites) != 1 or not isinstance(sites[0], ast.Name):
                return None
            parent = self.parents.get(sites[0])
            if not isinstance(parent, ast.Assign | ast.AnnAssign):
                return None
            if (
                control_flow_contexts(parent, self.parents)
                or not self._in_direct_function_body(parent, binding.owner.node)
                or parent.lineno >= call_site.lineno
            ):
                return None
            value = parent.value
            if not isinstance(value, ast.Call):
                return None
            construction = self._constructor_type(value)
            if construction is None:
                return None
            type_name, evidence = construction
            constructor_evidence = add_evidence(self.evidence, self.module, value)
            assignment_evidence = add_evidence(self.evidence, self.module, sites[0])
            assignment_name = expression.id
            return (
                type_name,
                [*evidence, constructor_evidence, assignment_evidence],
                {
                    "kind": "construction",
                    "target": type_name,
                    "constructor_evidence_id": constructor_evidence,
                    "assignment_evidence_id": assignment_evidence,
                    "assignment_name": assignment_name,
                },
            )
        if isinstance(expression, ast.Call):
            construction = self._constructor_type(expression)
            if construction is None:
                return None
            type_name, evidence = construction
            constructor_evidence = add_evidence(self.evidence, self.module, expression)
            return (
                type_name,
                [*evidence, constructor_evidence],
                {
                    "kind": "construction",
                    "target": type_name,
                    "constructor_evidence_id": constructor_evidence,
                    "assignment_evidence_id": None,
                    "assignment_name": None,
                },
            )
        return None

    def _constructor_type(self, call: ast.Call) -> tuple[str, list[str]] | None:
        status, targets, _, _ = resolve_name(call.func, index=self.index, scopes=self.scopes)
        if status is not SourceResolution.RESOLVED or len(targets) != 1:
            return None
        type_name = targets[0]
        declaration = self.index.binding_declarations.get(type_name)
        if (
            declaration is None
            or declaration["kind"] != "class"
            or not self.index.constructor_results.get(type_name)
            or _mapping_value(declaration["data"], "source_binding_unique") is not True
            or _mapping_value(declaration["data"], "class_header_static") is not True
            or _mapping_value(declaration["data"], "default_instance_result") is not True
        ):
            return None
        root = call.func
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            binding = self.scopes.lookup(root, root.id)
            if binding.uncertain or binding.owner is None:
                return None
            if binding.owner is self.scopes.root and root.id not in self.stable_bindings:
                return None
            if (
                binding.kind in {BindingKind.MODULE, BindingKind.SYMBOL}
                and len(binding.targets) != 1
            ):
                return None
        provider = self.provider_bindings.get(type_name)
        return type_name, [
            *declaration["evidence_ids"],
            *([provider.evidence_id] if provider is not None else []),
            add_evidence(self.evidence, self.module, call.func),
        ]

    def _method_declaration(
        self, owner: str, method: str
    ) -> tuple[str, RawRecord, list[str]] | None:
        seen: set[str] = set()
        current = owner
        inherited_evidence: list[str] = []
        while current not in seen:
            seen.add(current)
            target = f"{current}.{method}"
            declaration = self.index.binding_declarations.get(target)
            if declaration is not None:
                if (
                    declaration["kind"] != "method"
                    or _mapping_value(declaration["data"], "parent") != current
                    or bool(_mapping_value(declaration["data"], "decorators"))
                ):
                    return None
                return target, declaration, inherited_evidence
            owner_declaration = self.index.binding_declarations.get(current)
            if (
                owner_declaration is None
                or _mapping_value(owner_declaration["data"], "class_header_static") is not True
            ):
                return None
            bases = _mapping_value(owner_declaration["data"], "base_declarations")
            if not isinstance(bases, list) or len(bases) != 1 or not isinstance(bases[0], dict):
                return None
            base = bases[0]
            targets = base.get("targets")
            evidence = base.get("evidence_ids")
            if (
                base.get("status") != SourceResolution.RESOLVED
                or not isinstance(targets, list)
                or len(targets) != 1
                or not isinstance(targets[0], str)
                or not isinstance(evidence, list)
            ):
                return None
            current = targets[0]
            inherited_evidence.extend((*owner_declaration["evidence_ids"], *evidence))
        return None

    def _native_import_target(self, node: ast.expr) -> tuple[str, list[str]] | None:
        dotted = dotted_expression(node)
        if dotted is None:
            return None
        root, separator, suffix = _partition_first(dotted, ".")
        binding = self.scopes.lookup(node, root)
        if (
            binding.kind not in {BindingKind.MODULE, BindingKind.SYMBOL}
            or binding.uncertain
            or len(binding.targets) != 1
            or binding.owner is None
            or binding.targets[0] in self.escaped_native_targets
        ):
            return None
        sites = binding.owner.bindings.get(root, ())
        if len(sites) != 1 or not isinstance(sites[0], ast.Import | ast.ImportFrom):
            return None
        target = binding.targets[0] + (f".{suffix}" if separator else "")
        if target not in NATIVE_CALL_TARGETS or self._native_target_revoked(target):
            return None
        return target, [add_evidence(self.evidence, self.module, sites[0])]

    def _native_target_revoked(self, target: str) -> bool:
        sys_modules_aliases = {"sys.modules"}
        changed = True
        while changed:
            changed = False
            for statement in ast.walk(self.module.tree):
                if isinstance(statement, ast.Assign):
                    source_alias = (
                        statement.value.id
                        if isinstance(statement.value, ast.Name)
                        else dotted_expression(statement.value)
                    )
                    if source_alias in sys_modules_aliases:
                        for assigned in statement.targets:
                            if (
                                isinstance(assigned, ast.Name)
                                and assigned.id not in sys_modules_aliases
                            ):
                                sys_modules_aliases.add(assigned.id)
                                changed = True
                elif isinstance(statement, ast.ImportFrom) and statement.module == "sys":
                    if any(item.name == "modules" for item in statement.names):
                        sys_modules_aliases.add(
                            next(
                                item.asname or item.name
                                for item in statement.names
                                if item.name == "modules"
                            )
                        )
        for node in ast.walk(self.module.tree):
            targets: tuple[ast.expr, ...] = ()
            if isinstance(node, ast.Assign):
                targets = tuple(item for item in node.targets if isinstance(item, ast.expr))
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                targets = (node.target,)
            elif isinstance(node, ast.Delete):
                targets = tuple(item for item in node.targets if isinstance(item, ast.expr))
            if self._native_targets_mutated(node, targets, target):
                return True
            for mutation in targets:
                if not isinstance(mutation, ast.Subscript):
                    continue
                table = dotted_expression(mutation.value)
                module = _partition_first(target, ".")[0]
                if (
                    table in sys_modules_aliases
                    and isinstance(mutation.slice, ast.Constant)
                    and mutation.slice.value == module
                ):
                    return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"setattr", "delattr"} and len(node.args) >= 2:
                    member = node.args[1]
                    for owner in self._native_expression_targets(node.args[0]):
                        if isinstance(member, ast.Constant) and isinstance(member.value, str):
                            if f"{owner}.{member.value}" == target:
                                return True
                        elif target == owner or _starts_with(target, f"{owner}."):
                            return True
        return False

    def _is_builtin_native_mutator(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Name) or node.func.id not in {"setattr", "delattr"}:
            return False
        binding = self.scopes.lookup(node.func, node.func.id)
        return binding.kind is BindingKind.UNBOUND and not binding.uncertain

    def _native_expression_targets(
        self, expression: ast.expr, seen: frozenset[str] = frozenset()
    ) -> set[str]:
        value = dotted_expression(expression)
        if value is None:
            return set()
        root, separator, suffix = _partition_first(value, ".")
        binding = self.scopes.lookup(expression, root)
        if binding.kind in {BindingKind.MODULE, BindingKind.SYMBOL} and len(binding.targets) == 1:
            origins = {binding.targets[0]}
        elif binding.owner is not None and root not in seen:
            origins = self._native_alias_targets(root, binding.owner, seen | {root})
        else:
            return set()
        return {origin + (f".{suffix}" if separator else "") for origin in origins}

    def _native_alias_targets(self, name: str, owner: Scope, seen: frozenset[str]) -> set[str]:
        bindings: dict[str, list[ast.AST]] = owner.bindings
        sites = bindings.get(name, ())
        origins: set[str] = set()
        for site in sites:
            if not isinstance(site, ast.Name):
                continue
            assignment = self.parents.get(site)
            if not isinstance(assignment, ast.Assign | ast.AnnAssign) or assignment.value is None:
                continue
            origins = origins | self._native_expression_targets(assignment.value, seen)
        return origins

    def _native_targets_mutated(
        self,
        node: ast.AST,
        targets: tuple[ast.expr, ...],
        target: str,
    ) -> bool:
        for item in targets:
            if isinstance(item, ast.Name):
                binding = self.scopes.lookup(item, item.id)
                sites = binding.owner.bindings.get(item.id, ()) if binding.owner else ()
                if not any(
                    isinstance(self.parents.get(site), ast.Import | ast.ImportFrom)
                    for site in sites
                ):
                    continue
            changed_targets = self._native_expression_targets(item)
            if isinstance(item, ast.Name) and isinstance(node, ast.Assign | ast.AnnAssign):
                value = node.value
                if value is not None and changed_targets & self._native_expression_targets(value):
                    continue
            for changed_target in changed_targets:
                if target == changed_target or _starts_with(target, f"{changed_target}."):
                    return True
        return False

    def _native_call(
        self, node: ast.Call
    ) -> tuple[str, CallBindingOrigin, list[str], dict[str, object]] | None:
        direct = self._native_import_target(node.func)
        if direct is not None:
            return self._native_import_call(direct)
        return self._native_random_receiver_call(node)

    def _native_import_call(
        self, direct: tuple[str, list[str]]
    ) -> tuple[str, CallBindingOrigin, list[str], dict[str, object]] | None:
        target, evidence = direct
        provider = self.provider_bindings.get(target)
        if provider is not None:
            evidence = [*evidence, provider.evidence_id]
        origin = (
            CallBindingOrigin.CONSTRUCTOR
            if target == "random.Random"
            else CallBindingOrigin.NATIVE_RECEIVER
            if _starts_with(target, "random.Random.")
            else CallBindingOrigin.NATIVE
        )
        if provider is not None:
            proof: dict[str, object] = {
                "kind": "provider_member",
                "target": target,
                "provider_evidence_id": provider.evidence_id,
                "runtime_name": self.runtime.name if self.runtime is not None else "python",
                "runtime_version": self.runtime.version if self.runtime is not None else "unknown",
            }
        elif self.runtime is not None:
            if target != "datetime.datetime.now":
                return None
            descriptor_proof = self._datetime_descriptor_proof(target)
            if descriptor_proof is None:
                return None
            proof = {
                "kind": "native_descriptor",
                "target": target,
                "runtime_name": self.runtime.name,
                "runtime_version": self.runtime.version,
                **descriptor_proof,
                "witness_evidence_ids": evidence,
            }
        else:
            return None
        return target, origin, evidence, proof

    def _native_random_receiver_call(
        self, node: ast.Call
    ) -> tuple[str, CallBindingOrigin, list[str], dict[str, object]] | None:
        if not isinstance(node.func, ast.Attribute):
            return None
        receiver = node.func.value
        constructor: ast.Call | None = receiver if isinstance(receiver, ast.Call) else None
        assignment_evidence: str | None = None
        if isinstance(receiver, ast.Name):
            binding = self.scopes.lookup(receiver, receiver.id)
            if (
                binding.uncertain
                or binding.owner is None
                or self._receiver_escaped(binding.owner, receiver.id)
            ):
                return None
            sites = binding.owner.bindings.get(receiver.id, ())
            if len(sites) != 1 or not isinstance(sites[0], ast.Name):
                return None
            assignment = self.parents.get(sites[0])
            if (
                not isinstance(assignment, ast.Assign | ast.AnnAssign)
                or assignment.value is None
                or isinstance(assignment, ast.Assign)
                and len(assignment.targets) != 1
            ):
                return None
            if (assignment.lineno, assignment.col_offset) >= (node.lineno, node.col_offset):
                return None
            if self._native_instance_member_changed(receiver.id, node):
                return None
            constructor = assignment.value if isinstance(assignment.value, ast.Call) else None
            assignment_evidence = add_evidence(self.evidence, self.module, sites[0])
        if constructor is None:
            return None
        type_identity = self._native_import_target(constructor.func)
        if type_identity is None or type_identity[0] != "random.Random":
            return None
        target = f"{type_identity[0]}.{node.func.attr}"
        if target not in NATIVE_CALL_TARGETS or self._native_target_revoked(target):
            return None
        provider = self.provider_bindings.get(target)
        if provider is None:
            return None
        constructor_evidence = add_evidence(self.evidence, self.module, constructor)
        return (
            target,
            CallBindingOrigin.NATIVE_RECEIVER,
            [
                *type_identity[1],
                provider.evidence_id,
                constructor_evidence,
                *([assignment_evidence] if assignment_evidence is not None else []),
            ],
            {
                "kind": "provider_member",
                "target": target,
                "provider_evidence_id": provider.evidence_id,
                "runtime_name": self.runtime.name if self.runtime is not None else "python",
                "runtime_version": self.runtime.version if self.runtime is not None else "unknown",
            },
        )

    def _native_instance_member_changed(self, name: str, call: ast.Call) -> bool:
        call_position = (call.lineno, call.col_offset)
        owner = self.scopes.lookup(call, name).owner
        for node in ast.walk(self.module.tree):
            targets: tuple[ast.expr, ...] = ()
            if isinstance(node, ast.Assign):
                targets = tuple(item for item in node.targets if isinstance(item, ast.expr))
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                targets = (node.target,)
            elif isinstance(node, ast.Delete):
                targets = tuple(item for item in node.targets if isinstance(item, ast.expr))
            if any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == name
                and self.scopes.lookup(target.value, name).owner is owner
                for target in targets
            ):
                return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"setattr", "delattr"} and len(node.args) >= 2:
                    receiver_owner, member = node.args[:2]
                    if (
                        isinstance(receiver_owner, ast.Name)
                        and receiver_owner.id == name
                        and self.scopes.lookup(receiver_owner, name).owner
                        is self.scopes.lookup(call, name).owner
                        and isinstance(member, ast.Constant)
                        and isinstance(member.value, str)
                    ):
                        return True
            if (
                isinstance(node, ast.Name)
                and node.id == name
                and isinstance(node.ctx, ast.Store | ast.Del)
                and self.scopes.lookup(node, name).owner is owner
                and (node.lineno, node.col_offset) > call_position
            ):
                return True
        return False

    def _datetime_descriptor_proof(self, target: str) -> dict[str, object] | None:
        if target != "datetime.datetime.now" or sys.implementation.name != "cpython":
            return None
        try:
            module = _datetime
            owner = module.datetime
            descriptor = inspect.getattr_static(owner, "now")
            module_file = module.__file__
            if not isinstance(module_file, str):
                return None
            source_path = Path(module_file).resolve()
            stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
            source_path.relative_to(stdlib)
            source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except (AttributeError, ImportError, KeyError, OSError, ValueError):
            return None
        descriptor_type = type(descriptor)
        if (
            module.__name__ != "datetime"
            or owner.__module__ != "datetime"
            or owner.__qualname__ != "datetime"
            or descriptor_type.__name__ != "classmethod_descriptor"
            or descriptor_type.__module__ != "builtins"
            or descriptor.__objclass__ is not owner
            or descriptor.__name__ != "now"
        ):
            return None
        return {
            "runtime_implementation": sys.implementation.name,
            "descriptor_owner_module": owner.__module__,
            "descriptor_owner_qualname": owner.__qualname__,
            "descriptor_member": descriptor.__name__,
            "descriptor_kind": descriptor_type.__name__,
            "stdlib_source_digest": source_digest,
        }

    def _call_binding(
        self, node: ast.Call, status: SourceResolution, targets: list[str], evidence_id: str
    ) -> RecordData | None:
        if node.func.end_lineno != node.func.lineno:
            return None
        native = self._native_call(node)
        if native is not None:
            target, origin, witness, proof = native
            return {
                "origin": origin,
                "target": target,
                "evidence_ids": sorted({evidence_id, *witness}),
                "proof": proof,
            }
        direct = self._direct_call_binding(node, status, targets, evidence_id)
        if direct is not None:
            return direct
        constructor = self._constructor_call_binding(node, evidence_id)
        if constructor is not None:
            return constructor
        return self._receiver_call_binding(node, targets, evidence_id)

    def _direct_call_binding(
        self, node: ast.Call, status: SourceResolution, targets: list[str], evidence_id: str
    ) -> RecordData | None:
        if (
            not isinstance(node.func, ast.Name)
            or status is not SourceResolution.RESOLVED
            or len(targets) != 1
        ):
            return None
        declaration = self.index.binding_declarations.get(targets[0])
        if declaration is None:
            return None
        data: dict[str, object] = declaration["data"]
        if (
            declaration["kind"] != "function"
            or data.get("source_binding_unique") is not True
            or data.get("source_binding_static") is not True
            or data.get("decorators")
        ):
            return None
        binding = self.scopes.lookup(node.func, node.func.id)
        if (
            binding.uncertain
            or binding.owner is None
            or (
                binding.owner is self.scopes.root
                and binding.kind is not BindingKind.UNBOUND
                and node.func.id not in self.stable_bindings
            )
        ):
            return None
        return {
            "origin": CallBindingOrigin.DIRECT,
            "target": targets[0],
            "evidence_ids": sorted({evidence_id, *self.symbol_evidence.get(targets[0], ())}),
        }

    def _constructor_call_binding(self, node: ast.Call, evidence_id: str) -> RecordData | None:
        if not isinstance(node.func, ast.Name | ast.Attribute):
            return None
        constructed = self._constructor_type(node)
        if constructed is None:
            return None
        target, evidence = constructed
        provider = self.provider_bindings.get(target)
        return {
            "origin": CallBindingOrigin.CONSTRUCTOR,
            "target": target,
            "evidence_ids": sorted({evidence_id, *evidence}),
            "proof": {
                "kind": "constructor",
                "target": target,
                "constructor_evidence_id": add_evidence(self.evidence, self.module, node),
                "provider_evidence_id": provider.evidence_id if provider is not None else None,
                "runtime_name": self.runtime.name if self.runtime is not None else "python",
                "runtime_version": self.runtime.version if self.runtime is not None else "unknown",
            },
        }

    def _receiver_call_binding(
        self, node: ast.Call, targets: list[str], evidence_id: str
    ) -> RecordData | None:
        if not isinstance(node.func, ast.Attribute):
            return None
        receiver = node.func.value
        if isinstance(receiver, ast.Attribute):
            stored = self._stored_receiver_call(node, receiver, targets, evidence_id)
            if stored is not None:
                return stored
        constructed = self._constructed_receiver_call(node, receiver, evidence_id)
        if constructed is not None:
            return constructed
        return self._declared_receiver_call(node, receiver, targets, evidence_id)

    def _stored_receiver_call(
        self, node: ast.Call, receiver: ast.Attribute, targets: list[str], evidence_id: str
    ) -> RecordData | None:
        stored = self._stored_type(receiver)
        if stored is None:
            return None
        if not isinstance(node.func, ast.Attribute):
            return None
        owner, evidence, proof = stored
        method = self._method_declaration(owner, node.func.attr)
        if method is None:
            return None
        target, declaration, inherited = method
        parent = _mapping_value(declaration["data"], "parent", "")
        owner_declaration = self.index.binding_declarations.get(
            parent if isinstance(parent, str) else ""
        )
        if target not in targets or owner_declaration is None:
            return None
        return self._receiver_binding_record(
            CallBindingOrigin.STORED_RECEIVER,
            target,
            evidence_id,
            [
                *evidence,
                *inherited,
                *declaration["evidence_ids"],
                *owner_declaration["evidence_ids"],
            ],
            proof,
        )

    def _constructed_receiver_call(
        self, node: ast.Call, receiver: ast.expr, evidence_id: str
    ) -> RecordData | None:
        if not isinstance(node.func, ast.Attribute):
            return None
        constructed = self._constructed_type(receiver, node)
        if constructed is None:
            return None
        owner, evidence, proof = constructed
        method = self._method_declaration(owner, node.func.attr)
        if method is None:
            return None
        target, declaration, inherited = method
        parent = _mapping_value(declaration["data"], "parent", "")
        owner_declaration = self.index.binding_declarations.get(
            parent if isinstance(parent, str) else ""
        )
        constructed_declaration = self.index.binding_declarations.get(owner)
        if (
            owner_declaration is None
            or constructed_declaration is None
            or _mapping_value(constructed_declaration["data"], "source_member_owner_static")
            is not True
            or _mapping_value(owner_declaration["data"], "source_member_owner_static") is not True
        ):
            return None
        return self._receiver_binding_record(
            CallBindingOrigin.CONSTRUCTED_RECEIVER,
            target,
            evidence_id,
            [
                *evidence,
                *inherited,
                *declaration["evidence_ids"],
                *owner_declaration["evidence_ids"],
            ],
            proof,
        )

    @staticmethod
    def _receiver_binding_record(
        origin: CallBindingOrigin,
        target: str,
        evidence_id: str,
        witnesses: list[str],
        proof: dict[str, object] | None,
    ) -> RecordData:
        record: RecordData = {
            "origin": origin,
            "target": target,
            "evidence_ids": sorted({evidence_id, *witnesses}),
        }
        if proof is not None:
            record["proof"] = proof
        return record

    def _declared_receiver_call(
        self, node: ast.Call, receiver: ast.expr, targets: list[str], evidence_id: str
    ) -> RecordData | None:
        if not isinstance(node.func, ast.Attribute):
            return None
        if not isinstance(receiver, ast.Name):
            return None
        binding = self.scopes.lookup(receiver, receiver.id)
        if (
            binding.owner is None
            or binding.uncertain
            or self._receiver_escaped(binding.owner, receiver.id)
        ):
            return None
        sites = binding.owner.bindings.get(receiver.id, ())
        if len(sites) != 1 or not isinstance(sites[0], ast.arg):
            return None
        annotation = sites[0].annotation
        if not isinstance(annotation, ast.Name | ast.Attribute):
            return None
        identity = self._annotation_identity(annotation)
        if identity is None:
            return None
        owner_name, import_evidence = identity
        target = f"{owner_name}.{node.func.attr}"
        owner = self.index.binding_declarations.get(owner_name)
        member = self.index.binding_declarations.get(target)
        if owner is None or member is None:
            return None
        if (
            owner["kind"] != "class"
            or _mapping_value(owner["data"], "source_binding_unique") is not True
            or _mapping_value(owner["data"], "source_member_binding_static") is not True
            or member["kind"] != "method"
            or _mapping_value(member["data"], "parent") != owner_name
            or _mapping_value(member["data"], "decorators")
            or target not in targets
        ):
            return None
        annotation_evidence = add_evidence(self.evidence, self.module, annotation)
        return self._receiver_binding_record(
            CallBindingOrigin.DECLARED_RECEIVER,
            target,
            evidence_id,
            [
                annotation_evidence,
                *import_evidence,
                *owner["evidence_ids"],
                *member["evidence_ids"],
            ],
            None,
        )

    def _call_arguments(self, node: ast.Call) -> list[RecordData]:
        arguments: list[RecordData] = []
        for argument in node.args:
            value = argument.value if isinstance(argument, ast.Starred) else argument
            arguments.append(
                {
                    "kind": "starred_positional"
                    if isinstance(argument, ast.Starred)
                    else "positional",
                    "keyword": None,
                    "value_kind": "string_literal"
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    else "other",
                    "value": value.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    else None,
                    "evidence_ids": [add_evidence(self.evidence, self.module, argument)],
                }
            )
        for keyword in node.keywords:
            arguments.append(
                {
                    "kind": "keyword" if keyword.arg is not None else "starred_keyword",
                    "keyword": keyword.arg,
                    "value_kind": "string_literal"
                    if isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                    else "other",
                    "value": keyword.value.value
                    if isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                    else None,
                    "evidence_ids": [add_evidence(self.evidence, self.module, keyword)],
                }
            )
        return arguments

    def visit_Call(self, node: ast.Call) -> None:
        scope = self.scopes.by_node[node]
        receivers = {
            name: receiver
            for name in {child.id for child in ast.walk(node.func) if isinstance(child, ast.Name)}
            if (receiver := self._receiver(node.func, name)) is not None
        }
        expression = annotation_text(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = resolve_name(
            node.func,
            index=self.index,
            scopes=self.scopes,
            receiver_types=receivers,
        )
        evidence_id = add_evidence(self.evidence, self.module, node)
        item_id = call_id(self.module, node, expression)
        binding = self._call_binding(node, status, targets, evidence_id)
        if binding is not None:
            canonical_target = binding["target"]
            targets = [canonical_target] if isinstance(canonical_target, str) else targets
            candidate_count = len(targets)
            status = SourceResolution.RESOLVED
            reason = "source-proven call identity"
        target_evidence_ids = sorted(
            {
                evidence_id
                for target in targets
                for evidence_id in self.symbol_evidence.get(target, [])
            }
        )
        source_line = self.module.lines[node.lineno - 1]
        self.items.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind=f"{status}_call",
                title=f"Call {expression}",
                subjects=[scope.qualified_name, *targets],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": scope.qualified_name,
                    "source_definition_id": scope.definition_id
                    if scope is self.scopes.root or scope.definition_id in self.index.definition_ids
                    else None,
                    "source_module": self.module.module,
                    "expression": expression,
                    "status": status,
                    "targets": targets,
                    "candidate_count": candidate_count,
                    "candidates_truncated": candidate_count > len(targets),
                    "reason": reason,
                    "target_evidence_ids": target_evidence_ids,
                    "call_arguments": (
                        self._call_arguments(node)
                        if binding is not None
                        and node.end_lineno == node.lineno
                        and call_excerpt_matches(
                            expression,
                            source_line,
                            node.lineno,
                            node.col_offset,
                            node.end_lineno,
                        )
                        else None
                    ),
                    "result_bindings": self._result_bindings(node, item_id),
                    "construction": self._construction(
                        node, expression, status, targets, candidate_count > len(targets)
                    ),
                    "call_binding": binding,
                },
            )
        )
        self.generic_visit(node)


def collect_calls(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
    provider_bindings: Sequence[ProviderBinding] = (),
    runtime: RuntimeInfo | None = None,
    imports: Sequence[RawRecord] = (),
) -> list[RawRecord]:
    """Run the call collector over every module and sort the records by id."""
    calls, _ = collect_calls_with_resolvers(
        parsed, index, evidence, provider_bindings, runtime, imports
    )
    return calls


def collect_calls_with_resolvers(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
    provider_bindings: Sequence[ProviderBinding] = (),
    runtime: RuntimeInfo | None = None,
    imports: Sequence[RawRecord] = (),
) -> tuple[list[RawRecord], tuple[CallCollector, ...]]:
    """Collect calls and retain their per-module resolver for construct evidence."""
    calls: list[RawRecord] = []
    resolvers: list[CallCollector] = []
    for module in parsed:
        call_collector = CallCollector(module, index, evidence, provider_bindings, runtime, imports)
        call_collector.visit(module.tree)
        calls.extend(call_collector.items)
        resolvers.append(call_collector)
    calls.sort(key=lambda item: item["id"])
    return calls, tuple(resolvers)
