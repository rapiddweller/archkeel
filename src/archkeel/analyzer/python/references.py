# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record uses of a scanned symbol that are not calls (AD-26).

A function handed to a dictionary, passed as an argument or read as a property is used,
but no call site names it. Without this signal a call graph reports such a symbol as
unreferenced, which was wrong for every candidate it produced on Archkeel itself.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Sequence

from archkeel.ir.facts import (
    EvidenceClass,
    SourceReferenceContext,
    SourceResolution,
    in_scope,
    stable_id,
)
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified, source_reference_context

from .resolve import SymbolIndex, dotted_expression, resolve_name
from .scopes import LexicalScopes
from .source import (
    ParsedModule,
    add_evidence,
    annotation_text,
    control_flow_contexts,
    definition_id,
    location,
    unique_direct_module_bindings,
)


def _end_location(node: ast.AST, line: int, column: int) -> tuple[int, int]:
    if isinstance(node, ast.expr | ast.stmt | ast.arg):
        return node.end_lineno or line, node.end_col_offset or column + 1
    return line, column + 1


def _enum_member_classes(
    parsed: Sequence[ParsedModule], index: SymbolIndex, roots: dict[str, frozenset[str]]
) -> frozenset[str]:
    eligible: set[str] = {
        f"{module.module}.{name}"
        for module in parsed
        for name in roots[module.module]
        if f"{module.module}.{name}" in index.enum_members
    }
    for module in parsed:
        wildcard = any(
            isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(module.tree)
        )
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Store | ast.Del):
                continue
            if wildcard:
                return frozenset()
            dotted = dotted_expression(node)
            if dotted is None:
                continue
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if not isinstance(root, ast.Name):
                continue
            binding = module.aliases.get(root.id)
            if binding is not None:
                if root.id not in roots[module.module]:
                    # An ambiguous writer may refer to any of its competing imported targets.
                    return frozenset()
                written = binding.target + dotted[len(root.id) :]
            elif f"{module.module}.{root.id}" in index.enum_members:
                written = f"{module.module}.{dotted}"
            else:
                continue
            eligible.difference_update(
                [name for name in eligible if in_scope(name, written) or in_scope(written, name)]
            )
    return frozenset(eligible)


