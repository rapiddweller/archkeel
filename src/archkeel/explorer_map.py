# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Project bounded maps from the same component and relation rows as the report."""

import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from .explorer_hierarchy import _groups, _module_hierarchy, _scoped_module_filter


def _map_search(db: sqlite3.Connection, text: str, parent: str) -> tuple[str, list[str]]:
    if parent:
        return _scoped_module_filter(db, parent, text)
    return "instr(lower(name),lower(?))>0", [text]


def _call_sites(visible: list[str]) -> str:
    marks = ",".join("?" for _ in visible)
    return (
        "WITH RECURSIVE descendants(visible,id,depth) AS ("
        f"SELECT id,id,0 FROM element WHERE id IN ({marks}) UNION ALL "
        "SELECT descendants.visible,element.id,descendants.depth+1 FROM descendants "
        "JOIN element ON element.parent=descendants.id WHERE descendants.depth<128), "
        "nearest AS (SELECT visible,id,row_number() OVER "
        "(PARTITION BY id ORDER BY depth,visible) AS rank FROM descendants), "
        "contributors AS (SELECT a.visible AS source,b.visible AS target,relation.id, "
        "relation.kind,1 AS weight FROM relation "
        "JOIN nearest a ON a.id=relation.source AND a.rank=1 "
        "JOIN nearest b ON b.id=relation.target AND b.rank=1 "
        "WHERE relation.target IS NOT NULL AND a.visible!=b.visible "
        "AND (relation.kind='source_call' OR (relation.kind='call' AND "
        "json_extract(relation.body,'$.resolution')='resolved')) "
        ") "
    )


def _projected_sites() -> str:
    return (
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
        "WHERE a.visible!=b.visible AND (relation.kind='source_call' OR ("
        "relation.kind IN ('import','call') "
        "AND json_extract(relation.body,'$.resolution')='resolved')) "
        "AND oi.source IS NULL), "
        "ranked AS (SELECT *,min(priority) OVER "
        "(PARTITION BY kind,source,target) AS best FROM sites), "
        "contributors AS (SELECT source,target,kind,id,weight FROM ranked WHERE priority=best) "
    )


def _projection(
    visible: list[str], aliases: list[tuple[str, str]] | None
) -> tuple[str, Sequence[str]]:
    if aliases is None:
        return _call_sites(visible), visible
    seeds = json.dumps([*((item, item) for item in visible), *aliases])
    return _projected_sites(), (seeds,)


def _projected(
    db: sqlite3.Connection,
    context: list[str | int],
    visible: list[str],
    aliases: list[tuple[str, str]] | None,
    focus: str = "",
) -> tuple[list[dict[str, Any]], int]:
    if not visible and not aliases:
        return [], 0
    sql, params = _projection(visible, aliases)
    where = " WHERE source=? OR target=?" if focus else ""
    rows = db.execute(
        sql + ",pairs AS (SELECT source,target,kind,sum(weight) AS count,min(id) AS evidence "
        "FROM contributors" + where + " GROUP BY source,target,kind) "
        "SELECT source,target,kind,count,evidence,count(*) OVER () FROM pairs "
        "ORDER BY source,target,kind LIMIT 500",
        (*params, focus, focus) if focus else params,
    ).fetchall()
    return [
        {
            "id": evidence,
            "relation_id": evidence,
            "aggregate_id": json.dumps([*context, source, target, kind], separators=(",", ":")),
            "source": source,
            "target": target,
            "count": count,
            "kind": kind,
            "resolution": "candidate" if kind == "source_call" else "resolved",
            "aggregate": True,
        }
        for source, target, kind, count, evidence, _ in rows
    ], rows[0][5] if rows else 0


