# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read immutable Git inputs and check the declaration commit's shape."""

import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from .snapshot import resolve_commit


class GitError(ValueError):
    """The repository cannot supply the required immutable evidence."""


def git_bytes(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitError(f"Git evidence unavailable: {' '.join(args[:2])}") from exc


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or any(c in value for c in "\x00\\:")
    ):
        raise GitError(f"unsafe repository path: {value!r}")
    return path.as_posix()


def read_blob(root: Path, revision: str, path: str) -> bytes:
    path = relative_path(path)
    entry = git_bytes(root, "ls-tree", "-z", revision, "--", path).split(b"\0")
    entries = [item.split(b"\t", 1) for item in entry if item]
    if len(entries) != 1 or entries[0][1].decode() != path:
        raise GitError(f"missing regular Git blob: {path}")
    mode, kind, oid = entries[0][0].split()
    if mode not in {b"100644", b"100755"} or kind != b"blob":
        raise GitError(f"expected a regular Git blob: {path}")
    return git_bytes(root, "cat-file", "blob", oid.decode())


def archive_excluded(root: Path, paths: Iterable[str]) -> frozenset[str]:
    """The working-tree paths `git archive` never writes: untracked ignored files and files
    marked `export-ignore`. A snapshot of a commit cannot hold them, so a comparison of that
    snapshot with the working tree has to leave them out (AD-100).
    """
    listed = "".join(f"{relative_path(path)}\0" for path in paths)
    ignored = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=root,
        input=listed,
        capture_output=True,
        text=True,
    )
    attributes = subprocess.run(
        ["git", "check-attr", "-z", "--stdin", "export-ignore"],
        cwd=root,
        input=listed,
        capture_output=True,
        text=True,
    )
    # check-ignore exits 1 when nothing is ignored; anything else is a failure.
    if ignored.returncode not in {0, 1} or attributes.returncode != 0:
        raise GitError("Git ignore rules or attributes could not be read")
    ignored_paths: str = ignored.stdout
    # check-attr -z answers `path NUL attribute NUL value NUL` per path.
    answers: str = attributes.stdout
    fields = answers.split("\0")
    exported = {
        path
        for path, _, value in zip(fields[0::3], fields[1::3], fields[2::3], strict=False)
        if value == "set"
    }
    return frozenset({path for path in ignored_paths.split("\0") if path} | exported)


def changed_paths(root: Path, before: str, after: str) -> set[str]:
    return {
        value.decode()
        for value in git_bytes(
            root, "diff", "--no-renames", "--name-only", "-z", before, after, "--"
        ).split(b"\0")
        if value
    }


def parents(root: Path, commit: str) -> list[str]:
    return git_bytes(root, "show", "-s", "--format=%P", commit).decode().split()


def is_ancestor(root: Path, before: str, after: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", before, after], cwd=root, capture_output=True
    )
    if result.returncode not in {0, 1}:
        raise GitError("Git ancestry could not be checked")
    return result.returncode == 0


def remote_tip(root: Path, branch: str) -> str:
    git_bytes(root, "check-ref-format", f"refs/heads/{branch}")
    return resolve_commit(root, f"refs/remotes/origin/{branch}")


def check_git_order(
    root: Path, *, baseline: str, expectation: str, head: str, expected_path: str, branch: str
) -> tuple[str, ...]:
    failures = []
    if parents(root, expectation) != [baseline]:
        failures.append("expectation commit must have exactly baseline as parent")
    if changed_paths(root, baseline, expectation) != {relative_path(expected_path)}:
        failures.append("expectation commit must change only the expectation file")
    if not is_ancestor(root, expectation, head):
        failures.append("expectation commit must be an ancestor of candidate")
    if not is_ancestor(root, expectation, remote_tip(root, branch)):
        failures.append("expectation commit must exist on the supplied origin branch")
    if read_blob(root, expectation, expected_path) != read_blob(root, head, expected_path):
        failures.append("candidate changed the published expectation")
    return tuple(failures)
