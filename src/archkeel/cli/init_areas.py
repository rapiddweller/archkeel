# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the language areas of a repository by folder layout and manifest only (AD-660).

An area is one scan: a Python project, a Cargo workspace, a TypeScript project (or workspace) or
a Dart package. A repository with one area is drafted as one configuration (`init_draft`); a
repository with several is drafted as a system, one part for each area. No source file is read.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .init_layouts import (
    _IGNORED,
    Layout,
    NothingToDraft,
    Part,
    _escape,
    _name,
    _refuse,
    _tsconfig,
    python_layouts,
    rust_layout,
    typescript_layout,
)

_DEPTH: Final = 3
_CODE: Final = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
# The tsconfig of a project leaves its test files out; the scan then reports each as a gap that
# leaves the whole scope unknown. A draft leaves them out of the scan too (the result says so).
_TESTS: Final = "exclude_test_sources = true\n"
_NAMES: Final = {"python": "Python", "rust": "Rust", "typescript": "TypeScript", "dart": "Dart"}


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


def typescript_project(repo: Path, folder: Path) -> Layout:
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


def dart_layout(repo: Path, folder: Path) -> Layout:
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
    if (folder / "Cargo.toml").is_file() and (layout := rust_layout(repo, folder)):
        return layout
    if (folder / "package.json").is_file():
        if _workspaces(folder):
            return typescript_layout(repo, folder)
        if (folder / "tsconfig.json").is_file():
            return typescript_project(repo, folder)
    if (folder / "pubspec.yaml").is_file():
        return dart_layout(repo, folder)
    return None


def discover(repo: Path) -> tuple[list[Area], str]:
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
                areas += [Area(layout.roots[0], layout) for layout in python_layouts(repo, folder)]
            except NothingToDraft as error:
                why = why or str(error)
    return areas, why


def unique_ids(areas: list[Area]) -> list[str]:
    """One part id for each area: the folder name, or the language for the root, made unique."""
    labels = [area.label for area in areas]
    return [
        label if labels.count(label) == 1 else f"{area.layout.language}-{label}"
        for area, label in zip(areas, labels, strict=True)
    ]


def title_of(area: Area, identifier: str) -> str:
    """The title of a part: the language and the id."""
    return f"{_NAMES[area.layout.language]} {identifier}"


def detect(repo: Path) -> list[Area]:
    """The areas of the repository, or `NothingToDraft` when it has none."""
    areas, why = discover(repo)
    if not areas:
        raise NothingToDraft(
            why
            or "no Python package, Cargo workspace, TypeScript project or Dart package found "
            "(folder layout and manifest only)."
        )
    return areas
