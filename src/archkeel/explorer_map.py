# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project bounded maps from the same component and relation rows as the report."""

import json
import sqlite3
from pathlib import PurePosixPath
from typing import Any


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


def _call_edges(db: sqlite3.Connection, visible: list[str]) -> tuple[list[dict[str, Any]], int]:
    marks = ",".join("?" for _ in visible)
    sql = (
        "WITH RECURSIVE descendants(visible,id,depth) AS ("
        f"SELECT id,id,0 FROM element WHERE id IN ({marks}) UNION ALL "
        "SELECT descendants.visible,element.id,descendants.depth+1 FROM descendants "
        "JOIN element ON element.parent=descendants.id WHERE descendants.depth<128), "
        "nearest AS (SELECT visible,id,row_number() OVER "
        "(PARTITION BY id ORDER BY depth,visible) AS rank FROM descendants), "
        "pairs AS (SELECT a.visible AS source,b.visible AS target,count(*) AS count, "
        "min(relation.id) AS relation_id FROM relation "
        "JOIN nearest a ON a.id=relation.source AND a.rank=1 "
        "JOIN nearest b ON b.id=relation.target AND b.rank=1 "
        "WHERE relation.kind='call' AND relation.target IS NOT NULL "
        "AND json_extract(relation.body,'$.resolution')='resolved' AND a.visible!=b.visible "
        "GROUP BY a.visible,b.visible) "
        "SELECT source,target,count,relation_id,count(*) OVER () FROM pairs "
        "ORDER BY source,target LIMIT 500"
    )
    rows = db.execute(sql, visible).fetchall()
    edges = [
        {
            "id": row[3],
            "relation_id": row[3],
            "source": row[0],
            "target": row[1],
            "count": row[2],
            "kind": "call",
            "resolution": "resolved",
            "aggregate": True,
        }
        for row in rows
    ]
    return edges, rows[0][4] if rows else 0


def _edges(
    db: sqlite3.Connection, items: list[dict[str, Any]], groups: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    visible = [
        item["id"] for item in [*items, *groups] if item["kind"] not in {"layer", "directory"}
    ]
    edges: list[dict[str, Any]] = []
    edge_total = 0
    if visible:
        marks = ",".join("?" for _ in visible)
        unresolved = dict(
            db.execute(
                "WITH RECURSIVE ancestors(call_id, owner) AS ("
                "SELECT id,source FROM relation WHERE kind='call' AND target IS NULL UNION "
                "SELECT ancestors.call_id,element.parent FROM ancestors JOIN element "
                "ON element.id=ancestors.owner WHERE element.parent IS NOT NULL "
                "AND element.parent!='system') "
                f"SELECT owner,count(*) FROM ancestors WHERE owner IN ({marks}) GROUP BY owner",
                visible,
            ).fetchall()
        )
        for item in [*items, *groups]:
            if item["id"] in unresolved:
                item["unresolved_calls"] = unresolved[item["id"]]
        marks = ",".join("?" for _ in visible)
        where = (
            f"source IN ({marks}) AND (target IN ({marks}) OR target IS NULL) "
            "AND kind IN ('import','call','requires','interface')"
        )
        edge_total = db.execute(
            "SELECT count(*) FROM relation WHERE " + where, (*visible, *visible)
        ).fetchone()[0]
        edge_rows = db.execute(
            "SELECT body FROM relation WHERE " + where + " ORDER BY id LIMIT 500",
            (*visible, *visible),
        ).fetchall()
        edges = [json.loads(row[0]) for row in edge_rows]
        if any(item["kind"] in {"module", "component"} for item in items):
            calls, call_total = _call_edges(db, visible)
            edge_total += call_total
            edges = calls + edges[: max(0, 500 - len(calls))]
    return edges, edge_total


def _map_view(
    db: sqlite3.Connection, parent: str, view: str, cursor: str, limit: int
) -> dict[str, object]:
    """Read a page of hierarchy and its measured relationships."""
    if view not in {"components", "modules"}:
        raise ValueError("invalid map view")
    scope = (
        None
        if parent == "system"
        else db.execute("SELECT kind FROM element WHERE id=?", (parent,)).fetchone()
    )
    if parent != "system" and scope is None:
        raise ValueError("unknown map parent")
    if view == "modules" and (scope is None or scope[0] == "component"):
        base = (
            "WITH RECURSIVE scope(id) AS (SELECT ? UNION SELECT element.id FROM element "
            "JOIN scope ON element.parent=scope.id WHERE element.kind='component') "
            "SELECT id,body FROM element WHERE kind='module' AND parent IN (SELECT id FROM scope)"
        )
        params: tuple[object, ...] = (parent,)
    else:
        kinds = (
            ("component",)
            if scope is None or scope[0] == "component"
            else ("class", "function", "method", "property")
        )
        marks = ",".join("?" for _ in kinds)
        base = f"SELECT id,body FROM element WHERE parent=? AND kind IN ({marks})"
        params = (parent, *kinds)
        if kinds == ("component",) and not db.execute(base + " LIMIT 1", params).fetchone():
            base = "SELECT id,body FROM element WHERE parent=? AND kind='module'"
            params = (parent,)
    total = db.execute("SELECT count(*) FROM (" + base + ")", params).fetchone()[0]
    rows = db.execute(
        base + " AND id>? ORDER BY id LIMIT ?", (*params, cursor, limit + 1)
    ).fetchall()
    items = [json.loads(row[1]) for row in rows[:limit]]
    groups = _groups(db, parent, items)
    edges, edge_total = _edges(db, items, groups)
    return {
        "parent": parent,
        "view": view,
        "items": items,
        "groups": groups,
        "edges": edges,
        "total": total,
        "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
        "edge_total": edge_total,
        "edges_truncated": edge_total > len(edges),
    }