class ReferenceCollector(ast.NodeVisitor):
    """Walk one module and record every non-call use of an indexed symbol."""

    def __init__(
        self,
        module: ParsedModule,
        index: SymbolIndex,
        evidence: dict[str, RawEvidence],
        enum_member_roots: frozenset[str],
        enum_member_classes: frozenset[str],
    ) -> None:
        self.module = module
        self.index = index
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scopes = LexicalScopes.for_module(module)
        self.enum_member_roots = enum_member_roots
        self.enum_member_classes = enum_member_classes
        self.attribute_definitions: set[str] = set()

    def _source_role(
        self,
        node: ast.AST,
        role: str,
        canonical_name: str,
        declaration_id: str,
        **details: object,
    ) -> None:
        status = details.get("status", SourceResolution.RESOLVED)
        if role in {"read", "value_transfer"} and canonical_name.startswith("builtins."):
            status = SourceResolution.PARTIALLY_RESOLVED
            details["status"] = status
        if status != SourceResolution.RESOLVED:
            details["targets"] = []
            if role in {"read", "write", "delete", "value_transfer"}:
                declaration_id = stable_id("DECL", canonical_name)
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        end_line, end_column = _end_location(node, line, column)
        scope = self.scopes.by_node[node]
        declaration_owner = scope
        while declaration_owner.parent is not None and declaration_owner.definition_id is None:
            declaration_owner = declaration_owner.parent
        self.items.append(
            classified(
                item_id=stable_id(
                    "SOURCE-ROLE",
                    self.module.rel_path,
                    line,
                    column,
                    end_line,
                    end_column,
                    role,
                    canonical_name,
                ),
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind="source_role",
                title=f"{role} of {canonical_name}",
                subjects=[scope.qualified_name, canonical_name],
                evidence_ids=[evidence_id],
                data={
                    "role": role,
                    "canonical_name": canonical_name,
                    "expression": canonical_name,
                    "status": details.get("status", SourceResolution.RESOLVED),
                    "targets": [canonical_name],
                    "use": "source_role",
                    "declaration_id": declaration_id,
                    "source_scope": scope.qualified_name,
                    "source_module": self.module.module,
                    **(
                        {
                            "declaration_owner_scope": declaration_owner.qualified_name,
                            "declaration_owner_id": declaration_owner.definition_id,
                        }
                        if isinstance(declaration_owner.definition_id, str)
                        else {"declaration_owner_scope": declaration_owner.qualified_name}
                    ),
                    "line": line,
                    "column": column,
                    "end_line": end_line,
                    "end_column": end_column,
                    **details,
                },
            )
        )

    def _canonical_name(self, node: ast.Name) -> tuple[str, str, str]:
        binding = self.scopes.lookup(node, node.id)
        status, targets, _, _ = resolve_name(
            node, index=self.index, scopes=self.scopes, value_reference=True
        )
        if status == SourceResolution.RESOLVED and len(targets) == 1:
            name = targets[0]
            return name, self._binding_declaration_id(name), status
        owner = binding.owner or self.scopes.by_node[node]
        name = f"{owner.qualified_name}.{node.id}"
        sites = owner.bindings.get(node.id, ())
        direct_stores = [
            site
            for site in sites
            if isinstance(site, ast.Name) and isinstance(site.ctx, ast.Store | ast.Del)
        ]
        if (
            direct_stores
            and len(direct_stores) == len(sites)
            and not any(control_flow_contexts(site, self.scopes.parents) for site in direct_stores)
        ):
            status = SourceResolution.RESOLVED
        return name, stable_id("DECL", self.module.rel_path, name), status

    def _declaration_name(self, node: ast.Name) -> tuple[str, str]:
        """Return the lexical binding declared here, independent of its assigned value."""
        binding = self.scopes.lookup(node, node.id)
        owner = binding.owner or self.scopes.by_node[node]
        name = f"{owner.qualified_name}.{node.id}"
        return name, self._binding_declaration_id(name, local=True)

    def _binding_declaration_id(self, name: str, *, local: bool = False) -> str:
        declaration = self.index.binding_declarations.get(name)
        if declaration is not None:
            return declaration["id"]
        symbol_id = self.index.symbol_ids.get(name)
        if symbol_id is not None:
            return symbol_id
        owner, _, member = name.rpartition(".")
        class_declaration = self.index.binding_declarations.get(owner)
        class_data = class_declaration["data"] if class_declaration is not None else {}
        class_kind = class_data["kind"] if "kind" in class_data else None
        if class_declaration is not None and class_kind != "class":
            class_declaration = None
        attributes = (
            class_declaration["data"]["attribute_declarations"]
            if class_declaration is not None
            and "attribute_declarations" in class_declaration["data"]
            else ()
        )
        for attribute in attributes:
            definition_id = attribute["definition_id"] if "definition_id" in attribute else None
            attribute_name = attribute["name"] if "name" in attribute else None
            if attribute_name == member and isinstance(definition_id, str):
                return definition_id
        return stable_id("DECL", self.module.rel_path, name) if local else stable_id("DECL", name)

    def _has_canonical_declaration(self, name: str, declaration_id: str) -> bool:
        if self.index.symbol_ids.get(name) == declaration_id:
            return True
        owner, _, member = name.rpartition(".")
        class_declaration = self.index.binding_declarations.get(owner)
        class_data = class_declaration["data"] if class_declaration is not None else {}
        class_kind = class_data["kind"] if "kind" in class_data else None
        if class_declaration is not None and class_kind != "class":
            class_declaration = None
        attributes = (
            class_declaration["data"]["attribute_declarations"]
            if class_declaration is not None
            and "attribute_declarations" in class_declaration["data"]
            else ()
        )
        for attribute in attributes:
            attribute_name = attribute["name"] if "name" in attribute else None
            definition_id = attribute["definition_id"] if "definition_id" in attribute else None
            if attribute_name == member and definition_id == declaration_id:
                return True
        return False

    def _expression(self, node: ast.expr) -> dict[str, object]:
        if isinstance(node, ast.Constant) and isinstance(
            node.value, (str, int, float, bool, type(None))
        ):
            return {
                "expression_kind": "literal",
                "constant": node.value,
                "status": "resolved",
                "targets": [],
            }
        if isinstance(node, ast.Name | ast.Attribute):
            status, targets, _, _ = resolve_name(
                node, index=self.index, scopes=self.scopes, value_reference=True
            )
            if status == SourceResolution.RESOLVED and len(targets) == 1:
                target = targets[0]
                if target not in self.index.names and target not in self.index.declaration_names:
                    status = SourceResolution.PARTIALLY_RESOLVED
                    targets = []
            line, _, column = location(node)
            excerpt = self.module.lines[line - 1] if line <= len(self.module.lines) else ""
            context = source_reference_context(excerpt, column, ast.unparse(node))
            if status == SourceResolution.RESOLVED and context is not SourceReferenceContext.VALUE:
                return {
                    "expression_kind": "reference",
                    "status": SourceResolution.PARTIALLY_RESOLVED,
                    "targets": [],
                    "expression": ast.unparse(node),
                }
            return {
                "expression_kind": "reference",
                "status": status,
                "targets": sorted(targets),
                "expression": annotation_text(node) or ast.unparse(node),
            }
        return {"expression_kind": "unsupported", "status": "partially_resolved", "targets": []}

    def _parameter_default(
        self,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        argument: ast.arg,
        expression: ast.expr,
    ) -> None:
        parent_scope = self.scopes.by_node[function]
        owner = f"{parent_scope.qualified_name}.{function.name}"
        parameter = f"{owner}.{argument.arg}"
        declaration_id = definition_id(self.module, function, owner)
        function_line, _, _ = location(function)
        expression_line, expression_end, _ = location(expression)
        if expression_line != function_line or expression_end != expression_line:
            self._source_role(
                expression,
                "parameter_default",
                parameter,
                declaration_id,
                parameter=parameter,
                expression_kind="unsupported",
                status=SourceResolution.PARTIALLY_RESOLVED,
                targets=[],
                expression=ast.unparse(expression),
            )
            return
        self._source_role(
            expression,
            "parameter_default",
            parameter,
            declaration_id,
            parameter=parameter,
            **self._expression(expression),
        )

    def _function_source_roles(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent_scope = self.scopes.by_node[node]
        owner = f"{parent_scope.qualified_name}.{node.name}"
        positional = [*node.args.posonlyargs, *node.args.args]
        defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        for argument, default in zip(positional, defaults, strict=True):
            if default is not None:
                self._parameter_default(node, argument, default)
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
            if default is not None:
                self._parameter_default(node, argument, default)
        parameters = {argument.arg for argument in (*positional, *node.args.kwonlyargs)}
        for expression in _function_expressions(node):
            if not isinstance(expression, ast.BoolOp) or not isinstance(expression.op, ast.Or):
                continue
            left = expression.values[0] if expression.values else None
            if not isinstance(left, ast.Name) or left.id not in parameters:
                continue
            parameter = f"{owner}.{left.id}"
            self._source_role(
                expression,
                "fallback",
                parameter,
                definition_id(self.module, node, owner),
                parameter=parameter,
                **(
                    self._expression(expression.values[1])
                    if len(expression.values) == 2
                    else {"expression_kind": "unsupported", "status": "partially_resolved"}
                ),
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_source_roles(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_source_roles(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record(node, node.id, "value")
        elif isinstance(node.ctx, ast.Del):
            name, declaration_id = self._declaration_name(node)
            _, _, status = self._canonical_name(node)
            self._source_role(node, "delete", name, declaration_id, status=status)
        elif isinstance(node.ctx, ast.Store):
            name, declaration_id = self._declaration_name(node)
            _, _, status = self._canonical_name(node)
            binding = self.scopes.lookup(node, node.id)
            sites = binding.owner.bindings.get(node.id, ()) if binding.owner is not None else ()
            stores = sorted(
                (
                    site
                    for site in sites
                    if isinstance(site, ast.Name) and isinstance(site.ctx, ast.Store)
                ),
                key=lambda site: (location(site)[0], location(site)[2]),
            )
            role = "definition" if stores and stores[0] is node else "write"
            if role != "definition" or not self._has_canonical_declaration(name, declaration_id):
                self._source_role(
                    node,
                    role,
                    name,
                    declaration_id,
                    status=(
                        SourceResolution.PARTIALLY_RESOLVED if role == "definition" else status
                    ),
                )
        parent = self.scopes.parents.get(node)
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(parent, ast.Dict)
            and node in parent.values
        ):
            name, declaration_id, status = self._canonical_name(node)
            self._source_role(
                node,
                "value_transfer",
                name,
                declaration_id,
                status=status,
                transfer_kind="dictionary_value",
            )

    def visit_Lambda(self, node: ast.Lambda) -> None:
        parent = self.scopes.parents.get(node)
        if (
            isinstance(parent, ast.Dict)
            and node in parent.values
            and isinstance(node.body, ast.Call)
        ):
            status, targets, _, _ = resolve_name(
                node.body.func, index=self.index, scopes=self.scopes, value_reference=True
            )
            if (
                status == SourceResolution.RESOLVED
                and not node.body.args
                and not node.body.keywords
                and len(targets) == 1
            ):
                target = targets[0]
                self._source_role(
                    node.body,
                    "value_transfer",
                    target,
                    self._binding_declaration_id(target),
                    status=status,
                    transfer_kind="dictionary_lambda_call",
                )
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for value in node.values:
            if (
                isinstance(value, ast.Name | ast.Lambda)
                or not isinstance(value, ast.Call)
                or len(value.args) != 1
                or value.keywords
                or not isinstance(value.args[0], ast.Name)
            ):
                continue
            candidates: set[str] = set()
            child = value.args[0]
            status, targets, _, _ = resolve_name(
                child, index=self.index, scopes=self.scopes, value_reference=True
            )
            if status != SourceResolution.RESOLVED:
                continue
            for target in targets:
                alias = self.module.aliases.get(child.id)
                target_name: str = target
                if (alias is not None and alias.target == target_name) or target_name.rpartition(
                    "."
                )[2] == child.id:
                    candidates.add(target)
            for target in sorted(candidates):
                self._source_role(
                    value,
                    "value_transfer",
                    target,
                    stable_id("DECL", target),
                    status=SourceResolution.PARTIALLY_RESOLVED,
                    expression_kind="unsupported",
                    transfer_kind="unsupported_dictionary_value",
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Store | ast.Del):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            scope = self.scopes.by_node[node]
            if (
                isinstance(root, ast.Name)
                and root.id == "self"
                and isinstance(scope.node, ast.FunctionDef | ast.AsyncFunctionDef)
                and scope.parent is not None
                and isinstance(scope.parent.node, ast.ClassDef)
            ):
                name = f"{scope.parent.qualified_name}.{node.attr}"
                status = SourceResolution.RESOLVED
            else:
                status, targets, _, _ = resolve_name(
                    node, index=self.index, scopes=self.scopes, value_reference=True
                )
                status = SourceResolution.PARTIALLY_RESOLVED
                name = (
                    targets[0]
                    if status == SourceResolution.RESOLVED and len(targets) == 1
                    else f"{scope.qualified_name}.{node.attr}"
                )
            role = "delete" if isinstance(node.ctx, ast.Del) else "write"
            if (
                role == "write"
                and isinstance(root, ast.Name)
                and root.id == "self"
                and isinstance(scope.node, ast.FunctionDef | ast.AsyncFunctionDef)
                and scope.parent is not None
                and isinstance(scope.parent.node, ast.ClassDef)
                and name not in self.attribute_definitions
            ):
                role = "definition"
                self.attribute_definitions.add(name)
            self._source_role(
                node, role, name, stable_id("DECL", self.module.rel_path, name), status=status
            )
            return
        dotted = dotted_expression(node) if isinstance(node.ctx, ast.Load) else None
        if dotted is None:
            self.generic_visit(node)
            return
        self._record(node, dotted, "attribute")

    def _record(self, node: ast.expr, expression: str, use: str) -> None:
        scope = self.scopes.by_node[node]
        enum_member = self._enum_member_class(node)
        if enum_member is None:
            status, targets, _, _ = resolve_name(
                node, index=self.index, scopes=self.scopes, value_reference=True
            )
        else:
            status, targets = SourceResolution.RESOLVED, [enum_member]
        local_source_binding, local_name, status, internal = self._local_reference_target(
            node, targets, status
        )
        if (status == SourceResolution.UNRESOLVED or not internal) and not local_source_binding:
            return
        if local_source_binding and status == SourceResolution.UNRESOLVED:
            status = SourceResolution.PARTIALLY_RESOLVED
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        text = annotation_text(node) or expression
        declaration = self._annotation_declaration(node)
        source_context = source_reference_context(
            self.evidence[evidence_id]["excerpt"], column, text
        )
        if source_context is None or (
            declaration.get("reference_context") == SourceReferenceContext.ANNOTATION
            and source_context is not SourceReferenceContext.ANNOTATION
        ):
            context = SourceReferenceContext.UNKNOWN
            declaration = {}
        else:
            context = source_context
        self.items.append(
            classified(
                item_id=stable_id("REF", self.module.rel_path, line, column, text),
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind=f"{use}_reference",
                title=f"Reference {text}",
                subjects=[scope.qualified_name, *internal],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": scope.qualified_name,
                    "source_definition_id": scope.definition_id
                    if scope is self.scopes.root or scope.definition_id in self.index.definition_ids
                    else None,
                    "source_module": self.module.module,
                    "expression": text,
                    "status": status,
                    "targets": sorted(internal),
                    "use": use,
                    "reference_context": context,
                    **(
                        {
                            "declaration_id": self._binding_declaration_id(local_name, local=True),
                            "local_source_binding": True,
                        }
                        if local_source_binding and local_name is not None
                        else {}
                    ),
                    **declaration,
                },
            )
        )

    def _local_reference_target(
        self,
        node: ast.expr,
        targets: list[str],
        status: SourceResolution,
    ) -> tuple[bool, str | None, SourceResolution, list[str]]:
        local_source_binding = False
        local_name: str | None = None
        if isinstance(node, ast.Name):
            binding = self.scopes.lookup(node, node.id)
            sites = binding.owner.bindings.get(node.id, ()) if binding.owner is not None else ()
            local_sites = [
                site
                for site in sites
                if isinstance(site, ast.Name) and isinstance(site.ctx, ast.Store | ast.Del)
            ]
            local_name = (
                f"{binding.owner.qualified_name}.{node.id}" if binding.owner is not None else None
            )
            if (
                binding.owner is not self.scopes.root
                and local_sites
                and len(local_sites) == len(sites)
                and not any(
                    control_flow_contexts(site, self.scopes.parents) for site in local_sites
                )
                and local_name is not None
                and (not targets or set(targets) == {local_name})
            ):
                local_source_binding = True
                targets = [local_name]
        internal = [
            target
            for target in targets
            if target in self.index.names or target in self.index.declaration_names
        ]
        if not internal and isinstance(node, ast.Name):
            binding = self.scopes.lookup(node, node.id)
            if binding.owner is not None and binding.owner.bindings.get(node.id):
                local_name = f"{binding.owner.qualified_name}.{node.id}"
                sites = binding.owner.bindings.get(node.id, ())
                direct_stores = [
                    site
                    for site in sites
                    if isinstance(site, ast.Name) and isinstance(site.ctx, ast.Store | ast.Del)
                ]
                if (
                    binding.owner is not self.scopes.root
                    and direct_stores
                    and len(direct_stores) == len(sites)
                    and not any(
                        control_flow_contexts(site, self.scopes.parents) for site in direct_stores
                    )
                ):
                    local_source_binding = True
                    internal = [local_name]
        return local_source_binding, local_name, status, internal

    def _annotation_declaration(self, node: ast.AST) -> dict[str, str]:
        current = node
        annotation = False
        while current in self.scopes.parents:
            parent = self.scopes.parents[current]
            if isinstance(parent, ast.arg) and parent.annotation is current:
                annotation = True
            if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef) and (
                parent.args is current or parent.returns is current
            ):
                if parent.args is current and not annotation:
                    return {}
                annotation |= parent.returns is current
                return self._operation_reference_context(parent, annotation)
            if isinstance(parent, ast.AnnAssign) and parent.annotation is current:
                return self._scoped_annotation(parent)
            if (
                sys.version_info >= (3, 12)
                and isinstance(parent, ast.TypeAlias)
                and parent.value is current
            ):
                return self._scoped_annotation(parent)
            if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                return {}
            current = parent
        return {}

    def _operation_reference_context(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef, annotation: bool
    ) -> dict[str, str]:
        scope = self.scopes.by_node[function]
        name = f"{scope.qualified_name}.{function.name}"
        return {
            "reference_context": "annotation" if annotation else "value",
            "declaration_scope": name,
            "declaration_definition_id": definition_id(self.module, function, name),
        }

    def _scoped_annotation(self, node: ast.AST) -> dict[str, str]:
        del node
        return {"reference_context": "annotation"}

    def _enum_member_class(self, node: ast.expr) -> str | None:
        """Resolve only a member listed on one statically bound enum class."""
        if not isinstance(node, ast.Attribute):
            return None
        root = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name) or root.id not in self.enum_member_roots:
            return None
        status, targets, _, _ = resolve_name(node.value, index=self.index, scopes=self.scopes)
        if status != SourceResolution.RESOLVED or len(targets) != 1:
            return None
        enum_name = targets[0]
        if enum_name not in self.enum_member_classes:
            return None
        members = self.index.enum_members.get(enum_name)
        return enum_name if members is not None and node.attr in members else None


