# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Safely materialize language inputs from one Git commit."""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from archkeel.ir.facts import Language
from archkeel.ir.repository_files import (
    RepositoryFileExclusionKind,
    RepositoryFileSelection,
    repository_path_selected,
)
from archkeel.ir.repository_manifest import manifest_file_digests

from .ports import RepositorySnapshotPaths

_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_GLOB_SYNTAX = frozenset("*?[]{}!")
_METADATA_PATH = PurePosixPath("pyproject.toml")
_PUBSPEC_PATH = PurePosixPath("pubspec.yaml")
_TS_RESOLVER_SUFFIXES = frozenset(
    {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".json"}
)
_LANGUAGE_SUFFIXES = {
    Language.PYTHON: frozenset({".py"}),
    Language.DART: frozenset({".dart"}),
    Language.TYPESCRIPT: frozenset({".ts", ".tsx", ".mts", ".cts"}),
}


class SnapshotError(RuntimeError):
    """Raised when a revision cannot be materialized without ambiguity."""


@dataclass(frozen=True)
class ArchivedSnapshot:
    """One temporary language snapshot and its resolved commit."""

    root: Path
    git_head: str
    repository_paths: RepositorySnapshotPaths | None = None


class RegularGitBlobKind(Enum):
    """The supported regular-file pairs from Git's ls-tree protocol."""

    REGULAR = (b"100644", b"blob")
    EXECUTABLE = (b"100755", b"blob")


def regular_git_blob_kind(mode: bytes, kind: bytes) -> RegularGitBlobKind | None:
    """Recognize a supported pair without changing either reader's error policy."""
    try:
        return RegularGitBlobKind((mode, kind))
    except ValueError:
        return None


