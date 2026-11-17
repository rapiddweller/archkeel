# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the folder layout of a TypeScript project or a package.json workspace (AD-638, AD-660).

A TypeScript project is one scan with its tsconfig; a workspace with a root tsconfig is one scan of
its members. Only the layout, the manifests and the tsconfig are read; no source file is read.
"""

from __future__ import annotations

import itertools
import json
import os
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path

from .core_schema import schema_file
from .init_areas import _IGNORED, _TESTS, Layout, Part, _members, _name, _refuse


def _escape(segment: str) -> str:
    """The module identity of a TypeScript path segment: a character other than an ASCII letter
    or digit is `_x<hex>_`, as the collector writes it (`.` is `_x2e_`, `_` is `_x5f_`)."""
    return "".join(c if c.isascii() and c.isalnum() else f"_x{ord(c):x}_" for c in segment)


@cache
def _code_suffixes() -> frozenset[str]:
    """The TypeScript and JavaScript source suffixes, read from the one owner of the table.

    `schema/archkeel-source-suffixes.txt` holds one `language suffix` row for each suffix; the
    contract crate embeds the same file."""
    lines = schema_file("archkeel-source-suffixes.txt").read_text(encoding="utf-8").splitlines()
    rows = [line.split(" ", 1) for line in lines if " " in line]
    return frozenset(suffix for language, suffix in rows if language == "typescript")


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
    namespace = _name(repo.name)  # the module identity holds the path already (#1617)
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


def _has_source(folder: Path, repo: Path) -> bool:
    """Whether `folder` holds code that is no test source (the scan of a draft leaves those out)."""
    for here, names, files in os.walk(folder):
        names[:] = [name for name in names if name not in _IGNORED]
        for file in files:
            if Path(file).suffix in _code_suffixes() and not _is_test(Path(here, file), repo):
                return True
    return False


def _is_test(path: Path, repo: Path) -> bool:
    """`is_test_source` of the TypeScript collector (`native/typescript/src/test_sources.rs`):
    a folder `test`, `tests` or `__tests__` above the file, or `*.test.<ext>`, `*.spec.<ext>`."""
    relative = path.relative_to(repo)
    stem = relative.name.rsplit(".", 1)[0]
    folders = any(part in {"test", "tests", "__tests__"} for part in relative.parts[:-1])
    return folders or stem.endswith((".test", ".spec"))


def _own_project(folder: Path) -> bool:
    """A folder with its own package.json and tsconfig.json is a TypeScript project of its own."""
    return (folder / "package.json").is_file() and (folder / "tsconfig.json").is_file()


def _selected(folder: Path) -> Callable[[Path], bool]:
    """Whether the `include` of the tsconfig of the project can select a file below a folder
    (relative to the project). Without a readable `include`, every folder: TypeScript then takes
    `**/*` or the `include` of the config that it extends."""
    try:
        config = json.loads(_jsonc(folder / "tsconfig.json"))
    except (OSError, UnicodeError, ValueError):
        return lambda _: True
    patterns = config.get("include") if isinstance(config, dict) else None
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        return lambda _: True
    literal = [_literal(pattern) for pattern in patterns]

    def selects(relative: Path) -> bool:
        parts = relative.parts
        return any(parts[: len(lead)] == lead or lead[: len(parts)] == parts for lead in literal)

    return selects


def _literal(pattern: str) -> tuple[str, ...]:
    """The folders of an include pattern before its first wildcard: `./src/**/*` is `("src",)`."""
    parts = [part for part in pattern.replace("\\", "/").split("/") if part not in {"", "."}]
    lead = itertools.takewhile(lambda part: not any(c in part for c in "*?[{"), parts)
    found = tuple(lead)
    # A last part without a wildcard can be a file (`src/index.ts`): its folder is the literal.
    return found[:-1] if found == tuple(parts) and found and "." in found[-1] else found


def _jsonc(path: Path) -> str:
    """The text of a tsconfig without comments and trailing commas (JSON with comments)."""
    text, out, i = path.read_text(encoding="utf-8"), [], 0
    quoted = False
    while i < len(text):
        char = text[i]
        if quoted:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            out.append(char)
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = len(text) if i < 0 else i
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _typescript_project(repo: Path, folder: Path) -> Layout:
    """One component for each folder of the project that holds code; the folders inside `src`
    count instead of `src` itself. The files beside them are the component `root`.

    The scan root is the project folder, not `src`: an import of a file beside `src` (a config or a
    host list) then resolves to a module of the scan. The identity of a module is the namespace
    and the repository-relative path, each segment escaped as the collector writes it."""
    # A module identity is the namespace and the repository path (#1617): the namespace of the
    # repository keeps a project below the root from naming its folder twice (`web.src.web`).
    namespace = _name(repo.name)

    selects = _selected(folder)

    def code_dirs(parent: Path) -> list[Path]:
        # A folder is a component when the tsconfig selects it, it holds code that is no test
        # source, and it is no project of its own (another part of the system, #1710).
        return [
            path
            for path in sorted(parent.iterdir())
            if path.is_dir()
            and path.name not in _IGNORED
            and selects(path.relative_to(folder))
            and not _own_project(path)
            and _has_source(path, repo)
        ]

    def code_files(parent: Path) -> list[Path]:
        return [
            path
            for path in sorted(parent.iterdir())
            if path.is_file() and path.suffix in _code_suffixes()
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
