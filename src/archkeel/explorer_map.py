# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project bounded maps from the same component and relation rows as the report."""

import json
import sqlite3
from typing import Any

from .explorer_hierarchy import _groups, _module_hierarchy, _scoped_module_filter


def _map_search(db: sqlite3.Connection, text: str, parent: str) -> tuple[str, list[str]]:
    if parent:
        return _scoped_module_filter(db, parent, text)
    return "instr(lower(name),lower(?))>0", [text]


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


def _projected_edges(
    db: sqlite3.Connection, visible: list[str], aliases: list[tuple[str, str]]
) -> tuple[list[dict[str, Any]], int]:
    sql = (
        "WITH RECURSIVE descendants(visible,id,depth) AS ("
        "SELECT json_extract(value,'$[0]'),json_extract(value,'$[1]'),0 FROM json_each(?) UNION "
        "SELECT descendants.visible,element.id,descendants.depth+1 FROM descendants "
        "JOIN element ON element.parent=descendants.id WHERE descendants.depth<128), "
        "nearest AS (SELECT visible,id,row_number() OVER "
        "(PARTITION BY id ORDER BY depth,visible) AS rank FROM descendants), "
        "owned_imports AS MATERIALIZED (SELECT DISTINCT "
        "json_extract(s.body,'$.component') AS source,json_extract(t.body,'$.component') AS target "
        "FROM relation JOIN element s ON s.id=relation.source AND s.kind='module' "
        "JOIN element t ON t.id=relation.target AND t.kind='module' "
        "WHERE relation.kind='import' AND json_extract(relation.body,'$.resolution')='resolved'), "
        "sites AS (SELECT a.visible AS source,b.visible AS target,relation.id,relation.kind, "
        "coalesce(json_extract(relation.body,'$.count'),1) AS weight, "
        "CASE WHEN relation.kind='import' AND (s.kind!='module' OR t.kind!='module') "
        "THEN 1 ELSE 0 END AS priority "
        "FROM relation JOIN nearest a ON a.id=relation.source AND a.rank=1 "
        "JOIN nearest b ON b.id=relation.target AND b.rank=1 "
        "JOIN element s ON s.id=relation.source JOIN element t ON t.id=relation.target "
        "LEFT JOIN owned_imports oi "
        "ON relation.kind='import' AND oi.source=s.id AND oi.target=t.id "
        "WHERE relation.kind IN ('import','call') AND a.visible!=b.visible "
        "AND json_extract(relation.body,'$.resolution')='resolved' "
        "AND oi.source IS NULL), "
        "ranked AS (SELECT *,min(priority) OVER "
        "(PARTITION BY kind,source,target) AS best FROM sites), "
        "pairs AS (SELECT source,target,kind,sum(weight) AS count,min(id) AS evidence "
        "FROM ranked WHERE priority=best GROUP BY source,target,kind) "
        "SELECT source,target,kind,count,evidence,count(*) OVER () FROM pairs "
        "ORDER BY source,target,kind LIMIT 10000"
    )
    seeds = json.dumps([*((item, item) for item in visible), *aliases])
    rows = db.execute(sql, (seeds,)).fetchall()
    return [
        {
            "id": evidence,
            "relation_id": evidence,
            "source": source,
            "target": target,
            "count": count,
            "kind": kind,
            "resolution": "resolved",
            "aggregate": True,
        }
        for source, target, kind, count, evidence, _ in rows
    ], rows[0][5] if rows else 0