def resolve_commit(root: Path, revision: str) -> str:
    """Resolve a ref to the complete commit object ID used for the archive."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError(f"cannot resolve Git revision {revision!r}") from exc
    git_head = completed.stdout.strip()
    if not _FULL_GIT_SHA.fullmatch(git_head):
        raise SnapshotError(f"Git revision {revision!r} did not resolve to a full SHA-1 commit ID")
    return git_head


def _validated_roots(roots: tuple[str, ...]) -> tuple[PurePosixPath, ...]:
    if not roots:
        raise SnapshotError("snapshot roots must not be empty")
    validated: list[PurePosixPath] = []
    for value in roots:
        if not isinstance(value, str) or not value:
            raise SnapshotError("snapshot roots must be non-empty strings")
        if (
            "\x00" in value
            or "\\" in value
            or ":" in value
            or any(char in value for char in _GLOB_SYNTAX)
        ):
            raise SnapshotError(f"unsafe snapshot root: {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise SnapshotError(f"unsafe snapshot root: {value!r}")
        if path not in validated:
            validated.append(path)
    return tuple(validated)


def _git_archive_bytes(
    root: Path,
    git_head: str,
    *,
    roots: tuple[PurePosixPath, ...],
    language: Language = Language.PYTHON,
    tsconfig: str | None = None,
    repository_paths: tuple[str, ...] = (),
) -> bytes:
    """Build a tar from tree blobs; Git export attributes must not change evidence."""
    try:
        language = Language(language)
    except ValueError as exc:
        raise SnapshotError(f"unsupported snapshot language: {language}") from exc
    extra_paths = frozenset(path.encode() for path in repository_paths)
    metadata_path = _METADATA_PATH if language is Language.PYTHON else _PUBSPEC_PATH
    try:
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "-z", git_head],
            cwd=root,
            check=True,
            capture_output=True,
        )
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as stream:
            for entry in completed.stdout.split(b"\0"):
                if not entry:
                    continue
                metadata, raw_path = entry.split(b"\t", 1)
                if (
                    raw_path not in extra_paths
                    and language is Language.TYPESCRIPT
                    and not (
                        raw_path.endswith(
                            tuple(suffix.encode() for suffix in _TS_RESOLVER_SUFFIXES)
                        )
                        or (tsconfig is not None and raw_path == tsconfig.encode())
                    )
                ):
                    continue
                if (
                    raw_path not in extra_paths
                    and language is not Language.TYPESCRIPT
                    and raw_path != metadata_path.as_posix().encode()
                    and not (
                        raw_path.endswith(
                            tuple(suffix.encode() for suffix in _LANGUAGE_SUFFIXES[language])
                        )
                        and any(
                            source_root == PurePosixPath(".")
                            or raw_path.startswith(source_root.as_posix().encode() + b"/")
                            for source_root in roots
                        )
                    )
                ):
                    continue
                name = raw_path.decode("utf-8")
                path = PurePosixPath(name)
                scoped = path.suffix in _LANGUAGE_SUFFIXES[language] and any(
                    path.is_relative_to(source_root) for source_root in roots
                )
                resolver = (
                    path.suffix in _TS_RESOLVER_SUFFIXES or name == tsconfig
                    if language is Language.TYPESCRIPT
                    else path == _PUBSPEC_PATH
                    if language is Language.DART
                    else path == _METADATA_PATH
                )
                if not scoped and not resolver and raw_path not in extra_paths:
                    continue
                _safe_member_path(name)
                mode, kind, oid = metadata.split()
                if regular_git_blob_kind(mode, kind) is None:
                    raise SnapshotError(f"expected a regular Git blob: {name!r}")
                _archive_blob(stream, root, name, oid)

        return buffer.getvalue()
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError, ValueError) as exc:
        raise SnapshotError(f"cannot read snapshot blobs from Git commit {git_head}") from exc


def _archive_blob(stream: tarfile.TarFile, root: Path, name: str, oid: bytes) -> None:
    payload = subprocess.run(
        ["git", "cat-file", "blob", oid.decode("ascii")],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    stream.addfile(member, io.BytesIO(payload))


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise SnapshotError(f"unsafe Git archive member: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SnapshotError(f"unsafe Git archive member: {name!r}")
    return path


def _materialize_archive(
    archive: bytes,
    destination: Path,
    *,
    roots: tuple[str, ...],
    language: Language = Language.PYTHON,
    tsconfig: str | None = None,
    repository_paths: tuple[str, ...] = (),
) -> None:
    """Extract scoped sources and commit-bound resolver inputs for one language."""
    try:
        language = Language(language)
    except ValueError as exc:
        raise SnapshotError(f"unsupported snapshot language: {language}") from exc
    validated_roots = _validated_roots(roots)
    scoped_files = 0
    seen: set[PurePosixPath] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
            for member in stream.getmembers():
                path = _safe_member_path(member.name)
                if path in seen:
                    raise SnapshotError(f"duplicate Git archive member: {member.name!r}")
                seen.add(path)
                target = destination.joinpath(*path.parts)
                if member.isdir():
                    if language is not Language.TYPESCRIPT and not any(
                        path.is_relative_to(root) or root.is_relative_to(path)
                        for root in validated_roots
                    ):
                        raise SnapshotError(f"unsupported Git archive member: {member.name!r}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                is_scoped_source = path.suffix in _LANGUAGE_SUFFIXES[language] and any(
                    path.is_relative_to(root) for root in validated_roots
                )
                if language is Language.PYTHON:
                    allowed_metadata = path == _METADATA_PATH
                elif language is Language.DART:
                    allowed_metadata = path == _PUBSPEC_PATH
                else:
                    allowed_metadata = path.name in {"package.json", "tsconfig.json"} or (
                        tsconfig is not None and path.as_posix() == tsconfig
                    )
                resolver_input = (
                    language is Language.TYPESCRIPT and path.suffix in _TS_RESOLVER_SUFFIXES
                )
                if not member.isfile() or not (
                    is_scoped_source
                    or allowed_metadata
                    or resolver_input
                    or member.name in repository_paths
                ):
                    raise SnapshotError(f"unsupported Git archive member: {member.name!r}")
                source = stream.extractfile(member)
                if source is None:
                    raise SnapshotError(f"cannot read Git archive member: {member.name!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
                if is_scoped_source:
                    scoped_files += 1
    except (tarfile.TarError, OSError) as exc:
        raise SnapshotError(f"invalid Git archive: {exc}") from exc
    if scoped_files == 0:
        raise SnapshotError(f"Git archive contains no scoped {language.title()} sources")


def _repository_paths(
    root: Path, git_head: str, selections: tuple[RepositoryFileSelection, ...]
) -> tuple[RepositorySnapshotPaths, tuple[str, ...]]:
    try:
        entries = subprocess.run(
            ["git", "ls-tree", "-r", "-z", git_head],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        paths = tuple(
            sorted(entry.split(b"\t", 1)[1].decode("utf-8") for entry in entries if entry)
        )
        extra = {
            path
            for path in paths
            if any(repository_path_selected(s, path, b"#!") for s in selections)
        }
        for selection in selections:
            for exclusion in selection.exclusions:
                extra.add(exclusion.path)
                if exclusion.kind is not RepositoryFileExclusionKind.MANIFEST:
                    continue
                result = subprocess.run(
                    ["git", "show", f"{git_head}:{exclusion.path}"],
                    cwd=root,
                    capture_output=True,
                )
                if (
                    result.returncode
                    or hashlib.sha256(result.stdout).hexdigest() != exclusion.sha256
                ):
                    continue
                try:
                    extra.update(
                        path for path, _ in manifest_file_digests(exclusion.path, result.stdout)
                    )
                except (ValueError, TypeError, UnicodeError):
                    continue
        return RepositorySnapshotPaths(paths, git_head, False), tuple(sorted(extra))
    except (OSError, UnicodeError, subprocess.CalledProcessError, ValueError) as error:
        raise SnapshotError("cannot enumerate repository inputs from Git revision") from error


@contextmanager
def materialize_git_snapshot(
    root: Path,
    revision: str,
    *,
    roots: tuple[str, ...],
    language: Language = Language.PYTHON,
    tsconfig: str | None = None,
    repository_selections: tuple[RepositoryFileSelection, ...] = (),
) -> Iterator[ArchivedSnapshot]:
    """Yield a safely extracted language snapshot for one resolved commit."""
    repository_root = root.resolve()
    validated_roots = _validated_roots(roots)
    git_head = resolve_commit(repository_root, revision)
    repository = None
    extra_paths: tuple[str, ...] = ()
    if repository_selections:
        repository, extra_paths = _repository_paths(
            repository_root, git_head, repository_selections
        )
    archive = _git_archive_bytes(
        repository_root,
        git_head,
        roots=validated_roots,
        language=language,
        tsconfig=tsconfig,
        repository_paths=extra_paths,
    )
    with TemporaryDirectory(prefix="archkeel-snapshot-") as temporary:
        destination = Path(temporary)
        _materialize_archive(
            archive,
            destination,
            roots=roots,
            language=language,
            tsconfig=tsconfig,
            repository_paths=extra_paths,
        )
        yield ArchivedSnapshot(root=destination, git_head=git_head, repository_paths=repository)
