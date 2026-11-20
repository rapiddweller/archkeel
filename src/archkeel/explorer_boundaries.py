# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find bounded, explicitly marked candidate process and HTTP boundaries."""

import ast
import hashlib
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_CALL = re.compile(
    r"\b(?:axios|comHandler(?:Datamimic\w+)?)\.(get|post|put|patch|delete)\s*\(\s*([^,)]*)", re.I
)
_ROUTE = re.compile(r"^\s*@\w+\.(get|post|put|patch|delete)\(\s*(['\"])(/[^'\"]*)\2", re.I)
_LITERAL = re.compile(r"^(['\"])(/[^'\"]*)\1$")


def _row(
    source: str,
    target: str | None,
    kind: str,
    evidence: list[dict[str, Any]],
    reason: str,
    column: int = 0,
) -> dict[str, Any]:
    identity = repr((source, target, kind, evidence, column)).encode()
    return {
        "id": "boundary:" + hashlib.sha256(identity).hexdigest(),
        "source": source,
        "target": target,
        "kind": kind,
        "resolution": "candidate" if target else "open",
        "evidence": evidence,
        "reason": reason,
    }


def _files(root: Path, modules: list[dict[str, Any]]) -> Iterator[tuple[str, str, str]]:
    for module in modules[:10000]:
        relative = Path(module["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        path = root / relative
        try:
            if path.resolve() != root.resolve() / relative or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        yield module["name"], relative.as_posix(), text


def boundary_rows(root: Path, modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find sites in supplied modules; candidates do not assert a runtime connection."""
    routes: dict[tuple[str, str], list[tuple[str, str, int]]] = {}
    for name, path, text in _files(root, modules):
        if path.endswith(".py"):
            for number, line in enumerate(text.splitlines(), 1):
                match = _ROUTE.match(line)
                if match:
                    routes.setdefault((match[1].lower(), match[3]), []).append((name, path, number))
    rows = []
    for name, path, text in _files(root, modules):
        if path.endswith(".py"):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                ):
                    rows.append(
                        _row(
                            name,
                            None,
                            "process",
                            [{"path": path, "line": node.lineno}],
                            "Process target is not resolved.",
                            node.col_offset,
                        )
                    )
        elif path.endswith((".ts", ".tsx", ".js", ".jsx")):
            for number, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith(("//", "*")):
                    continue
                for match in _CALL.finditer(line):
                    literal = _LITERAL.fullmatch(match[2].strip())
                    matches = routes.get((match[1].lower(), literal[2]), []) if literal else []
                    evidence = [{"path": path, "line": number}]
                    if len(matches) == 1:
                        target, route_path, route_line = matches[0]
                        rows.append(
                            _row(
                                name,
                                target,
                                "http",
                                evidence + [{"path": route_path, "line": route_line}],
                                "Method and path match; runtime routing is unverified.",
                                match.start(),
                            )
                        )
                    else:
                        rows.append(
                            _row(
                                name,
                                None,
                                "http",
                                evidence,
                                "HTTP target is dynamic, missing, or ambiguous.",
                                match.start(),
                            )
                        )
    return rows
