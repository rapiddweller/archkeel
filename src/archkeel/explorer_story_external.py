# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Expose source-backed external calls without claiming runtime binding."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .explorer_story_sql import _sqlite_direction


def _imports(
    db: Any,
    module: str,
    systems: dict[str, tuple[str, str]],
    location: Callable[[object], dict[str, Any] | None],
) -> set[str]:
    imported: set[str] = set()
    for record in db.execute(
        "SELECT body FROM relation WHERE kind='import' AND source=? ORDER BY id LIMIT 200",
        (module,),
    ):
        data = json.loads(record[0])
        target = data.get("target")
        if data.get("resolution") != "external" or not isinstance(target, str):
            continue
        package = target.split(".", 1)[0]
        if package not in systems:
            continue
        evidence = [location(site.get("reference")) for site in data.get("evidence", [])]
        if evidence and all(evidence):
            imported.add(package)
    return imported


_SYSTEMS = {
    "sqlite3": ("relational_database", "SQLite"),
    "redis": ("redis", "Redis"),
    "psycopg": ("relational_database", "PostgreSQL"),
    "psycopg2": ("relational_database", "PostgreSQL"),
    "asyncpg": ("relational_database", "PostgreSQL"),
}
_ENTRIES = {
    "sqlite3": {"sqlite3.connect"},
    "redis": {"redis.Redis", "redis.StrictRedis", "redis.from_url"},
    "psycopg": {"psycopg.connect"},
    "psycopg2": {"psycopg2.connect"},
    "asyncpg": {"asyncpg.connect", "asyncpg.create_pool"},
}


def _external(
    db: Any,
    root: Path,
    module: str | None,
    function: str | None,
    claimed: list[dict[str, str]],
    definition: dict[str, Any] | None,
    location: Callable[[object], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        dict(
            item,
            label=item["system"],
            status="claim",
            evidence=[],
            reason="Author claim; service use is not verified.",
        )
        for item in claimed
    ]
    if module is None or function is None:
        return rows
    imported = _imports(db, module, _SYSTEMS, location)
    calls = [
        json.loads(record[0])
        for record in db.execute(
            "SELECT body FROM relation WHERE kind='call' AND source=? ORDER BY id LIMIT 200",
            (function,),
        )
    ]
    for call in calls:
        target = call.get("target")
        if (
            isinstance(target, str)
            and db.execute("SELECT 1 FROM element WHERE id=?", (target,)).fetchone()
        ):
            continue
        expression = call.get("expression")
        if not isinstance(expression, str) or "." not in expression:
            continue
        package = expression.split(".", 1)[0]
        if package not in imported or expression not in _ENTRIES[package]:
            continue
        evidence = [location(site.get("reference")) for site in call.get("evidence", [])]
        if evidence and all(evidence):
            system, label = _SYSTEMS[package]
            resolved = call.get("resolution") == "external"
            item = {
                "system": system,
                "label": label,
                "status": "observed_call",
                "binding": "external" if resolved else "unknown",
                "reason": (
                    "Static call and import; runtime target is not verified."
                    if resolved
                    else "The call and import are visible, but the binding is unresolved."
                ),
                "evidence": evidence,
            }
            if label == "SQLite" and definition is not None:
                item.update(_sqlite_direction(root, definition, calls, location))
            rows.append(item)
    return rows
