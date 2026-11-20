# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find source-backed SQL directions for an explicit SQLite connection."""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _connect(value: ast.expr) -> bool:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "closing"
    ):
        value = value.args[0] if len(value.args) == 1 else value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "connect"
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "sqlite3"
    )


def _aliases(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    bindings: dict[str, ast.Name] = {}
    for node in ast.walk(function):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name) and _connect(item.context_expr):
                    bindings[item.optional_vars.id] = item.optional_vars
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id in bindings and node is not bindings[node.id]:
                bindings.pop(node.id, None)
    return set(bindings)


def _sqlite_direction(
    root: Path,
    definition: dict[str, Any],
    calls: list[dict[str, Any]],
    location: Callable[[object], dict[str, Any] | None],
) -> dict[str, Any]:
    """Return only source-verified literal SQL on a direct connection in this function."""
    source = root / definition["path"]
    try:
        if source.stat().st_size > 2_000_000:
            return {}
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return {}
    functions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno == definition["line"]
    ]
    if len(functions) != 1 or location(definition["reference"]) is None:
        return {}
    function = functions[0]
    aliases = _aliases(function)
    sites = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (
            node.func.attr != "execute"
            or not isinstance(owner, ast.Name)
            or owner.id not in aliases
            or not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            continue
        sql = node.args[0].value.strip().split(None, 1)
        command = sql[0].upper() if sql else ""
        direction = (
            "reads"
            if command == "SELECT"
            else "writes"
            if command in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE"}
            else None
        )
        if direction:
            sites[(owner.id + ".execute", node.lineno)] = direction
    directions: set[str] = set()
    evidence = []
    for call in calls:
        expression = call.get("expression")
        if not isinstance(expression, str):
            continue
        for raw in call.get("evidence", []):
            site = location(raw.get("reference"))
            if site is None or site["path"] != definition["path"]:
                continue
            direction = sites.get((expression, site["line"]))
            if direction:
                directions.add(direction)
                evidence.append(site)
    if not evidence or location(definition["reference"]) is None:
        return {}
    return {
        "direction": "reads_writes" if len(directions) == 2 else next(iter(directions)),
        "direction_evidence": evidence,
        "direction_reason": "Literal SQL is visible here; runtime execution is not verified.",
    }
