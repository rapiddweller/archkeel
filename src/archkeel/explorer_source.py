# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read a bounded source excerpt and verify it against the snapshot."""

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

Row = dict[str, object]
_SCIP_STATUSES = frozenset({"local_resolved", "external_std", "external_dep", "unresolved"})
_SCIP_PROVENANCES = frozenset({"ast_exact", "scip_verified"})


def _source_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("source outside scan root")
    path = root / relative
    if path.resolve() != root.resolve() / relative or not path.is_file():
        raise ValueError("source unavailable")
    return path


def _number(args: Row, name: str, default: int, maximum: int) -> int:
    value = args.get(name, default)
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 10:
        value = int(value)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _source(db: sqlite3.Connection, root: Path, args: Row) -> Row:
    row = db.execute(
        "SELECT path,line,digest FROM location WHERE id=?", (_text(args, "reference"),)
    ).fetchone()
    if row is None:
        raise ValueError("unknown source reference")
    name, anchor, digest = row
    start = _number(args, "start", max(1, anchor - 3), 2**31 - 1)
    count = _number(args, "limit", 24, 120)
    if not digest:
        raise ValueError("source unavailable at scan time")
    hasher = hashlib.sha256()
    lines = []
    index = 1
    fragment = bytearray()
    with _source_path(root, name).open("rb") as stream:
        while chunk := stream.readline(65536):
            hasher.update(chunk)
            if start <= index < start + count:
                fragment.extend(chunk[: 4096 - len(fragment)])
            if chunk.endswith(b"\n"):
                if start <= index < start + count:
                    lines.append(fragment.decode("utf-8", errors="replace").rstrip("\r\n"))
                fragment.clear()
                index += 1
        if fragment:
            lines.append(fragment.decode("utf-8", errors="replace"))
    if hasher.hexdigest() != digest:
        raise ValueError("source changed since scan")
    return {"path": name, "start": start, "line": anchor, "lines": lines}


def _text(args: Row, name: str, default: str | None = None) -> str:
    value = args.get(name, default)
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(f"invalid {name}")
    return value


def _import_evidence(db: sqlite3.Connection, relation: Row) -> Iterator[Row]:
    for row in db.execute(
        "WITH inputs AS ("
        "SELECT id FROM element WHERE id=? OR (kind='module' AND parent=?)"
        "), outputs AS ("
        "SELECT id FROM element WHERE id=? OR (kind='module' AND parent=?)"
        ") "
        "SELECT location.value FROM relation JOIN json_each(relation.body, '$.evidence') location "
        "WHERE relation.source IN (SELECT id FROM inputs) "
        "AND relation.target IN (SELECT id FROM outputs) "
        "AND relation.kind='import_site' AND json_extract(relation.body,'$.resolution')='local' "
        "AND json_extract(relation.body,'$.evidence_class')='FACT' "
        "ORDER BY json_extract(location.value,'$.path'),json_extract(location.value,'$.line')",
        (relation["source"], relation["source"], relation["target"], relation["target"]),
    ):
        yield json.loads(row[0])


def _relation_evidence(db: sqlite3.Connection, args: Row) -> Row:
    row = db.execute("SELECT body FROM relation WHERE id=?", (_text(args, "relation"),)).fetchone()
    if not row:
        raise ValueError("unknown relation")
    body = json.loads(row[0])
    items = body["evidence"]
    total = body.get("evidence_total", len(items))
    if body["kind"] == "import" and body["resolution"] == "resolved" and total > len(items):
        locations = {item["reference"]: item for item in items}
        for item in _import_evidence(db, body):
            locations.setdefault(item["reference"], item)
        items = sorted(locations.values(), key=lambda item: (item["path"], item["line"]))
    cursor = _text(args, "cursor", "")
    if cursor and not (cursor.isascii() and cursor.isdecimal()):
        raise ValueError("invalid evidence cursor")
    offset = int(cursor or "0")
    limit = _number(args, "limit", 200, 200)
    total = len(items)
    evidence_total = max(total, body.get("evidence_total", total))
    return {
        "items": items[offset : offset + limit],
        "relation": dict(body, evidence=items[offset : offset + limit]),
        "total": total,
        "evidence_total": evidence_total,
        "evidence_truncated": evidence_total > total,
        "next_cursor": str(offset + limit) if offset + limit < total else None,
    }


def _scip_artifacts(db: sqlite3.Connection) -> list[Row]:
    columns = [row[1] for row in db.execute("PRAGMA table_info(scip_artifact)").fetchall()]
    if not columns:
        return []
    if "language" in columns:
        rows = db.execute(
            "SELECT language, index_sha256, manifest_sha256 "
            "FROM scip_artifact ORDER BY language, index_sha256"
        ).fetchall()
        return [
            {"language": lang, "index_sha256": digest, "manifest_sha256": manifest}
            for lang, digest, manifest in rows
        ]
    rows = db.execute(
        "SELECT index_sha256, manifest_sha256 FROM scip_artifact ORDER BY index_sha256"
    ).fetchall()
    return [
        {"language": "rust", "index_sha256": digest, "manifest_sha256": manifest}
        for digest, manifest in rows
    ]


