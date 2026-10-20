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
from collections.abc import Sequence

from archkeel.ir.facts import EvidenceClass, SourceResolution, in_scope, stable_id
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified

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
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        end_line = getattr(node, "end_lineno", line) or line
        end_column = getattr(node, "end_col_offset", column + 1) or column + 1
        scope = self.scopes.by_node[node]
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
        attributes = (
            class_declaration["data"].get("attribute_declarations", ()) if class_declaration else ()
        )
        for attribute in attributes:
            if attribute.get("name") == member and isinstance(attribute.get("definition_id"), str):
                return attribute["definition_id"]
        return stable_id("DECL", self.module.rel_path, name) if local else stable_id("DECL", name)

    def _expression(self, node: ast.expr) -> dict[str, object]:
        if isinstance(node, ast.Constant) and isinstance(
            node.value, (str, int, float, bool, type(None))
        ):
            return {"expression_kind": "literal", "constant": node.value, "status": "resolved"}
        if isinstance(node, ast.Name | ast.Attribute):
            status, targets, _, _ = resolve_name(
                node, index=self.index, scopes=self.scopes, value_reference=True
            )
            return {
                "expression_kind": "reference",
                "status": status,
                "targets": sorted(targets),
                "expression": annotation_text(node) or ast.unparse(node),
            }
        return {"expression_kind": "unsupported", "status": "partially_resolved"}

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
        self._source_role(
            node,
            "definition",
            owner,
            definition_id(self.module, node, owner),
        )
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
        owner_scope = self.scopes.by_node[node]
        name = f"{owner_scope.qualified_name}.{node.name}"
        self._source_role(node, "definition", name, definition_id(self.module, node, name))
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
            self._source_role(node, role, name, declaration_id, status=status)
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
            direct_name = isinstance(value, ast.Name)
            direct_lambda = (
                isinstance(value, ast.Lambda)
                and isinstance(value.body, ast.Call)
                and not value.body.args
                and not value.body.keywords
            )
            if not direct_name and not direct_lambda:
                candidates: set[str] = set()
                for child in ast.walk(value):
                    if not isinstance(child, ast.Name | ast.Attribute):
                        continue
                    status, targets, _, _ = resolve_name(
                        child, index=self.index, scopes=self.scopes, value_reference=True
                    )
                    if status != SourceResolution.UNRESOLVED:
                        candidates.update(targets)
                for target in sorted(candidates):
                    self._source_role(
                        value,
                        "value_transfer",
                        target,
                        self._binding_declaration_id(target),
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
                local_sites
                and len(local_sites) == len(sites)
                and not any(
                    control_flow_contexts(site, self.scopes.parents) for site in local_sites
                )
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
                    direct_stores
                    and len(direct_stores) == len(sites)
                    and not any(
                        control_flow_contexts(site, self.scopes.parents) for site in direct_stores
                    )
                ):
                    local_source_binding = True
                    internal = [local_name]
        if (status == SourceResolution.UNRESOLVED or not internal) and not local_source_binding:
            return
        if local_source_binding and status == SourceResolution.UNRESOLVED:
            status = SourceResolution.PARTIALLY_RESOLVED
        evidence_id = add_evidence(self.evidence, self.module, node)
        line, _, column = location(node)
        text = annotation_text(node) or expression
        declaration = self._annotation_declaration(node)
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

    def _annotation_declaration(self, node: ast.AST) -> dict[str, str]:
        annotated_argument = False
        current = node
        while current in self.scopes.parents:
            parent = self.scopes.parents[current]
            if isinstance(parent, ast.arg):
                annotated_argument = parent.annotation is current
            if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
                if parent.returns is current or (annotated_argument and parent.args is current):
                    scope = self.scopes.by_node[parent]
                    name = f"{scope.qualified_name}.{parent.name}"
                    return {
                        "declaration_scope": name,
                        "declaration_definition_id": definition_id(self.module, parent, name),
                    }
                return {}
            if isinstance(parent, ast.ClassDef | ast.Lambda):
                return {}
            current = parent
        return {}

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
    pending = list(node.body)
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
        references.extend(collector.items)
    references.sort(key=lambda item: item["id"])
    return references
