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
    return _has_file(root, git_head, _METADATA_PATH.as_posix())


def _has_file(root: Path, git_head: str, path: str) -> bool:
    try:
        return (
            subprocess.run(
                ["git", "cat-file", "-e", f"{git_head}:{path}"],
                cwd=root,
                capture_output=True,
            ).returncode
            == 0
        )
    except OSError as exc:
        raise SnapshotError(f"cannot inspect Git commit {git_head}") from exc


def _typescript_pathspecs(root: Path, git_head: str, tsconfig: str | None) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", git_head],
            cwd=root,
            check=True,
            capture_output=True,
        )
        paths = [item.decode("utf-8") for item in completed.stdout.split(b"\x00") if item]
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
        raise SnapshotError(
            f"cannot list TypeScript resolver inputs from Git commit {git_head}"
        ) from exc
    return [
        f":(top,literal){path}"
        for path in paths
        if PurePosixPath(path).suffix in _TS_RESOLVER_SUFFIXES
        or PurePosixPath(path).name in {"package.json", "tsconfig.json"}
        or (tsconfig is not None and path == tsconfig)
    ]


def _git_archive_bytes(
    root: Path,
    git_head: str,
    *,
    roots: tuple[PurePosixPath, ...],
    language: str = "python",
    tsconfig: str | None = None,
) -> bytes:
    if language == "python":
        pathspecs = [*_python_pathspecs(roots)]
        if _has_metadata(root, git_head):
            pathspecs.append(_METADATA_PATH.as_posix())
    elif language == "dart":
        pathspecs = [
            ":(glob,top)**/*.dart"
            if path == PurePosixPath(".")
            else f":(glob,top){path.as_posix()}/**/*.dart"
            for path in roots
        ]
        if _has_file(root, git_head, _PUBSPEC_PATH.as_posix()):
            pathspecs.append(_PUBSPEC_PATH.as_posix())
    elif language == "typescript":
        # Resolution can cross selected graph roots. Keep tracked resolver inputs from this
        # exact commit; the collector emits graph nodes only from configured roots.
        pathspecs = _typescript_pathspecs(root, git_head, tsconfig)
    else:
        raise SnapshotError(f"unsupported snapshot language: {language}")
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
