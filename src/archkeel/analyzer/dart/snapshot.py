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
from enum import StrEnum
from pathlib import Path, PurePosixPath

from archkeel.ir.facts import (
    ResolutionInput,
    ResolutionRole,
    RuntimeRequirementState,
    dart_module_name,
)
from archkeel.ir.protocol import CollectionRequest


class SnapshotProblemKind(StrEnum):
    SOURCE_LINK = "DartSourceLink"
    READ_ERROR = "SnapshotError"
    MODULE_ERROR = "DartModuleError"
    SELECTED_ROOT = "SelectedRootError"
    CONTAINMENT = "ContainmentError"
    EXCLUDED_TREE = "ExcludedTreeError"
    MODULE_COLLISION = "DartModuleCollision"


class _SourceSuffix(StrEnum):
    DART = ".dart"


def _source_suffix(path: Path) -> _SourceSuffix | None:
    """Decode a filename suffix while retaining the selected .dart dotfile."""
    try:
        return _SourceSuffix(path.suffix or path.name)
    except ValueError:
        return None


class _Platform(StrEnum):
    WINDOWS = "win32"


def _platform(value: str) -> _Platform | None:
    try:
        return _Platform(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SnapshotProblem:
    path: str
    kind: SnapshotProblemKind
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
    sdk_constraint_state: RuntimeRequirementState
    inputs: tuple[ResolutionInput, ...]
    problems: tuple[SnapshotProblem, ...]
    roots: tuple[str, ...]

    @property
    def source_by_path(self) -> dict[str, Source]:
        return {source.rel_path: source for source in self.sources}


_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PUBSPEC_NAME = re.compile(r"^name\s*:\s*(.*?)\s*(?:#.*)?$")
_PUBSPEC_SDK = re.compile(r"sdk")
_PUBSPEC_IGNORABLE_LINE = re.compile(r"\s*(?:#.*)?")


def _roots(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise ValueError("Dart snapshot roots must not be empty")
    result: list[str] = []
    for value in values:
        if not value or re.search(r"[\x00\\\\:*?\[\]{}!]", value) is not None:
            raise ValueError(f"unsafe Dart snapshot root: {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or any(re.fullmatch(r"\.\.", part) for part in path.parts):
            raise ValueError(f"unsafe Dart snapshot root: {value!r}")
        normalized = path.as_posix()
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def _unquote_scalar(value: str) -> str:
    match = re.fullmatch(r"""(?P<quote>['\x22])(?P<value>[\s\S]*)(?P=quote)""", value)
    return match.group("value") if match is not None else value


def _pubspec_metadata(raw: bytes) -> tuple[str | None, str | None, RuntimeRequirementState]:
    """Read the top-level package name and environment SDK scalar without a YAML dependency."""
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None, None, RuntimeRequirementState.REQUIREMENT_INVALID
    name: str | None = None
    sdk: str | None = None
    environment_indent: int | None = None
    field_indent: int | None = None
    names = 0
    environments = 0
    sdk_fields = 0
    invalid_sdk = False
    for line in lines:
        if _PUBSPEC_IGNORABLE_LINE.fullmatch(line) is not None:
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            found_name = _PUBSPEC_NAME.fullmatch(line)
            if found_name is not None:
                names += 1
                value = found_name.group(1).strip()
                value = _unquote_scalar(value)
                name = value if _PACKAGE_NAME.fullmatch(value) else None
            key, separator, value = line.partition(":")
            value = value.split("#", 1)[0].strip()
            field_indent = None
            if re.fullmatch(r"\s*environment\s*", key) is not None and separator:
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
            if _PUBSPEC_SDK.fullmatch(field[0]) is not None and (
                indent != field_indent or re.search(r"\t", line[:indent]) is not None
            ):
                invalid_sdk = True
                continue
            if _PUBSPEC_SDK.fullmatch(field[0]) is not None:
                sdk_fields += 1
                value = field[2].strip().split(" #", 1)[0].strip()
                value = _unquote_scalar(value)
                if not field[1] or not value or re.search(r"[{}\[\]&*!|]", value) is not None:
                    invalid_sdk = True
                else:
                    sdk = value
    state: RuntimeRequirementState = (
        RuntimeRequirementState.REQUIREMENT_INVALID
        if invalid_sdk or environments > 1 or sdk_fields > 1
        else RuntimeRequirementState.DECLARED
        if sdk_fields == 1
        else RuntimeRequirementState.REQUIREMENT_MISSING
    )
    if names != 1:
        name = None
    if state == RuntimeRequirementState.REQUIREMENT_INVALID:
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


def _regular_opener(path: str, flags: int) -> int:
    # open(..., "rb") supplies the host binary flag. POSIX safety flags remain
    # additive; containment and inode identity are checked before consuming bytes.
    if _platform(sys.platform) != _Platform.WINDOWS:
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    return os.open(path, flags)


def _read_regular(path: Path, real_root: Path) -> bytes:
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode) or not path.resolve(strict=True).is_relative_to(
        real_root
    ):
        raise OSError("input is outside snapshot or not a regular file")
    with open(path, "rb", opener=_regular_opener) as stream:
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
        problems.append(
            SnapshotProblem(rel, SnapshotProblemKind.SOURCE_LINK, "source file is a symlink")
        )
        return None
    try:
        content = _read_regular(path, real_root)
    except OSError as error:
        problems.append(SnapshotProblem(rel, SnapshotProblemKind.READ_ERROR, str(error)))
        return None
    relative = PurePosixPath(rel).relative_to(PurePosixPath(source_root)).as_posix()
    short = dart_module_name(relative)
    if short is None:
        problems.append(
            SnapshotProblem(
                rel, SnapshotProblemKind.MODULE_ERROR, "path is not a Dart module identifier"
            )
        )
        return None
    source = Source(rel, f"{namespace}.{short}", content)
    item = ResolutionInput(rel, hashlib.sha256(content).hexdigest(), ResolutionRole.SELECTED)
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
        problems.append(
            SnapshotProblem(
                source_root, SnapshotProblemKind.SOURCE_LINK, "source root is a symlink"
            )
        )
        return []
    if not base.exists() or not base.is_dir():
        problems.append(
            SnapshotProblem(
                source_root,
                SnapshotProblemKind.SELECTED_ROOT,
                "selected root is missing or not a directory",
            )
        )
        return []
    try:
        if not base.resolve(strict=True).is_relative_to(real_root):
            problems.append(
                SnapshotProblem(
                    source_root, SnapshotProblemKind.CONTAINMENT, "source root escapes snapshot"
                )
            )
            return []
    except OSError as error:
        problems.append(SnapshotProblem(source_root, SnapshotProblemKind.READ_ERROR, str(error)))
        return []

    def on_walk_error(error: OSError) -> None:
        failed = Path(error.filename) if error.filename else base
        try:
            rel = failed.relative_to(root).as_posix()
        except ValueError:
            rel = source_root
        problems.append(SnapshotProblem(rel, SnapshotProblemKind.READ_ERROR, str(error)))

    result: list[tuple[Source, ResolutionInput]] = []
    for directory, dirnames, filenames in os.walk(base, followlinks=False, onerror=on_walk_error):
        current = Path(directory)
        dirnames[:] = _safe_subdirectories(root, current, dirnames, problems)
        for name in sorted(filenames):
            path = current / name
            rel = path.relative_to(root).as_posix()
            if _source_suffix(path) is _SourceSuffix.DART and rel not in seen_paths:
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
        if re.fullmatch(r"(?:\.dart_tool|pubcache|\.pub-cache)", name) is not None:
            problems.append(
                SnapshotProblem(
                    rel,
                    SnapshotProblemKind.EXCLUDED_TREE,
                    "selected source tree contains excluded generated/cache files",
                )
            )
        elif path.is_symlink():
            problems.append(
                SnapshotProblem(
                    rel, SnapshotProblemKind.SOURCE_LINK, "source directory is a symlink"
                )
            )
        else:
            result.append(name)
    return result


def _read_pubspec(
    root: Path, real_root: Path
) -> tuple[str, str | None, RuntimeRequirementState, ResolutionInput]:
    pubspec = root / "pubspec.yaml"
    if not os.path.lexists(pubspec) or pubspec.is_symlink():
        raise SnapshotError("regular pubspec.yaml is required inside the snapshot")
    try:
        raw = _read_regular(pubspec, real_root)
        package_name, sdk_constraint, parsed_state = _pubspec_metadata(raw)
        if package_name is None:
            raise SnapshotError("pubspec.yaml must declare a valid package name")
        item = ResolutionInput(
            "pubspec.yaml", hashlib.sha256(raw).hexdigest(), ResolutionRole.RESOLUTION
        )
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
                        rel,
                        SnapshotProblemKind.MODULE_COLLISION,
                        f"{module} maps from {', '.join(sorted(paths))}",
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
