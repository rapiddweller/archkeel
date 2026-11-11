# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Findings: hubs and cycles, each with its disposition and reason (AD-361).

Every cycle record gets a row. A package cycle that no module cycle backs exists only in the
roll-up: it is `context` and `run.not_ranked` counts it; every other cycle is ranked and
`summary.counts.cycles` counts it. A hub row names the gap that keeps its declared block empty.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import (
    ABSENT,
    CARRIER_CAP,
    DISPOSITION,
    FINDING_KIND,
    HUB_ABSOLUTE,
    HUB_RELATIVE_PERMILLE,
    LEVEL,
    PERMISSION,
    REASON,
    code,
)
from archkeel.report.payload.graph import Edge
from archkeel.report.payload.permissions import Permission
from archkeel.report.payload.records import Records
from archkeel.report.payload.tree import SYSTEM, Tree

Carrier = tuple[str, int, int]


@dataclass(frozen=True)
class Finding:
    kind: int
    subject: int
    value: int
    pool: int
    absolute: int
    relative_permille: int
    disposition: int
    reason: int
    carrier_total: int
    carriers: tuple[Carrier, ...]
    gap: str | None


def _top_owner(tree: Tree, node: int) -> int:
    for owner in tree.chain.get(tree.name[node], ()):
        return owner
    return ABSENT


def _pools(
    tree: Tree, records: Records, permissions: Sequence[Permission]
) -> tuple[dict[int, int], dict[int, int]]:
    """The modules that may import a module, and that it may import, under the contract."""
    modules = sorted(tree.ancestors)
    everyone = len(modules) - 1
    if records.contract is None or not tree.component_of_node:
        return dict.fromkeys(modules, everyone), dict.fromkeys(modules, everyone)
    allowed = {(p.component, p.target) for p in permissions if PERMISSION[p.status] == "allowed"}
    count: defaultdict[int, int] = defaultdict(int)
    for m in modules:
        count[_top_owner(tree, m)] += 1
    pools_in: dict[int, int] = {}
    pools_out: dict[int, int] = {}
    for m in modules:
        owner = _top_owner(tree, m)
        if owner == ABSENT:
            pools_in[m] = pools_out[m] = everyone
            continue
        users = {a for (a, b) in allowed if b == owner} | {owner}
        used = {b for (a, b) in allowed if a == owner} | {owner}
        pools_in[m] = sum(count[c] for c in users) - 1
        pools_out[m] = sum(count[c] for c in used) - 1
    return pools_in, pools_out


def _hub_gap(records: Records, tree: Tree, module: int, kind: str) -> str:
    """The gap that keeps the declared block of a hub empty: no list, no role, or no contract."""
    if records.contract is None:
        return "G-NO-CONTRACT"
    if kind == "fan_out_hub":
        return "G-ROLES"
    owner = tree.component_of_node.get(_top_owner(tree, module))
    return "G-PUBLIC-API" if owner is None or owner.public_api is None else "G-ROLES"


def _hubs(
    records: Records, tree: Tree, edges: Sequence[Edge], permissions: Sequence[Permission]
) -> list[Finding]:
    fan_in: defaultdict[int, set[int]] = defaultdict(set)
    fan_out: defaultdict[int, set[int]] = defaultdict(set)
    carried: defaultdict[int, dict[str, tuple[set[int], int]]] = defaultdict(dict)
    for edge in (e for e in edges if e.level == code(LEVEL, "module")):
        fan_in[edge.target].add(edge.source)
        fan_out[edge.source].add(edge.target)
        names = carried[edge.target]
        for crossing in edge.crossings:
            importers, unit = names.get(crossing.name, (set(), crossing.unit))
            importers.add(edge.source)
            names[crossing.name] = (importers, unit)
    pools_in, pools_out = _pools(tree, records, permissions)
    facades = frozenset(records.packages)
    found = []
    for module in sorted(tree.ancestors):
        for kind, value, pool in (
            ("fan_in_hub", len(fan_in[module]), pools_in[module]),
            ("fan_out_hub", len(fan_out[module]), pools_out[module]),
        ):
            if value < HUB_ABSOLUTE or value * 1000 < HUB_RELATIVE_PERMILLE * pool:
                continue
            carriers: list[Carrier] = []
            disposition, reason = "ranked", "open_question"
            if kind == "fan_in_hub":
                carriers = sorted(
                    ((n, len(i), u) for n, (i, u) in carried[module].items()),
                    key=lambda c: (-c[1], c[0]),
                )
                if tree.name[module] in facades:
                    disposition, reason = "context", "crate_facade"
            found.append(
                Finding(
                    code(FINDING_KIND, kind),
                    module,
                    value,
                    pool,
                    HUB_ABSOLUTE,
                    HUB_RELATIVE_PERMILLE,
                    code(DISPOSITION, disposition),
                    code(REASON, reason),
                    len(carriers),
                    tuple(carriers[:CARRIER_CAP]),
                    _hub_gap(records, tree, module, kind),
                )
            )
    return found


def _cycle_subject(tree: Tree, level: str, members: Sequence[str]) -> int:
    keys = {key: index for index, key in enumerate(tree.key)}
    prefix = level + ":" if level in ("module", "component", "package") else ""
    nodes = sorted(keys[prefix + m] for m in members if prefix + m in keys)
    return nodes[0] if nodes else SYSTEM


def build_findings(
    records: Records, tree: Tree, edges: Sequence[Edge], permissions: Sequence[Permission]
) -> tuple[Finding, ...]:
    """Return the hub and cycle findings, by disposition, kind, value descending, subject."""
    found = _hubs(records, tree, edges, permissions)
    for level, members, backed in records.cycles:
        rollup = level == "package" and not backed
        found.append(
            Finding(
                code(FINDING_KIND, "cycle"),
                _cycle_subject(tree, level, members),
                len(members),
                ABSENT,
                ABSENT,
                ABSENT,
                code(DISPOSITION, "context" if rollup else "ranked"),
                code(REASON, "rule_passes" if rollup else "open_question"),
                0,
                (),
                None,
            )
        )
    found.sort(key=lambda f: (f.disposition, f.kind, -f.value, f.subject))
    return tuple(found)