def _visible(items: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[str]:
    return [
        item["id"]
        for item in [*items, *groups]
        if item["kind"] not in {"layer", "directory", "file_group"}
    ]


def _edges(
    db: sqlite3.Connection,
    context: list[str | int],
    items: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    aliases: list[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    visible = _visible(items, groups)
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
            calls, call_total = _projected(db, context, visible, None)
            edge_total += call_total
            edges = calls + edges[: max(0, 500 - len(calls))]
    if aliases is not None:
        projected, observed_total = _projected(db, context, visible, aliases)
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


def _open_targets(db: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    candidates = [item["id"] for item in items if item["kind"] in {"module", "class"}]
    parents = {
        row[0]
        for row in db.execute(
            "SELECT DISTINCT parent FROM element WHERE parent IN (SELECT value FROM json_each(?))",
            (json.dumps(candidates),),
        )
    }
    for item in items:
        if (
            item["kind"] in {"component", "directory", "layer", "file_group"}
            or item["id"] in parents
        ):
            item["open_target"] = "map"
        elif item.get("source"):
            item["open_target"] = "source"


def _map_layout(
    db: sqlite3.Connection, parent: str, view: str, cursor: str, limit: int
) -> tuple[dict[str, Any], list[tuple[str, str]] | None]:
    scope = db.execute("SELECT kind FROM element WHERE id=?", (parent,)).fetchone()
    if view == "hierarchy" and (scope is None or scope[0] == "component"):
        layout, aliases = _module_hierarchy(db, parent)
        return dict(layout), aliases
    if view not in {"components", "modules", "hierarchy"}:
        raise ValueError("invalid map view")
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
    return {
        "parent": parent,
        "view": view,
        "module_overview": overview,
        "module_total": module_total,
        "items": items,
        "groups": groups,
        "total": total,
        "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
    }, ([] if any(item["kind"] == "component" for item in items) else None)


def _focus_projection(
    layout: dict[str, Any], aliases: list[tuple[str, str]] | None, focus: str
) -> tuple[list[str], list[tuple[str, str]] | None]:
    items, groups = layout["items"], layout["groups"]
    visible = _visible(items, groups)
    if not focus:
        return visible, aliases
    if not any(group["id"] == focus for group in groups):
        raise ValueError("unknown map focus")
    by_parent: dict[str, list[str]] = {}
    for item in [*items, *groups]:
        by_parent.setdefault(item["parent"], []).append(item["id"])
    pending = [focus]
    inside: set[str] = set()
    while pending:
        item = pending.pop()
        if item not in inside:
            inside.add(item)
            pending.extend(by_parent.get(item, []))
    seeds = [(focus, item) for item in visible if item in inside]
    for group, member in aliases or []:
        seeds.append((focus if group in inside else group, member))
    return [item for item in visible if item not in inside], seeds


def _map_view(
    db: sqlite3.Connection, parent: str, view: str, cursor: str, limit: int, focus: str = ""
) -> dict[str, object]:
    """Read a page of hierarchy and its measured relationships."""
    layout, aliases = _map_layout(db, parent, view, cursor, limit)
    items, groups = layout["items"], layout["groups"]
    _open_targets(db, [*items, *groups])
    context: list[str | int] = [parent, view, cursor, limit, focus]
    if focus:
        visible, aliases = _focus_projection(layout, aliases, focus)
        edges, total = _projected(db, context, visible, aliases, focus)
    else:
        edges, total = _edges(db, context, items, groups, aliases)
    return layout | {"edges": edges, "edge_total": total, "edges_truncated": total > len(edges)}


def _aggregate_relations(
    db: sqlite3.Connection, aggregate: str, cursor: str, limit: int
) -> dict[str, object]:
    """Read the indexed relations that contribute to one directed map edge."""
    token = json.loads(aggregate)
    if not isinstance(token, list) or len(token) != 8 or type(token[3]) is not int:
        raise ValueError("invalid aggregate")
    parent, view, page, size, focus, source, target, kind = token
    if not all(isinstance(item, str) for item in (parent, view, page, focus, source, target, kind)):
        raise ValueError("invalid aggregate")
    if not 1 <= size <= 200 or kind not in {"call", "import", "source_call"}:
        raise ValueError("invalid aggregate")
    layout, aliases = _map_layout(db, parent, view, page, size)
    visible, aliases = _focus_projection(layout, aliases, focus)
    if focus and focus not in {source, target}:
        raise ValueError("invalid aggregate")
    sql, params = _projection(visible, aliases)
    rows = db.execute(
        sql + ",chosen AS MATERIALIZED (SELECT id,weight FROM contributors "
        "WHERE source=? AND target=? AND kind=?), "
        "stats AS (SELECT count(*) AS total,coalesce(sum(weight),0) AS count FROM chosen), "
        "page AS (SELECT id FROM chosen WHERE id>? ORDER BY id LIMIT ?) "
        "SELECT relation.body,stats.total,stats.count FROM stats "
        "LEFT JOIN page ON true LEFT JOIN relation ON relation.id=page.id ORDER BY page.id",
        (*params, source, target, kind, cursor, limit + 1),
    ).fetchall()
    items = [json.loads(row[0]) for row in rows if row[0] is not None]
    return {
        "items": items[:limit],
        "total": rows[0][1],
        "count": rows[0][2],
        "next_cursor": items[limit - 1]["id"] if len(items) > limit else None,
    }
