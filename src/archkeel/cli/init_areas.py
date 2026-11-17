# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the language areas of a repository and read the folder layout of each (AD-638, AD-660).

An area is one scan: a Python project, a Cargo workspace, a TypeScript project (or workspace) or
a Dart package. A repository with one area is drafted as one configuration (`init_draft`); a
repository with several is drafted as a system, one part for each area. Only the layout is read:
folders, `__init__.py`, `Cargo.toml`, `package.json` of workspace members and manifests. No source
file is read and no import is followed, so a layout gives no fact about the code. A layout that
this module cannot name soundly raises `NothingToDraft`.
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


def _python_layouts(root: Path, folder: Path | None = None) -> list[Layout]:
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


def _rust_layout(repo: Path, root: Path) -> Layout | None:
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


def _typescript_layout(repo: Path, root: Path) -> Layout | None:
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


_DEPTH: Final = 3
_CODE: Final = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
# The tsconfig of a project leaves its test files out; the scan then reports each as a gap that
# leaves the whole scope unknown. A draft leaves them out of the scan too (the result says so).
_TESTS: Final = "exclude_test_sources = true\n"


@dataclass(frozen=True)
class Area:
    """One language area: where it lies (a repository-relative folder) and what it drafts."""

    folder: str
    layout: Layout

    @property
    def label(self) -> str:
        """The part id before the names of several areas are made unique."""
        return _name(Path(self.folder).name) if self.folder != "." else self.layout.language


def _folders(repo: Path) -> list[Path]:
    """The folders of the repository down to `_DEPTH`, the root first, without hidden or
    generated folders."""
    found, level = [repo], [repo]
    for _ in range(_DEPTH):
        level = [
            child
            for folder in level
            for child in sorted(folder.iterdir())
            if child.is_dir() and child.name not in _IGNORED and not child.name.startswith(".")
        ]
        found += level
    return found


def _has_code(folder: Path) -> bool:
    for _, names, files in os.walk(folder):
        names[:] = [name for name in names if name not in _IGNORED]
        if any(Path(file).suffix in _CODE for file in files):
            return True
    return False


def _typescript_project(repo: Path, folder: Path) -> Layout:
    """One component for each folder of the project that holds code; the folders inside `src`
    count instead of `src` itself. The files beside them are the component `root`.

    The scan root is the project folder, not `src`: an import of a file beside `src` (a config or a
    host list) then resolves to a module of the scan. The identity of a module is the namespace
    and the repository-relative path, each segment escaped as the collector writes it."""
    namespace = _name(folder.name or repo.name)

    def code_dirs(parent: Path) -> list[Path]:
        return [
            path
            for path in sorted(parent.iterdir())
            if path.is_dir() and path.name not in _IGNORED and _has_code(path)
        ]

    def code_files(parent: Path) -> list[Path]:
        return [
            path for path in sorted(parent.iterdir()) if path.is_file() and path.suffix in _CODE
        ]

    units, own = [], code_files(folder)
    for path in code_dirs(folder):
        if path.name == "src":
            units += code_dirs(path)
            own += code_files(path)
        else:
            units.append(path)

    def selector(path: Path) -> str:
        return ".".join([namespace, *(_escape(p) for p in path.relative_to(repo).parts)])

    labels = [_name(path.name) for path in units]
    parts = [
        Part(
            label if labels.count(label) == 1 else _name(path.relative_to(folder).as_posix()),
            (selector(path),),
        )
        for label, path in zip(labels, units, strict=True)
    ]
    if own:
        parts.append(Part("root", modules=tuple(selector(path) for path in own)))
    if not parts:
        raise _refuse(f"no TypeScript or JavaScript code in {folder.relative_to(repo).as_posix()}")
    scan = folder.relative_to(repo).as_posix()
    return Layout("typescript", namespace, (scan,), tuple(parts), _tsconfig(repo, folder) + _TESTS)


def _dart_layout(repo: Path, folder: Path) -> Layout:
    """One component for each folder of `lib`; the files beside them are the component `root`.
    The namespace is the package name of pubspec.yaml; a module is the namespace and the path
    below `lib` without `.dart`."""
    text = (folder / "pubspec.yaml").read_text(encoding="utf-8")
    found = re.search(r"^name:\s*([A-Za-z0-9_]+)", text, re.M)
    lib = folder / "lib"
    if not found or not lib.is_dir():
        raise _refuse(f"{folder.relative_to(repo).as_posix()} has no pubspec name or no lib folder")
    namespace = found[1]
    parts = [
        Part(_name(path.name), (f"{namespace}.{path.name}",))
        for path in sorted(lib.iterdir())
        if path.is_dir() and any(path.rglob("*.dart"))
    ]
    modules = tuple(f"{namespace}.{path.stem}" for path in sorted(lib.glob("*.dart")))
    if modules:
        parts.append(Part("root", modules=modules))
    if not parts:
        raise _refuse(f"no Dart code in {lib.relative_to(repo).as_posix()}")
    return Layout("dart", namespace, (lib.relative_to(repo).as_posix(),), tuple(parts))


def _workspaces(folder: Path) -> bool:
    try:
        data = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("workspaces"))


def _layout_of(repo: Path, folder: Path) -> Layout | None:
    """The layout of a Cargo, package.json or pubspec manifest in `folder`, or `None`."""
    if (folder / "Cargo.toml").is_file() and (layout := _rust_layout(repo, folder)):
        return layout
    if (folder / "package.json").is_file():
        if _workspaces(folder):
            return _typescript_layout(repo, folder)
        if (folder / "tsconfig.json").is_file():
            return _typescript_project(repo, folder)
    if (folder / "pubspec.yaml").is_file():
        return _dart_layout(repo, folder)
    return None


def _discover(repo: Path) -> tuple[list[Area], str]:
    """The areas of `repo`, and the first reason that a folder gave none (for a refusal)."""
    areas: list[Area] = []
    claimed: list[Path] = []
    why = ""
    for folder in _folders(repo):
        if any(folder.is_relative_to(done) for done in claimed):
            continue
        relative = folder.relative_to(repo).as_posix() or "."
        try:
            layout = _layout_of(repo, folder)
            if layout is not None:
                areas.append(Area(relative, layout))
                # The members of a workspace are inside it; a project owns its folder.
                members = [repo / root for root in layout.roots] if _workspaces(folder) else []
                claimed += members or ([folder] if folder != repo else [])
        except NothingToDraft as error:
            why = why or str(error)
        # A Python project can share its folder with a Cargo or Node manifest.
        if folder == repo or any((folder / n).is_file() for n in ("pyproject.toml", "setup.py")):
            try:
                areas += [Area(layout.roots[0], layout) for layout in _python_layouts(repo, folder)]
            except NothingToDraft as error:
                why = why or str(error)
    return areas, why


def _detect(repo: Path) -> list[Area]:
    """The areas of the repository, or `NothingToDraft` when it has none."""
    areas, why = _discover(repo)
    if not areas:
        raise NothingToDraft(
            why
            or "no Python package, Cargo workspace, TypeScript project or Dart package found "
            "(folder layout and manifest only)."
        )
    return areas
