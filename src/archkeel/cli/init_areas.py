# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the folder layout of one language area of a repository (AD-638, AD-660); `init_draft`
finds the areas.

An area is one scan: a Python project, a Cargo workspace, a TypeScript project (or workspace) or
a Dart package. A repository with one area is drafted as one configuration (`init_draft`); a
repository with several is drafted as a system, one part for each area. Only the layout is read:
folders, `__init__.py`, `Cargo.toml`, `package.json` of workspace members and manifests. No source
file is read and no import is followed, so a layout gives no fact about the code. A layout that
this module cannot name soundly raises `NothingToDraft`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Final

from .init_binding import _table, _value

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
    """The scan that a layout names: language, namespace, roots, components and an extra line.

    `project` is the folder of the `pyproject.toml` of a Python scan; `crates` are the folders of
    the crates of a Rust scan (AD-784 reads their manifests for a binding)."""

    language: str
    namespace: str
    roots: tuple[str, ...]
    parts: tuple[Part, ...]
    extra: str = ""
    note: str = ""
    project: str = ""
    crates: tuple[str, ...] = ()


def _refuse(why: str) -> NothingToDraft:
    return NothingToDraft(f"{why}. Write archkeel.toml by hand: {DOCUMENT}")


def _name(text: str) -> str:
    """A label or namespace: letters, digits and underscore only."""
    return re.sub(r"\W+", "_", text).strip("_").lower() or "app"


