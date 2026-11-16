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
import os
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
    """The module identity of a TypeScript path segment: a character other than an ASCII letter
    or digit is `_x<hex>_`, as the collector writes it (`.` is `_x2e_`, `_` is `_x5f_`)."""
    return "".join(c if c.isascii() and c.isalnum() else f"_x{ord(c):x}_" for c in segment)


def _packages(folder: Path) -> list[Path]:
    """The subfolders of `folder` that hold Python code at any depth (a folder without
    `__init__.py` is a namespace package, and the scan reads its modules too)."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_dir() and path.name not in _IGNORED and _has_python(path)
    )


def _has_python(folder: Path) -> bool:
    for _, names, files in os.walk(folder):
        names[:] = [name for name in names if name not in _IGNORED]
        if any(file.endswith(".py") for file in files):
            return True
    return False


def _members(root: Path, patterns: list[str], marker: str) -> list[Path]:
    """The workspace members: each folder that a pattern names (one `*` level) and that holds
    the marker file."""
    found: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_dir() and (path / marker).is_file() and path.name not in _IGNORED:
                found.add(path)
    return sorted(found)


def python_layouts(root: Path, folder: Path | None = None) -> list[Layout]:
    """The Python scans of a project folder: one component for each subpackage of a top-level
    package. A module name is the namespace and the path below the scan root, and the namespace
    must be the name of that root, so a scan has one root folder.

    Below `src` the folders that hold Python give one scan with one component each, or one scan
    of the only folder. In a folder without `src` each top-level package (with `__init__.py`) is
    its own scan. `root` is the repository; `folder` is the project folder below it."""
    folder = folder or root
    src = (folder / "src").is_dir()
    base = folder / "src" if src else folder
    found = (
        _packages(base) if src else [p for p in _packages(base) if (p / "__init__.py").is_file()]
    )
    if not found:
        where = base.relative_to(root).as_posix()
        raise _refuse(f"no top-level Python package (a folder with __init__.py) in {where}")
    note = _python_note(folder)
    if src and len(found) > 1:
        return [_python_scan(root, base, [p.name for p in found], note)]
    return [_python_single(root, package, note) for package in found]


def _python_single(root: Path, package: Path, note: str) -> Layout:
    """The scan of one package: a component for each folder in it that holds Python."""
    namespace = package.name
    parts = [Part(p.name, (f"{namespace}.{p.name}",)) for p in _packages(package)]
    parts.append(Part("root", modules=_beside(namespace, package, {p.label for p in parts}, True)))
    return Layout(
        "python", namespace, (package.relative_to(root).as_posix(),), tuple(parts), note=note
    )


def _python_scan(root: Path, base: Path, names: list[str], note: str) -> Layout:
    """The scan of a folder (`src`) that holds several packages: a component for each."""
    namespace = _name(base.name)
    parts = [Part(name, (f"{namespace}.{name}",)) for name in names]
    own = (base / "__init__.py").is_file()  # a package `src/__init__.py` is a module of the scan
    parts.append(Part("root", modules=_beside(namespace, base, set(names), own)))
    return Layout(
        "python", namespace, (base.relative_to(root).as_posix(),), tuple(parts), note=note
    )


def _beside(namespace: str, folder: Path, taken: set[str], itself: bool) -> tuple[str, ...]:
    """The modules directly in `folder`: the package itself and each `.py` file beside the parts."""
    return tuple(
        ([namespace] if itself and (folder / "__init__.py").is_file() else [])
        + [
            f"{namespace}.{path.stem}"
            for path in sorted(folder.glob("*.py"))
            if path.stem != "__init__" and path.stem not in taken
        ]
    )


def _python_note(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "requires-python" in pyproject.read_text(encoding="utf-8"):
        return ""
    return (
        "pyproject.toml has no [project].requires-python: the core cannot prove the scan scope "
        "(UNKNOWN: scope_proof) until it does."
    )


def rust_layout(repo: Path, root: Path) -> Layout | None:
    """One component for each crate of the Cargo workspace in `root` (a folder of the repository
    `repo`); `None` without a workspace."""
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
            parts.append(Part(_name(found[1]), (f"{_name(root.name or repo.name)}.{name}",)))
    if len(parts) < 2:
        raise _refuse("the Cargo workspace names fewer than two crates with a [package] name")
    scan = root.relative_to(repo).as_posix()
    return Layout("rust", _name(root.name or repo.name), (scan,), tuple(parts))


def typescript_layout(repo: Path, root: Path) -> Layout | None:
    """One component for each member of the `workspaces` of the package.json in `root` (a folder
    of the repository `repo`); `None` without them."""
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
    namespace = _name(root.name or repo.name)
    parts, roots = [], []
    for member in members:
        relative = member.relative_to(repo)
        selector = ".".join([namespace, *(_escape(part) for part in relative.parts)])
        parts.append(Part(_name(member.name), (selector,)))
        roots.append(relative.as_posix())
    extra = _tsconfig(repo, root)
    return Layout("typescript", namespace, tuple(roots), tuple(parts), extra)


def _tsconfig(repo: Path, folder: Path) -> str:
    config = folder / "tsconfig.json"
    return f'tsconfig = "{config.relative_to(repo).as_posix()}"\n' if config.is_file() else ""
