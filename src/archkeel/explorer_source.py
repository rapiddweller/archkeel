# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read a bounded source excerpt and verify it against the snapshot."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

Row = dict[str, object]


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