def _packages(folder: Path, repo: Path) -> list[Path]:
    """The subfolders of `folder` that hold Python code that is no test source, at any depth (a
    folder without `__init__.py` is a namespace package, and the scan reads its modules too)."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_dir() and path.name not in _IGNORED and _has_python(path, repo)
    )


def _has_python(folder: Path, repo: Path) -> bool:
    for here, names, files in os.walk(folder):
        names[:] = [name for name in names if name not in _IGNORED]
        if any(f.endswith(".py") and not _is_test(Path(here, f).relative_to(repo)) for f in files):
            return True
    return False


def _is_test(relative: Path) -> bool:
    """`is_test_source` of the Python collector (`native/python/src/discover.rs`): a folder `test`,
    `tests` or `__tests__` above the file, or a name `test_*.py` or `*_test.py`. A Python draft
    leaves these out of the scan (#1619), as the Rust and TypeScript drafts do."""
    name = relative.name
    named = (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")
    return named or any(part in {"test", "tests", "__tests__"} for part in relative.parts[:-1])


def _members(root: Path, patterns: list[str], marker: str) -> list[Path]:
    """The workspace members: each folder that a pattern names (one `*` level) and that holds
    the marker file."""
    found: set[Path] = set()
    for pattern in patterns:
        # `.` names the folder itself (tokio: `fuzz` is its own workspace); `glob` refuses it.
        relative = PurePosixPath(pattern)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        for path in root.glob(relative.as_posix()) if relative.parts else [root]:
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
        _packages(base, root)
        if src
        else [p for p in _packages(base, root) if (p / "__init__.py").is_file()]
    )
    if not found:
        where = base.relative_to(root).as_posix()
        raise _refuse(f"no top-level Python package (a folder with __init__.py) in {where}")
    note = _python_note(folder)
    if src and len(found) > 1:
        layouts = [_python_scan(root, base, [p.name for p in found], note)]
    else:
        layouts = [_python_single(root, package, note) for package in found]
    project = folder.relative_to(root).as_posix() or "."
    return [replace(layout, project=project) for layout in layouts]


def _python_single(root: Path, package: Path, note: str) -> Layout:
    """The scan of one package: a component for each folder in it that holds Python."""
    namespace = package.name
    parts = [Part(p.name, (f"{namespace}.{p.name}",)) for p in _packages(package, root)]
    parts.append(Part("root", modules=_beside(namespace, package, {p.label for p in parts}, True)))
    scan = package.relative_to(root).as_posix()
    return Layout("python", namespace, (scan,), tuple(parts), _TESTS, note=note)


def _python_scan(root: Path, base: Path, names: list[str], note: str) -> Layout:
    """The scan of a folder (`src`) that holds several packages: a component for each."""
    namespace = _name(base.name)
    parts = [Part(name, (f"{namespace}.{name}",)) for name in names]
    own = (base / "__init__.py").is_file()  # a package `src/__init__.py` is a module of the scan
    parts.append(Part("root", modules=_beside(namespace, base, set(names), own)))
    scan = base.relative_to(root).as_posix()
    return Layout("python", namespace, (scan,), tuple(parts), _TESTS, note=note)


def _beside(namespace: str, folder: Path, taken: set[str], itself: bool) -> tuple[str, ...]:
    """The modules directly in `folder`: the package itself and each `.py` file beside the parts
    that is no test source."""
    return tuple(
        ([namespace] if itself and (folder / "__init__.py").is_file() else [])
        + [
            f"{namespace}.{path.stem}"
            for path in sorted(folder.glob("*.py"))
            if path.stem != "__init__" and path.stem not in taken and not _is_test(Path(path.name))
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
    `repo`), or the layout of the one crate there (`_rust_crate`); `None` for neither."""
    manifest = root / "Cargo.toml"
    if not manifest.is_file():
        return None
    text = manifest.read_text(encoding="utf-8")
    if not re.search(r"^\[workspace\]", text, re.M):
        return _rust_crate(repo, root, text)
    listed = re.search(r"^members\s*=\s*\[(.*?)\]", text, re.M | re.S)
    patterns = re.findall(r'"([^"]+)"', listed[1]) if listed else []
    parts: list[Part] = []
    crates: list[str] = []
    # The scan reads every crate below the root, also one that `members` does not name (a fuzz
    # workspace, an excluded test crate): each needs an owner, after the members.
    named = _members(root, patterns, "Cargo.toml")
    for crate in [*named, *(path for path in _crates_below(root) if path not in named)]:
        found = re.search(
            r'^\[package\].*?^name\s*=\s*"([^"]+)"',
            (crate / "Cargo.toml").read_text(encoding="utf-8"),
            re.M | re.S,
        )
        if found:
            name = found[1].replace("-", "_")
            parts.append(Part(_name(found[1]), (f"{_name(root.name or repo.name)}.{name}",)))
            crates.append(crate.relative_to(repo).as_posix())
    if len(parts) < 2:
        raise _refuse("the Cargo workspace names fewer than two crates with a [package] name")
    scan = root.relative_to(repo).as_posix()
    # Test, bench and example code stays out of the scan, as for one crate (#1612) and TypeScript:
    # a dev-dependency back to a sibling crate is no edge of the production graph (#1680).
    namespace = _name(root.name or repo.name)
    return Layout("rust", namespace, (scan,), tuple(parts), _TESTS, crates=tuple(crates))


def _crates_below(root: Path) -> list[Path]:
    """Each folder at or below `root` with a `Cargo.toml`, without hidden or generated folders."""
    found = []
    for folder, names, files in os.walk(root):
        names[:] = sorted(n for n in names if n not in _IGNORED and not n.startswith("."))
        if "Cargo.toml" in files:
            found.append(Path(folder))
    return found


def _in_workspace(repo: Path, folder: Path) -> bool:
    """Whether a `Cargo.toml` with `[workspace]` lies in a folder above `folder`, in `repo`."""
    for above in folder.parents:
        if not above.is_relative_to(repo):
            return False
        manifest = above / "Cargo.toml"
        if manifest.is_file() and re.search(
            r"^\[workspace\]", manifest.read_text(encoding="utf-8"), re.M
        ):
            return True
    return False


def _rust_crate(repo: Path, root: Path, text: str) -> Layout | None:
    """The scan of one crate that no workspace holds (#1612): a component for each top module
    beside the crate root file (a `.rs` file or a folder that holds Rust), and `root` for the crate
    root and its build script. The collector names the crate `<namespace>.<package>` with `_` for
    `-`. Test, bench and example targets stay out of the scan, as for a TypeScript draft."""
    package = _table(text, "package")
    name = _value(package, "name")
    if name is None or _in_workspace(repo, root):
        return None
    stated = _value(_table(text, "lib"), "path")
    files = [stated] if stated else ["src/lib.rs", "src/main.rs"]
    top = next((root / file for file in files if (root / file).is_file()), None)
    if top is None:
        raise _refuse(f"the crate {name} has no src/lib.rs or src/main.rs")
    namespace = _name(root.name or repo.name)
    module = f"{namespace}.{name.replace('-', '_')}"
    names = sorted(
        {p.stem for p in top.parent.glob("*.rs") if p != top and p.name != "main.rs"}
        | {
            p.name
            for p in top.parent.iterdir()
            if p.is_dir() and p.name != "bin" and any(p.rglob("*.rs"))
        }
    )
    parts = [Part(_name(n), (f"{module}.{n}",)) for n in names if re.fullmatch(r"[A-Za-z_]\w*", n)]
    # Cargo builds `build.rs` unless `build = false`, and a stated `build = "path"` instead.
    off = re.search(r"^build\s*=\s*false", package or "", re.M)
    build = _value(package, "build") or (not off and (root / "build.rs").is_file())
    script = (f"{module}.build_script",) if build else ()
    # The collector reads the manifest as a module `cargo_toml`, with `_` until the name is free.
    manifest = "cargo_toml"
    while manifest in names:
        manifest += "_"
    parts.append(Part("root", modules=(module, *script, f"{module}.{manifest}")))
    scan = root.relative_to(repo).as_posix()
    return Layout("rust", namespace, (scan,), tuple(parts), _TESTS, crates=(scan,))


_DEPTH: Final = 3
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
        """The part id before the names of several areas are made unique: the folder name, or for
        the root the name of the project (its namespace), not its language (#1709)."""
        return _name(Path(self.folder).name) if self.folder != "." else self.layout.namespace


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
