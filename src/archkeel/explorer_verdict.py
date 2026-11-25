# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep the verdict rows of the core frame in a snapshot and answer three bounded questions.

The rows are a copy of what the core decided. Nothing here decides a verdict (AD-1084).
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .explorer_source import Row, _number, _source_path, _text

_ANSWER_BYTES = 16 * 1024
_TEXT_CHARS = 300
_NO_VERDICT = "this snapshot holds no contract verdict; scan again with a contract"
_SCHEMA = (
    "CREATE TABLE verdict(status TEXT,exit_code INTEGER,rules_violated INTEGER,unknown INTEGER,"
    "contract_digest TEXT)",
    "CREATE TABLE rationale(rule TEXT PRIMARY KEY,text TEXT)",
    "CREATE TABLE violation(id TEXT PRIMARY KEY,rule TEXT,body TEXT)",
    "CREATE INDEX violation_rule ON violation(rule,id)",
    "CREATE TABLE gap(id TEXT PRIMARY KEY,kind TEXT,body TEXT)",
    "CREATE INDEX gap_kind ON gap(kind,id)",
    "CREATE TABLE source(path TEXT PRIMARY KEY,digest TEXT)",
)
_Shape = Callable[[list[Row]], Row]


class Basis(StrEnum):
    """How sure ArchKeel is about one row. Nothing is inferred."""

    PROVEN = "proven"
    # The row rests on a possible import that the contract declares, not on an observed one.
    DECLARED = "declared"
    UNKNOWN = "unknown"


