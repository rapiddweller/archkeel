# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record the names a function binds and never reads (AD-26).

A parameter or local that no expression in its own body loads is settled inside one scope,
so this signal needs no cross-module resolution: the function's own tree answers it. The
record stays a fact; calling such a binding dead is a review claim in `ir`, never a verdict.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, classified, stable_id
from .source import ParsedModule, add_evidence, body_is_empty, location

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _own_scope(node: FunctionNode) -> Iterator[ast.AST]:
    """Walk the function body, stopping at a nested function or class of its own."""
    stack: list[ast.AST] = list(node.body)
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(current))


def _loaded_names(node: FunctionNode) -> set[str]:
    """Every name read below the function, reads from a closure included."""
    names: set[str] = set()
    for child in ast.walk(node):
        # `del value` is the idiom for consuming a binding on purpose, so it counts as a read.
        if isinstance(child, ast.Name) and not isinstance(child.ctx, ast.Store):
            names.add(child.id)
        elif isinstance(child, ast.Global | ast.Nonlocal):
            names.update(child.names)
    return names


def _parameter_names(node: FunctionNode) -> set[str]:
    arguments = node.args
    names = {
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    }
    for collected in (arguments.vararg, arguments.kwarg):
        if collected is not None:
            names.add(collected.arg)
    return names


def _local_names(node: FunctionNode) -> set[str]:
    return {
        child.id
        for child in _own_scope(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    }


def _signature_is_fixed(node: FunctionNode, *, inherits: bool) -> bool:
    """True where something other than the body chooses the parameters.

    A protocol, overload or abstract stub binds parameters it cannot read.
    """
    return inherits or bool(node.decorator_list) or body_is_empty(node)


def _is_deliberate(name: str) -> bool:
    """A leading underscore is Python's own way of saying a binding is unused on purpose."""
    return name.startswith("_") or name in {"self", "cls"}


class BindingCollector(ast.NodeVisitor):
    """Walk one module and record every parameter or local its function never reads."""

    def __init__(self, module: ParsedModule, evidence: dict[str, RawEvidence]) -> None:
        self.module = module
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scope_stack: list[str] = [module.module]
        self.inherits_stack: list[bool] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.inherits_stack.append(bool(node.bases))
        self.generic_visit(node)
        self.inherits_stack.pop()
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: FunctionNode) -> None:
        owner = f"{self.scope_stack[-1]}.{node.name}"
        loaded = _loaded_names(node)
        inherits = bool(self.inherits_stack and self.inherits_stack[-1])
        if not _signature_is_fixed(node, inherits=inherits):
            for name in sorted(_parameter_names(node) - loaded):
                self._record(node, owner, name, "parameter")
        for name in sorted(_local_names(node) - loaded):
            self._record(node, owner, name, "local")
        self.scope_stack.append(owner)
        self.generic_visit(node)
        self.scope_stack.pop()

    def _record(self, node: FunctionNode, owner: str, name: str, binding: str) -> None:
        if _is_deliberate(name):
            return
        line, _, column = location(node)
        evidence_id = add_evidence(self.evidence, self.module, node)
        self.items.append(
            classified(
                item_id=stable_id("BIND", self.module.rel_path, line, column, binding, name),
                evidence_class=EvidenceClass.FACT,
                area="repository_topology",
                kind=f"unused_{binding}",
                title=f"{owner} never reads {name}",
                subjects=[owner, self.module.module],
                evidence_ids=[evidence_id],
                data={
                    "owner": owner,
                    "module": self.module.module,
                    "name": name,
                    "binding": binding,
                },
            )
        )


def collect_bindings(
    parsed: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    """Run the binding collector over every module and sort the records by id."""
    items: list[RawRecord] = []
    for module in parsed:
        collector = BindingCollector(module, evidence)
        collector.visit(module.tree)
        items.extend(collector.items)
    items.sort(key=lambda item: item["id"])
    return items
