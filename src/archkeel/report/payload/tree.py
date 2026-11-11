# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The node tree of the payload: system, packages, components and modules (AD-361).

`parent` is the component tree: a module belongs to its innermost owning component, a component
to its parent component or to the system. Packages form their own tree under the system, and the
`package` column links a module to its package. No ancestor or reachability pair is stored.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import ABSENT, LEVEL, code
from archkeel.report.payload.records import Component, Records

SYSTEM = 0


@dataclass(frozen=True)
class Tree:
    level: tuple[int, ...]
    parent: tuple[int, ...]
    key: tuple[str, ...]
    name: tuple[str, ...]
    path: tuple[str | None, ...]
    package: tuple[int, ...]
    module_node: Mapping[str, int]
    component_node: Mapping[str, int]
    component_of_node: Mapping[int, Component]
    chain: Mapping[str, tuple[int, ...]]
    ancestors: Mapping[int, frozenset[int]]


@dataclass(frozen=True)
class _Spec:
    level: str
    depth: int
    key: str
    name: str
    path: str | None
    parent: str
    package: str | None


def _parents(components: Sequence[Component]) -> dict[str, str | None]:
    by_title: defaultdict[str, list[str]] = defaultdict(list)
    for item in components:
        by_title[item.title].append(item.id)
    ids = {item.id for item in components}
    out: dict[str, str | None] = {}
    for item in components:
        ref = item.parent_id
        if ref is None:
            out[item.id] = None
        elif ref in ids:
            out[item.id] = ref
        else:
            titled = by_title.get(ref, [])
            out[item.id] = titled[0] if len(titled) == 1 else None
    return out


def _depths(parents: Mapping[str, str | None]) -> dict[str, int]:
    depth: dict[str, int] = {}
    for start in parents:
        seen: list[str] = []
        current: str | None = start
        while current is not None and current not in depth and current not in seen:
            seen.append(current)
            current = parents[current]
        base = depth.get(current, -1) if current is not None else -1
        for offset, item in enumerate(reversed(seen), start=1):
            depth[item] = base + offset
    return depth


def _in_package(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _claim(component: Component, module: str) -> tuple[int, int] | None:
    if module in component.exact_modules:
        return (2, 0)
    lengths = [len(p) for p in component.packages if _in_package(module, p)]
    return (1, max(lengths)) if lengths else None


def ownership(records: Records) -> tuple[dict[str, tuple[str, ...]], dict[str, str | None]]:
    """Return the component chain (outermost first) of each owned module and the parents."""
    components = records.components
    parents = _parents(components)
    depth = _depths(parents)
    top_claims: defaultdict[str, list[str]] = defaultdict(list)
    for item in components:
        if parents[item.id] is None:
            for module in records.scopes.get(item.id, ()):
                top_claims[module].append(item.id)
    chain: dict[str, tuple[str, ...]] = {
        m: (owners[0],) for m, owners in top_claims.items() if len(owners) == 1
    }
    children: defaultdict[str, list[Component]] = defaultdict(list)
    for item in components:
        above = parents[item.id]
        if above is not None:
            children[above].append(item)
    for parent_id in sorted(children, key=lambda c: (depth[c], c)):
        for module in sorted(m for m, c in chain.items() if c[-1] == parent_id):
            scored = [
                (s, child.id) for child in children[parent_id] if (s := _claim(child, module))
            ]
            if not scored:
                continue
            best = max(score for score, _ in scored)
            winners = [cid for score, cid in scored if score == best]
            if len(winners) == 1:
                chain[module] = (*chain[module], winners[0])
    return chain, parents


def _package_parent(name: str, packages: frozenset[str]) -> str | None:
    parts = name.split(".")
    for end in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in packages:
            return candidate
    return None


def _package_specs(packages: frozenset[str]) -> list[_Spec]:
    specs = []
    for name in sorted(packages):
        above = _package_parent(name, packages)
        level_depth, cursor = 1, above
        while cursor is not None:
            level_depth += 1
            cursor = _package_parent(cursor, packages)
        parent = "package:" + above if above else ""
        specs.append(_Spec("package", level_depth, "package:" + name, name, None, parent, None))
    return specs


def _specs(
    records: Records, chain: Mapping[str, tuple[str, ...]], parents: Mapping[str, str | None]
) -> list[_Spec]:
    depth = _depths(parents)
    packages = frozenset(records.packages)
    specs = [_Spec("system", 0, "", "", None, "", None), *_package_specs(packages)]
    for item in records.components:
        above = parents[item.id]
        parent = "component:" + above if above else ""
        specs.append(
            _Spec(
                "component", depth[item.id], "component:" + item.id, item.title, None, parent, None
            )
        )
    for module in records.modules:
        owner = chain.get(module.name)
        package = "package:" + module.package if module.package in packages else None
        parent = "component:" + owner[-1] if owner else ""
        specs.append(
            _Spec("module", 0, "module:" + module.name, module.name, module.file, parent, package)
        )
    specs.sort(key=lambda s: (code(LEVEL, s.level), s.depth, s.key))
    return specs


def _ancestors(
    modules: Mapping[str, int], parent: Sequence[int], package: Sequence[int]
) -> dict[int, frozenset[int]]:
    """Return, per module node, every node above it in the component and the package tree."""
    out: dict[int, frozenset[int]] = {}
    for node in modules.values():
        found: set[int] = set()
        for start in (node, package[node]):
            step = start
            while step != ABSENT:
                found.add(step)
                step = parent[step]
        out[node] = frozenset(found)
    return out


def build_tree(records: Records) -> Tree:
    """Build the sorted node table: level, then depth, then key; a parent before its children."""
    chain, parents = ownership(records)
    specs = _specs(records, chain, parents)
    index = {spec.key: position for position, spec in enumerate(specs)}
    if len(index) != len(specs):
        raise ValueError("two nodes of the payload have the same key")
    parent = tuple(ABSENT if s.level == "system" else index[s.parent] for s in specs)
    package_column = tuple(index[s.package] if s.package else ABSENT for s in specs)
    component_node = {item.id: index["component:" + item.id] for item in records.components}
    module_node = {m.name: index["module:" + m.name] for m in records.modules}
    return Tree(
        level=tuple(code(LEVEL, s.level) for s in specs),
        parent=parent,
        key=tuple(s.key for s in specs),
        name=tuple(s.name for s in specs),
        path=tuple(s.path for s in specs),
        package=package_column,
        module_node=module_node,
        component_node=component_node,
        component_of_node={component_node[item.id]: item for item in records.components},
        chain={m: tuple(component_node[c] for c in owners) for m, owners in chain.items()},
        ancestors=_ancestors(module_node, parent, package_column),
    )
