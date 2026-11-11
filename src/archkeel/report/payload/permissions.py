# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The permission of each ordered pair of sibling components (AD-361).

The same decision as `report --only architecture`: a forbidden dependency rule forbids the pair;
else a complete_requires rule of the level forbids a pair without a requires entry; else a
requires entry or an allowed dependency rule allows it; else the pair is undecided. A rule
decides a whole pair only when its source and target are each one sibling's declared package.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import PERMISSION, code
from archkeel.report.payload.records import Component, DependencyRule, Records
from archkeel.report.payload.tree import Tree


@dataclass(frozen=True)
class Permission:
    component: int
    target: int
    status: int
    rule: str | None


def _resolve(name: str, item: Component, group: Sequence[Component]) -> Component | None:
    others = [c for c in group if c.id != item.id]
    prefix = item.parent_id + ":" if item.parent_id else ""
    for found in (
        [c for c in others if c.id == name],
        [c for c in others if c.title == name],
        [c for c in others if prefix and c.id == prefix + name],
    ):
        if len(found) == 1:
            return found[0]
    return None


def requires_pairs(records: Records) -> dict[tuple[str, str], str | None]:
    """Each resolved `requires` entry between siblings, by component id, with its rationale."""
    groups = _groups(records.components)
    out: dict[tuple[str, str], str | None] = {}
    for group in groups.values():
        for item in group:
            for entry in item.requires:
                other = _resolve(entry.component, item, group)
                if other is not None:
                    out.setdefault((item.id, other.id), entry.rationale)
    return out


def _groups(components: Sequence[Component]) -> dict[str | None, list[Component]]:
    groups: defaultdict[str | None, list[Component]] = defaultdict(list)
    for item in components:
        groups[item.parent_id].append(item)
    return groups


def _pair(rule: DependencyRule, group: Sequence[Component]) -> tuple[str, str] | None:
    if not rule.whole_pair or rule.source is None or rule.target is None:
        return None
    sources = [c.id for c in group if rule.source in c.packages]
    targets = [c.id for c in group if rule.target in c.packages]
    return (sources[0], targets[0]) if len(sources) == 1 and len(targets) == 1 else None


def _decide(
    pair: tuple[str, str],
    rules: Sequence[DependencyRule],
    deciding: Mapping[str, tuple[str, str] | None],
    requires: bool,
) -> tuple[str, str | None]:
    forbidden = sorted(
        r.id
        for r in rules
        if r.kind == "forbidden_dependency" and deciding[r.id] == pair and not r.allowed_sources
    )
    allowed = sorted(
        r.id for r in rules if r.kind == "allowed_dependency" and deciding[r.id] == pair
    )
    complete = sorted(r.id for r in rules if r.kind == "complete_requires")
    if forbidden:
        return "forbidden", forbidden[0]
    if complete and not requires:
        return "forbidden", complete[0]
    if requires or allowed:
        return "allowed", allowed[0] if allowed else None
    return "undecided", None


def build_permissions(records: Records, tree: Tree) -> tuple[Permission, ...]:
    """Return one row per ordered pair of sibling components, by component, then target."""
    requires = requires_pairs(records)
    rows = []
    for parent, group in _groups(records.components).items():
        rules = [r for r in records.dependency_rules if r.parent_id == parent]
        deciding = {r.id: _pair(r, group) for r in rules}
        for item in group:
            for other in group:
                if other.id == item.id:
                    continue
                pair = (item.id, other.id)
                status, rule = _decide(pair, rules, deciding, pair in requires)
                rows.append(
                    Permission(
                        tree.component_node[item.id],
                        tree.component_node[other.id],
                        code(PERMISSION, status),
                        rule,
                    )
                )
    return tuple(sorted(rows, key=lambda p: (p.component, p.target)))


def permission_of(permissions: Sequence[Permission]) -> dict[tuple[int, int], Permission]:
    """Index the permission rows by their pair of component nodes."""
    return {(p.component, p.target): p for p in permissions}