def _edges(
    db: sqlite3.Connection,
    items: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    aliases: list[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    visible = [
        item["id"] for item in [*items, *groups] if item["kind"] not in {"layer", "directory"}
    ]
    edges: list[dict[str, Any]] = []
    edge_total = 0
    if visible:
        marks = ",".join("?" for _ in visible)
        counts = {
            owner: (total, missing)
            for owner, total, missing in db.execute(
                "WITH RECURSIVE ancestors(call_id,owner,missing) AS ("
                "SELECT id,source,target IS NULL OR "
                "json_extract(body,'$.resolution') IS NOT 'resolved' "
                "FROM relation WHERE kind='call' UNION "
                "SELECT ancestors.call_id,element.parent,ancestors.missing FROM ancestors "
                "JOIN element ON element.id=ancestors.owner WHERE element.parent IS NOT NULL "
                "AND element.parent!='system') "
                f"SELECT owner,count(*),sum(missing) FROM ancestors WHERE owner IN ({marks}) "
                "GROUP BY owner",
                visible,
            )
        }
        for item in [*items, *groups]:
            if item["id"] in visible:
                item["recorded_calls"], item["unresolved_calls"] = counts.get(item["id"], (0, 0))
        where = (
            f"source IN ({marks}) AND (target IN ({marks}) OR target IS NULL) "
            "AND kind IN ('import','call','requires','interface')"
        )
        if aliases is not None:
            where += " AND (kind IN ('requires','interface') OR target IS NULL)"
        edge_total = db.execute(
            "SELECT count(*) FROM relation WHERE " + where, (*visible, *visible)
        ).fetchone()[0]
        edge_rows = db.execute(
            "SELECT body FROM relation WHERE " + where + " ORDER BY id LIMIT 500",
            (*visible, *visible),
        ).fetchall()
        edges = [json.loads(row[0]) for row in edge_rows]
        if aliases is None and any(item["kind"] in {"module", "component"} for item in items):
            calls, call_total = _call_edges(db, visible)
            edge_total += call_total
            edges = calls + edges[: max(0, 500 - len(calls))]
    if aliases is not None:
        projected, observed_total = _projected_edges(db, visible, aliases)
        edge_total += observed_total
        edges.extend(projected)
    return edges, edge_total


def _count_modules(db: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    owners = [item["id"] for item in items if item["kind"] == "component"]
    if not owners:
        return
    marks = ",".join("?" for _ in owners)
    counts = dict(
        db.execute(
            "WITH RECURSIVE children(owner,id,kind) AS ("
            f"SELECT id,id,kind FROM element WHERE id IN ({marks}) UNION "
            "SELECT children.owner,element.id,element.kind FROM children JOIN element "
            "ON element.parent=children.id WHERE children.kind='component') "
            "SELECT owner,count(*) FROM children WHERE kind='module' GROUP BY owner",
            owners,
        )
    )
    for item in items:
        if item["kind"] == "component":
            item["module_count"] = counts.get(item["id"], 0)


def _map_view(
    db: sqlite3.Connection, parent: str, view: str, cursor: str, limit: int
) -> dict[str, object]:
    """Read a page of hierarchy and its measured relationships."""
    if view == "hierarchy":
        hierarchy, aliases = _module_hierarchy(db, parent)
        items, groups = hierarchy["items"], hierarchy["groups"]
        if hierarchy["coarse"]:
            _count_modules(db, items)
        edges, edge_total = _edges(db, items, groups, aliases)
        return hierarchy | {
            "edges": edges,
            "edge_total": edge_total,
            "edges_truncated": edge_total > len(edges),
        }
    if view not in {"components", "modules"}:
        raise ValueError("invalid map view")
    scope = (
        None
        if parent == "system"
        else db.execute("SELECT kind FROM element WHERE id=?", (parent,)).fetchone()
    )
    if parent != "system" and scope is None:
        raise ValueError("unknown map parent")
    module_total = None
    overview = False
    if view == "modules" and (scope is None or scope[0] == "component"):
        base = (
            "WITH RECURSIVE scope(id) AS (SELECT ? UNION SELECT element.id FROM element "
            "JOIN scope ON element.parent=scope.id WHERE element.kind='component') "
            "SELECT id,body FROM element WHERE kind='module' AND parent IN (SELECT id FROM scope)"
        )
        params: tuple[object, ...] = (parent,)
        module_total = db.execute("SELECT count(*) FROM (" + base + ")", params).fetchone()[0]
        if (parent == "system" or module_total > 36) and db.execute(
            "SELECT 1 FROM element WHERE parent=? AND kind='component' LIMIT 1", params
        ).fetchone():
            base = "SELECT id,body FROM element WHERE parent=? AND kind IN ('component','module')"
            overview = True
            limit = min(limit, 16)
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
    total = (
        module_total
        if module_total is not None and not overview
        else db.execute("SELECT count(*) FROM (" + base + ")", params).fetchone()[0]
    )
    rows = db.execute(
        base + " AND id>? ORDER BY id LIMIT ?", (*params, cursor, limit + 1)
    ).fetchall()
    items = [json.loads(row[1]) for row in rows[:limit]]
    _count_modules(db, items)
    groups = _groups(db, parent, items)
    edges, edge_total = _edges(db, items, groups)
    return {
        "parent": parent,
        "view": view,
        "module_overview": overview,
        "module_total": module_total,
        "items": items,
        "groups": groups,
        "edges": edges,
        "total": total,
        "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
        "edge_total": edge_total,
        "edges_truncated": edge_total > len(edges),
    }
