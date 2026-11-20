# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read a bounded source excerpt and verify it against the snapshot."""

import hashlib
import sqlite3
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


def _reference(args: Row) -> str:
    value = args.get("reference")
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid reference")
    return value


def _number(args: Row, name: str, default: int, maximum: int) -> int:
    value = args.get(name, default)
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 10:
        value = int(value)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _source(db: sqlite3.Connection, root: Path, args: Row) -> Row:
    row = db.execute(
        "SELECT path,line,digest FROM location WHERE id=?", (_reference(args),)
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
