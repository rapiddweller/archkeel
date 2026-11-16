# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the folder layout of a project into the components that `init` drafts (AD-638).

Only the layout is read: folders, `__init__.py`, `Cargo.toml` and `package.json` of workspace
members. No source file is read and no import is followed, so a layout gives no fact about the
code. A layout that this module cannot name soundly raises `NothingToDraft`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DOCUMENT: Final = "https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md"
_IGNORED: Final = frozenset({".git", ".venv", "venv", "node_modules", "target", "build", "dist"})


class NothingToDraft(ValueError):
    """The layout names no components that the draft can state soundly."""


@dataclass(frozen=True)
class Part:
    """One drafted component: the label, the module selectors it owns."""

    label: str
    packages: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Layout:
    """The scan that a layout names: language, namespace, roots, components and an extra line."""

    language: str
    namespace: str
    roots: tuple[str, ...]
    parts: tuple[Part, ...]
    extra: str = ""
    note: str = ""


def _refuse(why: str) -> NothingToDraft:
    return NothingToDraft(f"{why}. Write archkeel.toml by hand: {DOCUMENT}")


def _name(text: str) -> str:
    """A label or namespace: letters, digits and underscore only."""
    return re.sub(r"\W+", "_", text).strip("_").lower() or "app"


def _escape(segment: str) -> str:
    """The module identity of a TypeScript path segment: a character outside [a-z0-9_] is
    `_x<hex>_`, as the collector names it."""
    return "".join(c if re.fullmatch(r"[a-z0-9_]", c) else f"_x{ord(c):x}_" for c in segment)


def _packages(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_dir() and path.name not in _IGNORED and (path / "__init__.py").is_file()
    )


def _members(root: Path, patterns: list[str], marker: str) -> list[Path]:
    """The workspace members: each folder that a pattern names (one `*` level) and that holds
    the marker file."""
    found: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_dir() and (path / marker).is_file() and path.name not in _IGNORED:
                found.add(path)
    return sorted(found)


def python_layout(root: Path) -> Layout:
    """One component for each subpackage of the one top-level package, or for each top-level
    package when there are several. The modules beside them are the component `root`."""
    base = root / "src" if (root / "src").is_dir() else root
    found = _packages(base)
    where = base.relative_to(root).as_posix()
    if not found:
        raise _refuse(f"no top-level Python package (a folder with __init__.py) in {where}")
    if len(found) == 1:
        package = found[0]
        scan = package.relative_to(root).as_posix()
        namespace, inside = package.name, _packages(package)
        owner, modules = package, [namespace]
        parts = [Part(p.name, (f"{namespace}.{p.name}",)) for p in inside]
    else:
        scan = base.relative_to(root).as_posix()
        namespace = _name(base.name if where != "." else root.name)
        owner, modules = base, []
        parts = [Part(p.name, (f"{namespace}.{p.name}",)) for p in found]
    taken = {part.label for part in parts}
    modules += [
        f"{namespace}.{path.stem}"
        for path in sorted(owner.glob("*.py"))
        if path.stem != "__init__" and path.stem not in taken
    ]
    parts.append(Part("root", modules=tuple(modules)))
    return Layout("python", namespace, (scan,), tuple(parts), note=_python_note(root))


def _python_note(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "requires-python" in pyproject.read_text(encoding="utf-8"):
        return ""
    return (
        "pyproject.toml has no [project].requires-python: the core cannot prove the scan scope "
        "(UNKNOWN: scope_proof) until it does."
    )


def rust_layout(root: Path) -> Layout | None:
    """One component for each crate of a Cargo workspace; `None` without a workspace."""
    manifest = root / "Cargo.toml"
    if not manifest.is_file():
        return None
    text = manifest.read_text(encoding="utf-8")
    if not re.search(r"^\[workspace\]", text, re.M):
        return None
    listed = re.search(r"^members\s*=\s*\[(.*?)\]", text, re.M | re.S)
    patterns = re.findall(r'"([^"]+)"', listed[1]) if listed else []
    parts: list[Part] = []
    for crate in _members(root, patterns, "Cargo.toml"):
        found = re.search(
            r'^\[package\].*?^name\s*=\s*"([^"]+)"',
            (crate / "Cargo.toml").read_text(encoding="utf-8"),
            re.M | re.S,
        )
        if found:
            name = found[1].replace("-", "_")
            parts.append(Part(_name(found[1]), (f"{_name(root.name)}.{name}",)))
    if len(parts) < 2:
        raise _refuse("the Cargo workspace names fewer than two crates with a [package] name")
    return Layout("rust", _name(root.name), (".",), tuple(parts))


def typescript_layout(root: Path) -> Layout | None:
    """One component for each member of the `workspaces` of package.json; `None` without them."""
    manifest = root / "package.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError as error:
        raise _refuse(f"package.json is not valid JSON ({error})") from None
    spaces = data.get("workspaces") if isinstance(data, dict) else None
    if isinstance(spaces, dict):
        spaces = spaces.get("packages")
    if not isinstance(spaces, list) or not spaces:
        return None
    members = _members(root, [s for s in spaces if isinstance(s, str)], "package.json")
    if len(members) < 2:
        raise _refuse("package.json workspaces name fewer than two packages")
    namespace = _name(root.name)
    parts, roots = [], []
    for member in members:
        relative = member.relative_to(root)
        selector = ".".join([namespace, *(_escape(part) for part in relative.parts)])
        parts.append(Part(_name(member.name), (selector,)))
        roots.append(relative.as_posix())
    extra = 'tsconfig = "tsconfig.json"\n' if (root / "tsconfig.json").is_file() else ""
    return Layout("typescript", namespace, tuple(roots), tuple(parts), extra)


def detect(root: Path) -> Layout:
    """The layout of `root`. Two languages at one root are refused: a run covers one language."""
    found = [layout for layout in (rust_layout(root), typescript_layout(root)) if layout]
    if len(found) > 1:
        raise _refuse(
            "the root holds a Cargo workspace and a package.json workspace, and a run covers one "
            "language"
        )
    return found[0] if found else python_layout(root)
