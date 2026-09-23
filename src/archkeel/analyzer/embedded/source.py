# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Parsed-module primitives shared by the scanner and its context collector."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from archkeel.ir.model import EvidenceClass, stable_id

from .records import RawEvidence, RawRecord, classified

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def location(node: ast.AST) -> tuple[int, int, int]:
    if not isinstance(node, ast.stmt | ast.expr | ast.excepthandler | ast.arg | ast.keyword):
        return 1, 1, 0
    line = max(node.lineno, 1)
    return line, node.end_lineno or line, node.col_offset


def own_scope(node: FunctionNode) -> Iterator[ast.AST]:
    """Walk a function's body, stopping at a nested function, lambda or class of its own.

    The unused-binding collector and the call collector both need this exact boundary: a
    name a nested scope binds or reads is not a fact about the outer function's own body,
    so both read it from here instead of each running its own version of the same walk.
    Nodes come in source order, so a receiver typed from an earlier binding is known by the
    time a later call result is typed from it (AD-40).
    """
    stack: list[ast.AST] = list(reversed(node.body))
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))


@dataclass(frozen=True)
class AliasBinding:
    target: str
    kind: str
    imported_name: str | None = None


class ScannedModule(Protocol):
    """The plain facts the shared package and module records read of any scanned module.

    Narrower than `ParsedModule` on purpose: a profile without a Python AST (AD-97) builds the
    same records from these five fields instead of fabricating a tree it does not have.
    """

    @property
    def rel_path(self) -> str: ...

    @property
    def module(self) -> str: ...

    @property
    def package(self) -> str: ...

    @property
    def all_exports(self) -> AbstractSet[str]: ...

    @property
    def compatibility_logic_free(self) -> bool: ...


@dataclass
class ParsedModule:
    path: Path
    rel_path: str
    module: str
    package: str
    source: str
    source_bytes: bytes
    lines: list[str]
    tree: ast.Module
    aliases: dict[str, AliasBinding] = field(default_factory=dict)
    all_exports: set[str] = field(default_factory=set)
    compatibility_logic_free: bool = False


def _excerpt(module: ParsedModule, node: ast.AST) -> str:
    start, _, _ = location(node)
    return module.lines[start - 1].rstrip() if start <= len(module.lines) else ""


def add_evidence(evidence: dict[str, RawEvidence], module: ParsedModule, node: ast.AST) -> str:
    line, end_line, column = location(node)
    return record_evidence(
        evidence, module.rel_path, (line, end_line, column), _excerpt(module, node)
    )


def record_evidence(
    evidence: dict[str, RawEvidence],
    rel_path: str,
    position: tuple[int, int, int],
    excerpt: str,
) -> str:
    """File one source location as evidence; shared by every profile's reader (AD-97)."""
    line, end_line, column = position
    # One source location is one evidence owner even when several observations
    # (for example a call and a dynamic-typing signal) refer to it.
    evidence_id = stable_id("EVD", rel_path, line, end_line, column)
    evidence[evidence_id] = {
        "id": evidence_id,
        "file": rel_path,
        "line": line,
        "end_line": end_line,
        "column": column,
        "excerpt": excerpt,
    }
    return evidence_id


def annotation_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except ValueError:
        return None


def decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        try:
            names.append(ast.unparse(target))
        except ValueError:
            continue
    return sorted(names)


def body_is_empty(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when nothing but a docstring, `pass` or `...` stands in the body.

    Collectors are peers that never import each other (AD-25), so the predicate the binding
    collector and the construct collector both need lives here, where both may reach it.
    """
    return all(
        isinstance(statement, ast.Pass)
        or (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
        for statement in node.body
    )


def module_for(path: Path, *, root: Path, namespace: str) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    prefix = namespace.split(".")
    for index in range(len(parts) - len(prefix) + 1):
        if parts[index : index + len(prefix)] == prefix:
            return ".".join(parts[index:])
    raise ValueError(f"source path does not contain configured namespace {namespace!r}")


def package_for(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else module


@dataclass(frozen=True)
class ParsedSources:
    """Modules parsed from one scan pass, their coverage failures and source digest."""

    modules: list[ParsedModule]
    failures: list[RawRecord]
    files_read: int
    source_digest: str


def parse_sources(paths: Sequence[Path], *, root: Path, namespace: str) -> ParsedSources:
    """Read, digest and parse each candidate path into a module or a coverage failure."""
    modules: list[ParsedModule] = []
    failures: list[RawRecord] = []
    read_count = 0
    digest = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
            read_count += 1
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
            source = raw.decode("utf-8")
            tree = ast.parse(source, filename=rel)
            module_name = module_for(path, root=root, namespace=namespace)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            if isinstance(exc, SyntaxError):
                line, message = exc.lineno or 1, exc.msg
            elif isinstance(exc, OSError):
                line, message = 1, exc.strerror or exc.__class__.__name__
            else:
                line, message = 1, exc.__class__.__name__
            failure_id = stable_id("COVERAGE", rel, line, exc.__class__.__name__, message)
            failures.append(
                classified(
                    item_id=failure_id,
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind=exc.__class__.__name__,
                    title=f"{rel}:{line} could not be analyzed",
                    subjects=[rel],
                    data={"file": rel, "line": line, "message": str(message)},
                )
            )
            continue
        modules.append(
            ParsedModule(
                path=path,
                rel_path=rel,
                module=module_name,
                package=package_for(module_name),
                source=source,
                source_bytes=raw,
                lines=source.splitlines(),
                tree=tree,
            )
        )
    return ParsedSources(
        modules=modules,
        failures=failures,
        files_read=read_count,
        source_digest=digest.hexdigest(),
    )