def _function_expressions(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ast.AST, ...]:
    pending: list[ast.AST] = list(node.body)
    expressions: list[ast.AST] = []
    while pending:
        current = pending.pop()
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        expressions.append(current)
        pending.extend(ast.iter_child_nodes(current))
    return tuple(expressions)


def collect_references(
    parsed: Sequence[ParsedModule],
    index: SymbolIndex,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    """Run the reference collector over every module and sort the records by id."""
    references: list[RawRecord] = []
    roots = {module.module: unique_direct_module_bindings(module) for module in parsed}
    enum_classes = _enum_member_classes(parsed, index, roots)
    for module in parsed:
        collector = ReferenceCollector(module, index, evidence, roots[module.module], enum_classes)
        collector.visit(module.tree)
        references.extend(_reuse_local_definition_references(collector.items))
    references.sort(key=lambda item: item["id"])
    return references


def _source_role_definition_key(item: RawRecord) -> tuple[str, str] | None:
    data = item["data"]
    if item["kind"] != "source_role" or "role" not in data or data["role"] != "definition":
        return None
    canonical_name = data["canonical_name"] if "canonical_name" in data else None
    declaration_id = data["declaration_id"] if "declaration_id" in data else None
    if isinstance(canonical_name, str) and isinstance(declaration_id, str):
        return canonical_name, declaration_id
    return None


def _reuse_local_definition_references(items: list[RawRecord]) -> list[RawRecord]:
    """Link one exact local read to its declaration instead of duplicating a role record."""
    definitions = {
        key: item for item in items if (key := _source_role_definition_key(item)) is not None
    }
    linked: set[tuple[str, str]] = set()
    for item in items:
        data = item["data"]
        if item["kind"] not in {"value_reference", "attribute_reference"}:
            continue
        targets = data["targets"] if "targets" in data else ()
        target = targets[0] if isinstance(targets, list) and len(targets) == 1 else None
        declaration_id = data["declaration_id"] if "declaration_id" in data else None
        if not isinstance(target, str) or not isinstance(declaration_id, str):
            continue
        key = (target, declaration_id)
        definition = definitions.get(key)
        if (
            definition is None
            or key in linked
            or "local_source_binding" not in data
            or data["local_source_binding"] is not True
        ):
            continue
        data["declaration_role"] = "definition"
        data["declaration_evidence_ids"] = list(definition["evidence_ids"])
        definition_data = definition["data"]
        data["declaration_status"] = (
            definition_data["status"] if "status" in definition_data else None
        )
        owner_scope = (
            definition_data["declaration_owner_scope"]
            if "declaration_owner_scope" in definition_data
            else (definition_data["source_scope"] if "source_scope" in definition_data else None)
        )
        data["declaration_owner_scope"] = owner_scope
        owner_id = (
            definition_data["declaration_owner_id"]
            if "declaration_owner_id" in definition_data
            else None
        )
        if isinstance(owner_id, str):
            data["declaration_owner_id"] = owner_id
        linked.add(key)
    return [item for item in items if _source_role_definition_key(item) not in linked]
