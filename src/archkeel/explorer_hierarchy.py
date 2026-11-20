# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read module containment and collapse dense real branches for the map."""

import json
import sqlite3
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, TypedDict


class _ModuleHierarchy(TypedDict):
    """Visible module-map nodes and their read coverage."""

    parent: str
    view: str
    module_overview: bool
    module_total: int
    items: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    total: int
    next_cursor: None
    coarse: bool
    scope_truncated: bool


def _groups(
    db: sqlite3.Connection, parent: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    pending = [item["parent"] for item in items if item["parent"] != parent]
    while pending:
        key = pending.pop()
        if key == parent or key in groups:
            continue
        row = db.execute(
            "SELECT body FROM element WHERE id=? AND kind='component'", (key,)
        ).fetchone()
        if row is None:
            continue
        group = json.loads(row[0])
        groups[key] = group
        pending.append(group["parent"])
    owners: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if item["kind"] == "module" and isinstance(item.get("path"), str):
            owners.setdefault(item["parent"], []).append(item)
    for owner, modules in owners.items():
        paths = [PurePosixPath(item["path"]).parent for item in modules]
        if len(set(paths)) < 2:
            continue
        common = list(paths[0].parts)
        for path in paths[1:]:
            while tuple(common) != path.parts[: len(common)]:
                common.pop()
        for item, path in zip(modules, paths, strict=True):
            current = owner
            for index in range(len(common) + 1, len(path.parts) + 1):
                folder = PurePosixPath(*path.parts[:index]).as_posix()
                key = json.dumps(["directory", owner, folder], separators=(",", ":"))
                groups.setdefault(
                    key,
                    {
                        "id": key,
                        "name": path.parts[index - 1],
                        "kind": "directory",
                        "parent": current,
                        "owner": owner,
                        "path": folder,
                    },
                )
                current = key
            item["parent"] = current
    for item in [*groups.values(), *items]:
        layer = item.get("layer")
        if item.get("kind") != "component" or not isinstance(layer, str) or not layer:
            continue
        owner = item["parent"]
        group_id = json.dumps(["layer", owner, layer], separators=(",", ":"))
        groups.setdefault(
            group_id, {"id": group_id, "name": layer, "kind": "layer", "parent": owner}
        )
        item["parent"] = group_id
    return list(groups.values())


def _hierarchy_branch(
    parent: str, nodes: list[dict[str, Any]], forced: set[str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, str]]]:
    children: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        children.setdefault(node["parent"], []).append(node)
    items: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    aliases: list[tuple[str, str]] = []

    def descendants(key: str) -> list[dict[str, Any]]:
        return [
            node for child in children.get(key, []) for node in [child, *descendants(child["id"])]
        ]

    def visit(key: str) -> None:
        for node in children.get(key, []):
            underneath = descendants(node["id"])
            count = sum(child["kind"] == "module" for child in underneath)
            kind = node["kind"]
            threshold = 20 if kind == "layer" else 12
            collapsed = bool(underneath) and (
                kind == "component"
                or max(len(underneath), count) > threshold
                or (forced is not None and node["id"] in forced)
            )
            if kind in {"layer", "directory", "component"}:
                node["module_count"] = count
            if not underneath or collapsed:
                items.append(dict(node, collapsed=collapsed))
                if collapsed and kind in {"layer", "directory"}:
                    aliases.extend(
                        (node["id"], child["id"])
                        for child in underneath
                        if child["kind"] in {"component", "module"}
                    )
            else:
                groups.append(node)
                visit(node["id"])

    visit(parent)
    return items, groups, aliases


def _grouped_branch(
    parent: str, nodes: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, str]]]:
    items, groups, aliases = _hierarchy_branch(parent, nodes)
    if len(items) <= 36 or not groups:
        return items, groups, aliases
    parents = {group["id"]: group["parent"] for group in groups}
    underneath: dict[str, set[str]] = {group["id"]: set() for group in groups}
    for item in items:
        owner = item["parent"]
        while owner in parents:
            underneath[owner].add(item["id"])
            owner = parents[owner]
    forced = set()
    hidden: set[str] = set()
    visible = len(items)
    for owner, members in sorted(underneath.items(), key=lambda pair: -len(pair[1])):
        newly_hidden = members - hidden
        if len(newly_hidden) > 1:
            forced.add(owner)
            hidden.update(newly_hidden)
            visible -= len(newly_hidden) - 1
            if visible <= 36:
                break
    return _hierarchy_branch(parent, nodes, forced) if forced else (items, groups, aliases)


def _scope_id(db: sqlite3.Connection, parent: str) -> tuple[str, str, str]:
    if parent.startswith("["):
        identity = json.loads(parent)
        if (
            not isinstance(identity, list)
            or len(identity) != 3
            or not all(isinstance(value, str) for value in identity)
            or identity[0] not in {"layer", "directory"}
        ):
            raise ValueError("unknown map parent")
        kind, owner, name = identity
    else:
        kind, owner, name = "component", parent, ""
    if (
        owner != "system"
        and db.execute("SELECT 1 FROM element WHERE id=? AND kind='component'", (owner,)).fetchone()
        is None
    ):
        raise ValueError("unknown map parent")
    return kind, owner, name