class Freshness(StrEnum):
    """Whether each file that the scan read still has its scan digest."""

    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation of a rule, as the core reported it."""

    rule: str
    subject: str
    at: str | None
    basis: Basis
    components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Unknown:
    """One part that the core did not decide. A gap is never proven."""

    kind: str
    subject: str
    reason: str
    at: str | None


@dataclass(frozen=True, slots=True)
class VerdictRows:
    """The verdict of one scan, ready to store."""

    status: str
    exit_code: int
    rules_violated: int
    unknown_rules: int
    contract_digest: str | None
    rationales: Mapping[str, str]
    findings: tuple[Finding, ...]
    unknowns: tuple[Unknown, ...]
    # Digest of each file that the scan assessed, to tell later whether the verdict is stale.
    sources: Mapping[str, str]


def _located(at: str | None) -> Row:
    return {} if at is None else {"at": at}


def store(connection: sqlite3.Connection, rows: VerdictRows | None) -> None:
    """Create the tables. A scan without a contract verdict leaves them empty."""
    for statement in _SCHEMA:
        connection.execute(statement)
    if rows is None:
        return
    connection.execute(
        "INSERT INTO verdict VALUES (?,?,?,?,?)",
        (
            rows.status,
            rows.exit_code,
            rows.rules_violated,
            rows.unknown_rules,
            rows.contract_digest,
        ),
    )
    connection.executemany("INSERT INTO rationale VALUES (?,?)", sorted(rows.rationales.items()))
    connection.executemany("INSERT INTO source VALUES (?,?)", sorted(rows.sources.items()))
    # Numbered after sorting, so the id order is the row order and equal input gives equal bytes.
    for number, finding in enumerate(
        sorted(rows.findings, key=lambda row: (row.rule, row.subject, row.at or ""))
    ):
        body = {
            "rule": finding.rule,
            "basis": finding.basis,
            "subject": finding.subject,
            **_located(finding.at),
            "components": finding.components,
        }
        connection.execute(
            "INSERT INTO violation VALUES (?,?,?)",
            (f"{number:08d}", finding.rule, json.dumps(body)),
        )
    for number, unknown in enumerate(
        sorted(rows.unknowns, key=lambda row: (row.kind, row.subject, row.at or "", row.reason))
    ):
        body = {
            "kind": unknown.kind,
            "basis": Basis.UNKNOWN,
            "subject": unknown.subject,
            "reason": unknown.reason,
            **_located(unknown.at),
            # The snapshot scan reads no baseline file, so no baseline accepts a gap here.
            "accepted_by_baseline": False,
        }
        connection.execute(
            "INSERT INTO gap VALUES (?,?,?)", (f"{number:08d}", unknown.kind, json.dumps(body))
        )


def _untrusted(text: str) -> Row:
    return {"text": text[:_TEXT_CHARS], "untrusted": True}


def _freshness(db: sqlite3.Connection, root: Path) -> Freshness:
    for name, digest in db.execute("SELECT path,digest FROM source ORDER BY path"):
        try:
            with _source_path(root, name).open("rb") as stream:
                current = hashlib.file_digest(stream, "sha256").hexdigest()
        except (OSError, ValueError):
            return Freshness.STALE
        if current != digest:
            return Freshness.STALE
    return Freshness.FRESH


def _count(
    db: sqlite3.Connection, table: str, where: str = "1=1", params: tuple[str, ...] = ()
) -> int:
    return int(db.execute(f"SELECT count(*) FROM {table} WHERE {where}", params).fetchone()[0])


def _stored(db: sqlite3.Connection) -> tuple[str, int, int, int, str | None] | None:
    # A snapshot of an older format has no table, and an observed scan has no row.
    if db.execute("SELECT 1 FROM sqlite_schema WHERE name='verdict'").fetchone() is None:
        return None
    row = db.execute(
        "SELECT status,exit_code,rules_violated,unknown,contract_digest FROM verdict"
    ).fetchone()
    return None if row is None else tuple(row)


def _verdict(db: sqlite3.Connection, root: Path, _args: Row, snapshot: str) -> Row:
    row = _stored(db)
    if row is None:
        return {"snapshot": snapshot, "status": None, "basis": Basis.UNKNOWN, "reason": _NO_VERDICT}
    status, exit_code, rules_violated, unknown, digest = row
    return {
        "status": status,
        "exit_code": exit_code,
        "violations": _count(db, "violation"),
        "rules_violated": rules_violated,
        "unknown": unknown,
        "gaps": _count(db, "gap"),
        "contract_digest": digest,
        "freshness": _freshness(db, root),
        "snapshot": snapshot,
    }


def _page(
    db: sqlite3.Connection,
    root: Path,
    args: Row,
    snapshot: str,
    table: str,
    where: tuple[str, tuple[str, ...]],
    shape: _Shape,
) -> Row:
    """One bounded page. Rows beyond the limit or the byte budget are cut and counted."""
    if _stored(db) is None:
        raise ValueError(_NO_VERDICT)
    condition, params = where
    limit = _number(args, "limit", 25, 100)
    cursor = _text(args, "cursor", "")
    fetched = db.execute(
        f"SELECT id,body FROM {table} WHERE {condition} AND id>? ORDER BY id LIMIT ?",
        (*params, cursor, limit + 1),
    ).fetchall()
    total = _count(db, table, condition, params)
    freshness = _freshness(db, root)

    def page(shown: int) -> Row:
        cut = shown < len(fetched)
        return {
            "snapshot": snapshot,
            "freshness": freshness,
            **shape([json.loads(body) for _, body in fetched[:shown]]),
            "total": total,
            "truncated": cut,
            "next_cursor": fetched[shown - 1][0] if cut and shown else None,
        }

    shown = min(limit, len(fetched))
    result = page(shown)
    while shown and len(json.dumps(result).encode()) > _ANSWER_BYTES:
        shown -= 1
        result = page(shown)
    return result


def _findings(db: sqlite3.Connection, root: Path, args: Row, snapshot: str) -> Row:
    condition, params = "1=1", tuple[str, ...]()
    if rule := _text(args, "rule", ""):
        condition, params = condition + " AND rule=?", (*params, rule)
    if component := _text(args, "component", ""):
        condition += (
            " AND EXISTS (SELECT 1 FROM json_each(violation.body,'$.components') WHERE value=?)"
        )
        params = (*params, component)

    def shape(items: list[Row]) -> Row:
        rules = sorted({str(item["rule"]) for item in items})
        marks = ",".join("?" * len(rules))
        text = dict(db.execute(f"SELECT rule,text FROM rationale WHERE rule IN ({marks})", rules))
        return {
            "items": [{key: item[key] for key in item if key != "components"} for item in items],
            "rationales": {rule: _untrusted(text[rule]) for rule in rules if rule in text},
        }

    return _page(db, root, args, snapshot, "violation", (condition, params), shape)


def _unknowns(db: sqlite3.Connection, root: Path, args: Row, snapshot: str) -> Row:
    condition, params = "1=1", tuple[str, ...]()
    if kind := _text(args, "kind", ""):
        condition, params = condition + " AND kind=?", (kind,)

    def shape(items: list[Row]) -> Row:
        return {"items": [item | {"reason": _untrusted(str(item["reason"]))} for item in items]}

    return _page(db, root, args, snapshot, "gap", (condition, params), shape)


ANSWERS: Mapping[str, Callable[[sqlite3.Connection, Path, Row, str], Row]] = {
    "verdict": _verdict,
    "findings": _findings,
    "unknowns": _unknowns,
}
