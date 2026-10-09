# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read only the selected Dart sources and their package identity input."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from archkeel.ir.facts import ResolutionInput, dart_module_name
from archkeel.ir.protocol import CollectionRequest


@dataclass(frozen=True, slots=True)
class SnapshotProblem:
    path: str
    kind: str
    message: str


class SnapshotError(RuntimeError):
    """A required snapshot metadata input cannot be safely read."""


@dataclass(frozen=True, slots=True)
class Source:
    rel_path: str
    module: str
    content: bytes


@dataclass(frozen=True, slots=True)
class Snapshot:
    sources: tuple[Source, ...]
    package_name: str
    sdk_constraint: str | None
    sdk_constraint_state: Literal[
        "metadata_missing", "requirement_missing", "requirement_invalid", "declared"
    ]
    inputs: tuple[ResolutionInput, ...]
    problems: tuple[SnapshotProblem, ...]
    roots: tuple[str, ...]

    @property
    def source_by_path(self) -> dict[str, Source]:
        return {source.rel_path: source for source in self.sources}


_GLOB = frozenset("*?[]{}!")
_EXCLUDED_DIRS = frozenset({".dart_tool", "pubcache", ".pub-cache"})
_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PUBSPEC_NAME = re.compile(r"^name\s*:\s*(.*?)\s*(?:#.*)?$")


def _roots(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise ValueError("Dart snapshot roots must not be empty")
    result: list[str] = []
    for value in values:
        if (
            not value
            or "\x00" in value
            or "\\" in value
            or ":" in value
            or any(char in value for char in _GLOB)
        ):
            raise ValueError(f"unsafe Dart snapshot root: {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe Dart snapshot root: {value!r}")
        normalized = path.as_posix()
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


_SDK_STATE = Literal["metadata_missing", "requirement_missing", "requirement_invalid", "declared"]


def _pubspec_metadata(raw: bytes) -> tuple[str | None, str | None, _SDK_STATE]:
    """Read the top-level package name and environment SDK scalar without a YAML dependency."""
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None, None, "requirement_invalid"
    name: str | None = None
    sdk: str | None = None
    environment_indent: int | None = None
    field_indent: int | None = None
    names = 0
    environments = 0
    sdk_fields = 0
    invalid_sdk = False
    for line in lines:
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            found_name = _PUBSPEC_NAME.fullmatch(line)
            if found_name is not None:
                names += 1
                value = found_name.group(1).strip()
                if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                    value = value[1:-1]
                name = value if _PACKAGE_NAME.fullmatch(value) else None
            key, separator, value = line.partition(":")
            value = value.split("#", 1)[0].strip()
            field_indent = None
            if key.strip() == "environment" and separator:
                environments += 1
                environment_indent = indent if not value.strip() else None
                if value.strip():
                    invalid_sdk = True
            else:
                environment_indent = None
        elif environment_indent == 0:
            if field_indent is None:
                field_indent = indent
            field = line.strip().partition(":")
            if field[0] == "sdk" and (indent != field_indent or "\t" in line[:indent]):
                invalid_sdk = True
                continue
            if field[0] == "sdk":
                sdk_fields += 1
                value = field[2].strip().split(" #", 1)[0].strip()
                if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                    value = value[1:-1]
                if not field[1] or not value or any(char in value for char in "{}[]&*!|"):
                    invalid_sdk = True
                else:
                    sdk = value
    state: _SDK_STATE = (
        "requirement_invalid"
        if invalid_sdk or environments > 1 or sdk_fields > 1
        else "declared"
        if sdk_fields == 1
        else "requirement_missing"
    )
    if names != 1:
        name = None
    if state == "requirement_invalid":
        sdk = None
    return name, sdk, state


def _real_snapshot_root(root: Path) -> Path:
    try:
        if root.is_symlink():
            raise SnapshotError("snapshot root must not be a symlink")
        real_root = root.resolve(strict=True)
    except OSError as error:
        raise SnapshotError(f"cannot resolve snapshot root: {error}") from error
    if not real_root.is_dir():
        raise SnapshotError("snapshot root is not a directory")
    return real_root


def _read_regular(path: Path, real_root: Path) -> bytes:
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode) or not path.resolve(strict=True).is_relative_to(
        real_root
    ):
        raise OSError("input is outside snapshot or not a regular file")
    flags = os.O_RDONLY
    if sys.platform == "win32":
        flags |= os.O_BINARY
    else:
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        # Check the opened object before consuming bytes; the pathname may have changed.
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(expected, opened):
            raise OSError("snapshot input changed before reading")
        return stream.read()


def _read_source_file(
    root: Path,
    real_root: Path,
    source_root: str,
    namespace: str,
    path: Path,
    problems: list[SnapshotProblem],
) -> tuple[Source, ResolutionInput] | None:
    rel = path.relative_to(root).as_posix()
    if path.is_symlink():
        problems.append(SnapshotProblem(rel, "DartSourceLink", "source file is a symlink"))
        return None
    try:
        content = _read_regular(path, real_root)
    except OSError as error:
        problems.append(SnapshotProblem(rel, "SnapshotError", str(error)))
        return None
    relative = PurePosixPath(rel).relative_to(PurePosixPath(source_root)).as_posix()
    short = dart_module_name(relative)
    if short is None:
        problems.append(
            SnapshotProblem(rel, "DartModuleError", "path is not a Dart module identifier")
        )
        return None
    source = Source(rel, f"{namespace}.{short}", content)
    item = ResolutionInput(rel, hashlib.sha256(content).hexdigest(), "selected")
    return source, item