def _scope_query(kind: str, owner: str, name: str) -> tuple[str, tuple[str, ...]]:
    if kind == "directory":
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts:
            raise ValueError("unknown map parent")
        prefix = path.as_posix().rstrip("/") + "/"
        return (
            "SELECT id,kind,body FROM element WHERE parent=? AND kind='module' "
            "AND substr(json_extract(body,'$.path'),1,length(?))=?",
            (owner, prefix, prefix),
        )
    params: tuple[str, ...]
    if kind == "layer":
        seed = (
            "SELECT id FROM element WHERE parent=? AND kind='component' "
            "AND json_extract(body,'$.layer')=?"
        )
        params = (owner, name)
    else:
        seed = "SELECT ?"
        params = (owner,)
    return (
        "WITH RECURSIVE scope(id) AS (" + seed + " UNION SELECT element.id FROM element "
        "JOIN scope ON element.parent=scope.id WHERE element.kind='component') "
        "SELECT id,kind,body FROM element WHERE kind IN ('module','component') AND id!=? "
        "AND (id IN (SELECT id FROM scope) OR parent IN (SELECT id FROM scope))",
        (*params, owner),
    )


def _range_scope(parent: str) -> tuple[str, str, str] | None:
    if parent.startswith('["file_group",'):
        value = json.loads(parent)
        if (
            len(value) == 4
            and all(isinstance(item, str) for item in value)
            and value[2] <= value[3]
        ):
            return value[1], value[2], value[3]
        raise ValueError("unknown map parent")
    return None


def _bound_branch(
    root: str, parent: str, items: list[dict[str, Any]], aliases: list[tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    if len(items) <= 36:
        return items, aliases
    aliases_by_item = defaultdict(list)
    for group, member in aliases:
        aliases_by_item[group].append(member)
    ordered = sorted(items, key=lambda item: item["id"])
    width = max(36, (len(ordered) + 35) // 36)
    cards: list[dict[str, Any]] = []
    connections: list[tuple[str, str]] = []
    for start in range(0, len(ordered), width):
        chunk = ordered[start : start + width]
        first, last = chunk[0], chunk[-1]
        key = json.dumps(["file_group", root, first["id"], last["id"]], separators=(",", ":"))
        cards.append(
            {
                "id": key,
                "name": f"{first['name']} – {last['name']}",
                "kind": "file_group",
                "parent": parent,
                "collapsed": True,
                "module_count": sum(_module_count(item) for item in chunk),
            }
        )
        for item in chunk:
            connections.extend(
                (key, member) for member in aliases_by_item.get(item["id"], [item["id"]])
            )
    return cards, connections


def _module_count(item: dict[str, Any]) -> int:
    return 1 if item["kind"] == "module" else int(item.get("module_count", 0))


def _module_hierarchy(
    db: sqlite3.Connection, parent: str
) -> tuple[_ModuleHierarchy, list[tuple[str, str]]]:
    """Build the complete grouping before bounding the visible cards."""
    narrowed = _range_scope(parent)
    root = narrowed[0] if narrowed else parent
    kind, owner, name = _scope_id(db, root)
    base, params = _scope_query(kind, owner, name)
    scoped = [
        json.loads(row[0])
        for row in db.execute("SELECT body FROM (" + base + ") ORDER BY id", params)
    ]
    if kind != "component" and not scoped:
        raise ValueError("unknown map parent")
    parents = {item["parent"] for item in scoped}
    leaves = [node for node in scoped if node["id"] not in parents]
    nodes = [*_groups(db, owner, leaves), *leaves]
    if kind == "directory":
        for node in nodes:
            if node["parent"] == owner:
                node["parent"] = root
    items, groups, aliases = _grouped_branch(root, nodes)
    if narrowed:
        _, first, last = narrowed
        items = [dict(item, parent=parent) for item in items if first <= item["id"] <= last]
        if not items:
            raise ValueError("unknown map parent")
        visible = {item["id"] for item in items}
        aliases = [(group, member) for group, member in aliases if group in visible]
        groups = []
    module_total = (
        sum(_module_count(item) for item in items)
        if narrowed
        else sum(node["kind"] == "module" for node in scoped)
    )
    items, aliases = _bound_branch(root, parent, items, aliases)
    if items and items[0]["kind"] == "file_group":
        groups = []
    return {
        "parent": parent,
        "view": "hierarchy",
        "module_overview": any(item["collapsed"] for item in items),
        "module_total": module_total,
        "items": items,
        "groups": groups,
        "total": len(items),
        "next_cursor": None,
        "coarse": False,
        "scope_truncated": False,
    }, aliases


def _scoped_module_filter(db: sqlite3.Connection, parent: str, text: str) -> tuple[str, list[str]]:
    """Search every scoped module, including the ones outside a flat overview."""
    params: tuple[str, ...]
    if _range_scope(parent) is not None:
        layout, aliases = _module_hierarchy(db, parent)
        seeds = [item["id"] for item in layout["items"] if item["kind"] in {"module", "component"}]
        seeds.extend(member for _, member in aliases)
        base = (
            "WITH RECURSIVE scope(id) AS (SELECT value FROM json_each(?) UNION "
            "SELECT element.id FROM element JOIN scope ON element.parent=scope.id "
            "WHERE element.kind IN ('component','module')) "
            "SELECT id,kind FROM element WHERE id IN (SELECT id FROM scope)"
        )
        params = (json.dumps(seeds),)
    else:
        kind, owner, name = _scope_id(db, parent)
        base, params = _scope_query(kind, owner, name)
    where = (
        f"id IN (SELECT id FROM ({base}) WHERE kind='module') AND "
        "(instr(lower(name),lower(?))>0 OR instr(lower(json_extract(body,'$.path')),lower(?))>0)"
    )
    return where, [*params, text, text]
