# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compiler lexical scopes and the source sites that bind their names."""

from __future__ import annotations

import ast
import symtable
import sys
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from archkeel.ir.facts import stable_id

from .source import DefinitionNode, ParsedModule, control_flow_contexts, definition_id, location

BindingKind: TypeAlias = Literal[
    "unknown", "local", "unbound", "declaration", "module", "symbol", "mixed"
]


@dataclass(slots=True)
class Scope:
    node: ast.AST
    table: symtable.SymbolTable | None
    qualified_name: str
    definition_id: str | None
    parent: Scope | None = None
    bindings: dict[str, list[ast.AST]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NameBinding:
    owner: Scope | None
    targets: tuple[str, ...] = ()
    kind: BindingKind = "unknown"
    uncertain: bool = False


class LexicalScopes(ast.NodeVisitor):
    """Share compiler name ownership between call and reference resolution.

    A missing or ambiguous compiler table cannot authorize a module fallback.
    This index is transient; collectors still publish the existing Source IR records.
    """

    def __init__(self, module: ParsedModule) -> None:
        self.module = module
        try:
            table = symtable.symtable(module.source, module.rel_path, "exec")
        except SyntaxError:
            table = None
        self.current = Scope(module.tree, table, module.module, stable_id("MOD", module.module))
        self.root = self.current
        self.parents = {
            child: parent
            for parent in ast.walk(module.tree)
            for child in ast.iter_child_nodes(parent)
        }
        self.by_node: dict[ast.AST, Scope] = {}
        self.visit(module.tree)

    def visit(self, node: ast.AST) -> None:
        self.by_node[node] = self.current
        super().visit(node)

    def _owner(self, scope: Scope, name: str) -> Scope | None:
        if scope.table is None:
            return None
        try:
            symbol = scope.table.lookup(name)
        except KeyError:
            return self.root
        if scope is self.root or symbol.is_local():
            return scope
        if symbol.is_global():
            return self.root
        parent = scope.parent
        while parent is not None:
            if parent.table is None:
                return None
            if parent.table.get_type() == "function":
                try:
                    binding = parent.table.lookup(name)
                except KeyError:
                    pass
                else:
                    if binding.is_local():
                        return parent
            parent = parent.parent
        return self.root

    def _bind(self, name: str, node: ast.AST) -> None:
        owner = self._owner(self.current, name)
        if owner is not None:
            owner.bindings.setdefault(name, []).append(node)

    def _enter(self, node: ast.AST, name: str, qualified_name: str, identity: str | None) -> Scope:
        parent = self.current
        matches = (
            []
            if parent.table is None
            else [
                table
                for table in parent.table.get_children()
                if table.get_name() == name and table.get_lineno() == location(node)[0]
            ]
        )
        self.current = Scope(
            node, matches[0] if len(matches) == 1 else None, qualified_name, identity, parent
        )
        return parent

    def _definition(self, node: DefinitionNode) -> None:
        self._bind(node.name, node)
        for child in ast.iter_child_nodes(node):
            if child not in node.body:
                self.visit(child)
        qualified = f"{self.current.qualified_name}.{node.name}"
        parent = self._enter(
            node, node.name, qualified, definition_id(self.module, node, qualified)
        )
        # Generic parameter and annotation scopes differ by interpreter version.
        if sys.version_info >= (3, 12) and node.type_params:
            self.current.table = None
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            self._parameters(node.args)
        for statement in node.body:
            self.visit(statement)
        self.current = parent

    def _parameters(self, args: ast.arguments) -> None:
        for argument in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            self._bind(argument.arg, argument)
        for variadic in (args.vararg, args.kwarg):
            if variadic is not None:
                self._bind(variadic.arg, variadic)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._definition(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._definition(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._definition(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        line, _, column = location(node)
        parent = self._enter(
            node, "lambda", f"{self.current.qualified_name}.<lambda:{line}:{column}>", None
        )
        self._parameters(node.args)
        self.visit(node.body)
        self.current = parent

    def _comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp, name: str
    ) -> None:
        self.visit(node.generators[0].iter)
        line, _, column = location(node)
        parent = self._enter(
            node, name, f"{self.current.qualified_name}.<{name}:{line}:{column}>", None
        )
        for position, generator in enumerate(node.generators):
            self.visit(generator.target)
            if position:
                self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        expressions = (node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)
        for expression in expressions:
            self.visit(expression)
        self.current = parent

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node, "listcomp")

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._comprehension(node, "setcomp")

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node, "dictcomp")

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._comprehension(node, "genexpr")

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store | ast.Del):
            self._bind(node.id, node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._bind(alias.asname or alias.name.split(".")[0], node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._bind(alias.asname or alias.name, node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, node)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name, node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest, node)
        self.generic_visit(node)

    def lookup(self, node: ast.AST, name: str) -> NameBinding:
        owner = self._owner(self.by_node[node], name)
        if owner is None:
            return NameBinding(None)
        return self._binding(owner, node, name)

    def _binding(self, owner: Scope, node: ast.AST, name: str) -> NameBinding:
        sites = owner.bindings.get(name, [])
        if (
            isinstance(owner.node, ast.ClassDef)
            and sites
            and all(
                (location(site)[0], location(site)[2]) > (location(node)[0], location(node)[2])
                for site in sites
            )
        ):
            # An unbound class-local name falls through to globals, not a later local value.
            return self._binding(self.root, node, name)
        targets: set[str] = set()
        kinds: set[BindingKind] = set()
        for site in sites:
            if isinstance(site, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                targets.add(f"{owner.qualified_name}.{site.name}")
                kinds.add("declaration")
            elif isinstance(site, ast.Import | ast.ImportFrom):
                alias = self.module.import_aliases.get(site, {}).get(name)
                if alias is not None:
                    targets.add(alias.target)
                    kinds.add(alias.kind)
        if targets:
            return NameBinding(
                owner,
                tuple(sorted(targets)),
                next(iter(kinds)) if len(kinds) == 1 else "mixed",
                len(sites) != 1
                or len(targets) != 1
                or any(control_flow_contexts(site, self.parents) for site in sites),
            )
        if sites or owner is not self.root:
            return NameBinding(
                owner,
                kind="local",
                uncertain=len(sites) != 1
                or any(control_flow_contexts(site, self.parents) for site in sites),
            )
        if any(
            isinstance(site, ast.ImportFrom) and any(alias.name == "*" for alias in site.names)
            for sites in owner.bindings.values()
            for site in sites
        ):
            return NameBinding(owner)
        return NameBinding(owner, kind="unbound")

    def receiver_class(self, binding: NameBinding, name: str) -> str | None:
        owner = binding.owner
        if owner is None or not isinstance(owner.node, ast.FunctionDef | ast.AsyncFunctionDef):
            return None
        node = owner.node
        parent = owner.parent
        parameters = (*node.args.posonlyargs, *node.args.args)
        if (
            parent is None
            or not isinstance(parent.node, ast.ClassDef)
            or not parameters
            or parameters[0].arg != name
            or len(owner.bindings.get(name, [])) != 1
            or node.decorator_list
        ):
            return None
        return parent.qualified_name
