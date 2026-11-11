# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The rows that explain a FAIL or an UNKNOWN: violations and unknowns (AD-361).

A violation row holds what `archkeel.api.load_violations` returns for the same record, and the
file and line of its first evidence. An unknown row comes from a record of the unknowns section,
a coverage failure, a diagnostic of the run, or the missing Target. Each row names a node.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import ABSENT, LEVEL, UNKNOWN_SOURCE, code, reason_code
from archkeel.report.payload.evaluation import Evaluation
from archkeel.report.payload.records import Records
from archkeel.report.payload.tree import SYSTEM, Tree

_PACKAGE = code(LEVEL, "package")


@dataclass(frozen=True)
class ViolationRow:
    kind: str
    rules: tuple[str, ...]
    subjects: tuple[str, ...]
    source_module: str | None
    target_module: str | None
    symbol: str | None
    source_component: int
    target_component: int
    evidence: tuple[str, ...]
    path: str | None
    line: int
    node: int


@dataclass(frozen=True)
class UnknownRow:
    source: int
    reason: int
    kind: str
    node: int
    rule: str | None
    detail: str


def _in_package(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _owner(module: str | None, records: Records, tree: Tree) -> int:
    """The one top-level component that claims a module, the rule of `ir.ownership.owner_of`."""
    if module is None:
        return ABSENT
    claims = [
        c
        for c in records.components
        if c.top and (module in c.exact_modules or any(_in_package(module, p) for p in c.packages))
    ]
    return tree.component_node[claims[0].id] if len(claims) == 1 else ABSENT


def build_violations(records: Records, tree: Tree) -> tuple[ViolationRow, ...]:
    """Return one row per violation record, by record id."""
    rows = []
    for item in records.violations:
        named = [
            m
            for m in (item.source_module, *item.subjects)
            if m is not None and m in tree.module_node
        ]
        rows.append(
            ViolationRow(
                kind=item.kind,
                rules=item.rules,
                subjects=item.subjects,
                source_module=item.source_module,
                target_module=item.target_module,
                symbol=item.symbol,
                source_component=_owner(item.source_module, records, tree),
                target_component=_owner(item.target_module, records, tree),
                evidence=item.evidence_ids,
                path=item.path,
                line=item.line,
                node=tree.module_node[named[0]] if named else ABSENT,
            )
        )
    return tuple(rows)


def _node(names: Sequence[str], tree: Tree, places: Mapping[str, int]) -> int:
    """The module, file or package that a reason names; else the system."""
    for name in names:
        if name in tree.module_node:
            return tree.module_node[name]
    for name in names:
        if name in places:
            return places[name]
    return SYSTEM


def build_unknowns(records: Records, tree: Tree, verdicts: Evaluation) -> tuple[UnknownRow, ...]:
    """Return the unknown rows, by source, node, reason, kind, detail and rule."""
    files = {path: index for index, path in enumerate(tree.path) if path is not None}
    packages = {tree.name[i]: i for i, level in enumerate(tree.level) if level == _PACKAGE}
    files = {**packages, **files}
    record, diagnostic, run = (code(UNKNOWN_SOURCE, name) for name in UNKNOWN_SOURCE)
    rows = [
        UnknownRow(
            record,
            reason_code(item.kind),
            item.kind,
            _node([*([item.module] if item.module else []), *item.subjects], tree, files),
            item.rules[0] if item.rules else None,
            item.title,
        )
        for item in records.unknowns
    ]
    rows += [
        UnknownRow(
            diagnostic, reason_code(d.kind), d.kind, _node([d.subject], tree, files), None, d.claim
        )
        for d in verdicts.diagnostics
    ]
    if not verdicts.target:
        rows.append(UnknownRow(run, reason_code("no_target"), "no_target", SYSTEM, None, ""))
    return tuple(
        sorted(rows, key=lambda r: (r.source, r.node, r.reason, r.kind, r.detail, r.rule or ""))
    )