def _read_source_root(
    root: Path,
    real_root: Path,
    source_root: str,
    namespace: str,
    seen_paths: set[str],
    problems: list[SnapshotProblem],
) -> list[tuple[Source, ResolutionInput]]:
    base = root / source_root
    if base.is_symlink():
        problems.append(SnapshotProblem(source_root, "DartSourceLink", "source root is a symlink"))
        return []
    if not base.exists() or not base.is_dir():
        problems.append(
            SnapshotProblem(
                source_root, "SelectedRootError", "selected root is missing or not a directory"
            )
        )
        return []
    try:
        if not base.resolve(strict=True).is_relative_to(real_root):
            problems.append(
                SnapshotProblem(source_root, "ContainmentError", "source root escapes snapshot")
            )
            return []
    except OSError as error:
        problems.append(SnapshotProblem(source_root, "SnapshotError", str(error)))
        return []

    def on_walk_error(error: OSError) -> None:
        failed = Path(error.filename) if error.filename else base
        try:
            rel = failed.relative_to(root).as_posix()
        except ValueError:
            rel = source_root
        problems.append(SnapshotProblem(rel, "SnapshotError", str(error)))

    result: list[tuple[Source, ResolutionInput]] = []
    for directory, dirnames, filenames in os.walk(base, followlinks=False, onerror=on_walk_error):
        current = Path(directory)
        dirnames[:] = _safe_subdirectories(root, current, dirnames, problems)
        for name in sorted(filenames):
            path = current / name
            rel = path.relative_to(root).as_posix()
            if name.endswith(".dart") and rel not in seen_paths:
                seen_paths.add(rel)
                item = _read_source_file(root, real_root, source_root, namespace, path, problems)
                if item is not None:
                    result.append(item)
    return result


def _safe_subdirectories(
    root: Path, current: Path, dirnames: list[str], problems: list[SnapshotProblem]
) -> list[str]:
    result: list[str] = []
    for name in sorted(dirnames):
        path = current / name
        rel = path.relative_to(root).as_posix()
        if name in _EXCLUDED_DIRS:
            problems.append(
                SnapshotProblem(
                    rel,
                    "ExcludedTreeError",
                    "selected source tree contains excluded generated/cache files",
                )
            )
        elif path.is_symlink():
            problems.append(SnapshotProblem(rel, "DartSourceLink", "source directory is a symlink"))
        else:
            result.append(name)
    return result


def _read_pubspec(
    root: Path, real_root: Path
) -> tuple[str, str | None, _SDK_STATE, ResolutionInput]:
    pubspec = root / "pubspec.yaml"
    if not os.path.lexists(pubspec) or pubspec.is_symlink():
        raise SnapshotError("regular pubspec.yaml is required inside the snapshot")
    try:
        raw = _read_regular(pubspec, real_root)
        package_name, sdk_constraint, parsed_state = _pubspec_metadata(raw)
        if package_name is None:
            raise SnapshotError("pubspec.yaml must declare a valid package name")
        item = ResolutionInput("pubspec.yaml", hashlib.sha256(raw).hexdigest(), "resolution")
        return package_name, sdk_constraint, parsed_state, item
    except OSError as error:
        raise SnapshotError(f"cannot read regular pubspec.yaml: {error}") from error


def _collision_problems(sources: list[Source], problems: list[SnapshotProblem]) -> None:
    module_paths: dict[str, list[str]] = {}
    for source in sources:
        module_paths.setdefault(source.module, []).append(source.rel_path)
    for module, paths in module_paths.items():
        if len(paths) > 1:
            for rel in paths:
                problems.append(
                    SnapshotProblem(
                        rel, "DartModuleCollision", f"{module} maps from {', '.join(sorted(paths))}"
                    )
                )


def read_snapshot(request: CollectionRequest) -> Snapshot:
    """Read each selected `.dart` file once; symlinks and escaped roots are never followed."""
    root = Path(request.snapshot.root).absolute()
    roots = _roots(request.scope.roots)
    real_root = _real_snapshot_root(root)
    problems: list[SnapshotProblem] = []
    inputs: dict[str, ResolutionInput] = {}
    sources: list[Source] = []
    seen_paths: set[str] = set()
    for source_root in roots:
        for source, item in _read_source_root(
            root, real_root, source_root, request.scope.namespace, seen_paths, problems
        ):
            sources.append(source)
            inputs[item.path] = item
    package_name, sdk_constraint, sdk_state, pubspec_input = _read_pubspec(root, real_root)
    inputs[pubspec_input.path] = pubspec_input
    _collision_problems(sources, problems)
    sources.sort(key=lambda item: item.rel_path)
    return Snapshot(
        tuple(sources),
        package_name,
        sdk_constraint,
        sdk_state,
        tuple(inputs[key] for key in sorted(inputs)),
        tuple(problems),
        roots,
    )
