# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Safely materialize language inputs from one Git commit."""

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
_PUBSPEC_PATH = PurePosixPath("pubspec.yaml")
_TS_RESOLVER_SUFFIXES = frozenset(
    {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".json"}
)
_LANGUAGE_SUFFIXES = {
    "python": frozenset({".py"}),
    "dart": frozenset({".dart"}),
    "typescript": frozenset({".ts", ".tsx", ".mts", ".cts"}),
}


class SnapshotError(RuntimeError):
    """Raised when a revision cannot be materialized without ambiguity."""


@dataclass(frozen=True)
class ArchivedSnapshot:
    """One temporary language snapshot and its resolved commit."""

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


def _git_archive_bytes(
    root: Path,
    git_head: str,
    *,
    roots: tuple[PurePosixPath, ...],
    language: str = "python",
    tsconfig: str | None = None,
) -> bytes:
    """Build a tar from tree blobs; Git export attributes must not change evidence."""
    if language not in _LANGUAGE_SUFFIXES:
        raise SnapshotError(f"unsupported snapshot language: {language}")
    metadata_path = _METADATA_PATH if language == "python" else _PUBSPEC_PATH
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
                if language == "typescript" and not (
                    raw_path.endswith(tuple(suffix.encode() for suffix in _TS_RESOLVER_SUFFIXES))
                    or (tsconfig is not None and raw_path == tsconfig.encode())
                ):
                    continue
                if (
                    language != "typescript"
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
                    if language == "typescript"
                    else path == _PUBSPEC_PATH
                    if language == "dart"
                    else path == _METADATA_PATH
                )
                if not scoped and not resolver:
                    continue
                _safe_member_path(name)
                mode, kind, oid = metadata.split()
                if mode not in {b"100644", b"100755"} or kind != b"blob":
                    raise SnapshotError(f"expected a regular Git blob: {name!r}")
                payload = subprocess.run(
                    ["git", "cat-file", "blob", oid.decode("ascii")],
                    cwd=root,
                    check=True,
                    capture_output=True,
                ).stdout
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                stream.addfile(member, io.BytesIO(payload))
        return buffer.getvalue()
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError, ValueError) as exc:
        raise SnapshotError(f"cannot read snapshot blobs from Git commit {git_head}") from exc


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
    language: str = "python",
    tsconfig: str | None = None,
) -> None:
    """Extract scoped sources and commit-bound resolver inputs for one language."""
    if language not in _LANGUAGE_SUFFIXES:
        raise SnapshotError(f"unsupported snapshot language: {language}")
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
                    if language != "typescript" and not any(
                        path.is_relative_to(root) or root.is_relative_to(path)
                        for root in validated_roots
                    ):
                        raise SnapshotError(f"unsupported Git archive member: {member.name!r}")
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                is_scoped_source = path.suffix in _LANGUAGE_SUFFIXES[language] and any(
                    path.is_relative_to(root) for root in validated_roots
                )
                if language == "python":
                    allowed_metadata = path == _METADATA_PATH
                elif language == "dart":
                    allowed_metadata = path == _PUBSPEC_PATH
                else:
                    allowed_metadata = path.name in {"package.json", "tsconfig.json"} or (
                        tsconfig is not None and path.as_posix() == tsconfig
                    )
                resolver_input = language == "typescript" and path.suffix in _TS_RESOLVER_SUFFIXES
                if not member.isfile() or not (
                    is_scoped_source or allowed_metadata or resolver_input
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


@contextmanager
def materialize_git_snapshot(
    root: Path,
    revision: str,
    *,
    roots: tuple[str, ...],
    language: str = "python",
    tsconfig: str | None = None,
) -> Iterator[ArchivedSnapshot]:
    """Yield a safely extracted language snapshot for one resolved commit."""
    repository_root = root.resolve()
    validated_roots = _validated_roots(roots)
    git_head = resolve_commit(repository_root, revision)
    archive = _git_archive_bytes(
        repository_root, git_head, roots=validated_roots, language=language, tsconfig=tsconfig
    )
    with TemporaryDirectory(prefix="archkeel-snapshot-") as temporary:
        destination = Path(temporary)
        _materialize_archive(
            archive, destination, roots=roots, language=language, tsconfig=tsconfig
        )
        yield ArchivedSnapshot(root=destination, git_head=git_head)