def _resolution_row(row: tuple[object, ...]) -> Row:
    (
        call_id,
        language,
        status,
        provenance,
        reason,
        target_id,
        dispatch_kind,
        evidence_id,
        decl_path,
        decl_line,
        crate_name,
        crate_version,
        symbol_path,
        ref_path,
        start_line,
        start_col,
        end_line,
        end_col,
    ) = row
    ref = (
        {
            "path": ref_path,
            "start_line": start_line,
            "start_column": start_col,
            "end_line": end_line,
            "end_column": end_col,
        }
        if ref_path is not None
        else None
    )
    return {
        "call_id": call_id,
        "relation_id": f"relation:call:{call_id}",
        "language": language,
        "status": status,
        "provenance": provenance,
        "reason": reason,
        "canonical_target_definition_id": target_id,
        "target_element_id": f"definition:{target_id}" if isinstance(target_id, str) else None,
        "dispatch_kind": dispatch_kind,
        "evidence_id": evidence_id,
        "declaration_path": decl_path,
        "declaration_line": decl_line,
        "crate_name": crate_name,
        "crate_version": crate_version,
        "symbol_path": symbol_path,
        "reference": ref,
    }


def _call_resolution(
    db: sqlite3.Connection,
    args: Row,
    call_scope: Callable[[sqlite3.Connection, str], tuple[str, Sequence[object]]],
    element_status: Callable[[sqlite3.Connection, str], str],
) -> Row:
    """Serve bounded read-only SCIP call resolution rows without mutating native edges."""
    present = db.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='call_resolution'"
    ).fetchone()
    if not present:
        return {
            "available": False,
            "artifacts": [],
            "counts": [],
            "items": [],
            "next_cursor": None,
        }
    element = _text(args, "element", "")
    status = _text(args, "status", "")
    provenance = _text(args, "provenance", "")
    call_id = _text(args, "call_id", "")
    if status and status not in _SCIP_STATUSES:
        raise ValueError("invalid call_resolution status")
    if provenance and provenance not in _SCIP_PROVENANCES:
        raise ValueError("invalid call_resolution provenance")
    limit = _number(args, "limit", 50, 200)
    cursor = _text(args, "cursor", "")

    join = ""
    scope_where = "1=1"
    scope_params: list[object] = []
    extra: Row = {}
    if element:
        elem_state = element_status(db, element)
        extra["element_status"] = elem_state
        if elem_state == "known":
            join = "JOIN relation ON relation.id = 'relation:call:' || cr.call_id"
            scope_where, scoped = call_scope(db, element)
            scope_params = list(scoped)
        else:
            scope_where = "0"

    clauses = [scope_where]
    params: list[object] = list(scope_params)
    if status:
        clauses.append("cr.status=?")
        params.append(status)
    if provenance:
        clauses.append("cr.provenance=?")
        params.append(provenance)
    if call_id:
        clauses.append("cr.call_id=?")
        params.append(call_id)
    filter_where = " AND ".join(clauses)
    has_filter = bool(element or status or provenance or call_id)
    if has_filter:
        count_rows = db.execute(
            f"SELECT cr.language, cr.status, cr.provenance, cr.reason, count(*) "
            f"FROM call_resolution cr {join} WHERE {filter_where} "
            f"GROUP BY cr.language, cr.status, cr.provenance, cr.reason "
            f"ORDER BY cr.language, cr.status, cr.provenance, cr.reason",
            params,
        ).fetchall()
    else:
        count_rows = db.execute(
            "SELECT language, status, provenance, reason, count FROM call_resolution_count"
        ).fetchall()
    counts = [
        {
            "language": lang,
            "status": st,
            "provenance": prov,
            "reason": rsn,
            "count": cnt,
        }
        for lang, st, prov, rsn, cnt in count_rows
    ]

    page_clauses = list(clauses)
    page_params = list(params)
    if cursor:
        page_clauses.append("cr.call_id>?")
        page_params.append(cursor)
    where = " AND ".join(page_clauses)
    rows = db.execute(
        f"SELECT cr.call_id, cr.language, cr.status, cr.provenance, cr.reason, "
        f"cr.canonical_target_definition_id, cr.dispatch_kind, cr.evidence_id, "
        f"cr.declaration_path, cr.declaration_line, cr.crate_name, cr.crate_version, "
        f"cr.symbol_path, cr.reference_path, cr.reference_start_line, "
        f"cr.reference_start_column, cr.reference_end_line, cr.reference_end_column "
        f"FROM call_resolution cr {join} WHERE {where} ORDER BY cr.call_id LIMIT ?",
        (*page_params, limit + 1),
    ).fetchall()
    items = [_resolution_row(r) for r in rows[:limit]]
    return extra | {
        "available": True,
        "artifacts": _scip_artifacts(db),
        "counts": counts,
        "items": items,
        "next_cursor": str(rows[limit - 1][0]) if len(rows) > limit else None,
    }
