# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Safely materialize scoped Python files from one Git commit."""

from __future__ import annotations

import io
import re
import subprocess
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_GLOB_SYNTAX = frozenset("*?[]{}!")
_METADATA_PATH = PurePosixPath("pyproject.toml")


class SnapshotError(RuntimeError):
    """Raised when a revision cannot be materialized without ambiguity."""


@dataclass(frozen=True)
class ArchivedSnapshot:
    """One temporary Python-only snapshot and its resolved commit."""

    root: Path
    git_head: str


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


def _python_pathspecs(roots: tuple[PurePosixPath, ...]) -> tuple[str, ...]:
    return tuple(
        ":(glob,top)**/*.py"
        if path == PurePosixPath(".")
        else f":(glob,top){path.as_posix()}/**/*.py"
        for path in roots
    )


def _has_metadata(root: Path, git_head: str) -> bool:
    try:
        return (
            subprocess.run(
                ["git", "cat-file", "-e", f"{git_head}:{_METADATA_PATH.as_posix()}"],
                cwd=root,
                capture_output=True,
            ).returncode
            == 0
        )
    except OSError as exc:
        raise SnapshotError(f"cannot inspect Git commit {git_head}") from exc


def _git_archive_bytes(root: Path, git_head: str, *, roots: tuple[PurePosixPath, ...]) -> bytes:
    pathspecs = [*_python_pathspecs(roots)]
    if _has_metadata(root, git_head):
        pathspecs.append(_METADATA_PATH.as_posix())
    try:
        completed = subprocess.run(
            ["git", "archive", "--format=tar", git_head, "--", *pathspecs],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError(f"cannot archive Git commit {git_head}") from exc
    return completed.stdout


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise SnapshotError(f"unsafe Git archive member: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SnapshotError(f"unsafe Git archive member: {name!r}")
    return path


def _materialize_archive(archive: bytes, destination: Path, *, roots: tuple[str, ...]) -> None:
    """Extract scoped Python files and optional commit-bound project metadata."""
    validated_roots = _validated_roots(roots)
    python_files = 0
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
                    if not any(
                        path.is_relative_to(root) or root.is_relative_to(path)
                        for root in validated_roots
                    ):
                        raise SnapshotError(f"unsupported Git archive member: {member.name!r}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                is_scoped_python = path.suffix == ".py" and any(
                    path.is_relative_to(root) for root in validated_roots
                )
                if not member.isfile() or (path != _METADATA_PATH and not is_scoped_python):
                    raise SnapshotError(f"unsupported Git archive member: {member.name!r}")
                source = stream.extractfile(member)
                if source is None:
                    raise SnapshotError(f"cannot read Git archive member: {member.name!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
                if is_scoped_python:
                    python_files += 1
    except (tarfile.TarError, OSError) as exc:
        raise SnapshotError(f"invalid Git archive: {exc}") from exc
    if python_files == 0:
        raise SnapshotError("Git archive contains no scoped Python sources")


@contextmanager
def materialize_git_snapshot(
    root: Path, revision: str, *, roots: tuple[str, ...]
) -> Iterator[ArchivedSnapshot]:
    """Yield a safely extracted Python snapshot for one resolved commit."""
    repository_root = root.resolve()
    validated_roots = _validated_roots(roots)
    git_head = resolve_commit(repository_root, revision)
    archive = _git_archive_bytes(repository_root, git_head, roots=validated_roots)
    with TemporaryDirectory(prefix="archkeel-snapshot-") as temporary:
        destination = Path(temporary)
        _materialize_archive(archive, destination, roots=roots)
        yield ArchivedSnapshot(root=destination, git_head=git_head)
