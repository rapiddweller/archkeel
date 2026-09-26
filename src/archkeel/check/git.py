# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read immutable Git inputs and check the declaration commit's shape."""

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .snapshot import resolve_commit


class GitError(ValueError):
    """The repository cannot supply the required immutable evidence."""


@dataclass(eq=False)
class MissingBlobError(GitError):
    """The revision's tree holds nothing at `path`, its repository path: an absent file, which
    `validate --against` decides on (AD-104), not one Git holds but cannot hand over."""

    path: str

    def __str__(self) -> str:
        return f"missing regular Git blob: {self.path}"


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


def _repository_path(root: Path, path: str) -> str:
    """`path`, relative to `root`, as the path from the repository's top level, for a message.

    `root` may sit below the top level, as `--root mobile` does. A directory name that is not
    UTF-8 shows its undecodable bytes as U+FFFD instead of stopping the message.
    """
    prefix: str = str(git_bytes(root, "rev-parse", "--show-prefix"), "utf-8", "replace")
    return prefix.rstrip("\n") + path


def read_blob(root: Path, revision: str, path: str) -> bytes:
    """The regular file `path`, relative to `root`, at `revision`; an error names its path from
    the repository's top level, so a message names the blob Git was asked for."""
    path = relative_path(path)
    entry = git_bytes(root, "ls-tree", "-z", revision, "--", path).split(b"\0")
    entries = [item.split(b"\t", 1) for item in entry if item]
    if len(entries) != 1 or entries[0][1].decode() != path:
        raise MissingBlobError(_repository_path(root, path))
    mode, kind, oid = entries[0][0].split()
    if mode not in {b"100644", b"100755"} or kind != b"blob":
        raise GitError(f"expected a regular Git blob: {_repository_path(root, path)}")
    return git_bytes(root, "cat-file", "blob", oid.decode())


def _listed_paths(root: Path, *args: str) -> frozenset[str]:
    try:
        listed: str = str(git_bytes(root, *args), "utf-8")
    except UnicodeDecodeError as error:
        # A path no reader can match is missing evidence, the same as a failed Git call.
        raise GitError(f"Git listed a path that is not UTF-8: {' '.join(args[:2])}") from error
    return frozenset(path for path in listed.split("\0") if path)


def working_tree_paths(root: Path, roots: tuple[str, ...]) -> frozenset[str]:
    """Every file under `roots` in Git's view of the working tree: the tracked ones and the
    untracked ones no ignore rule excludes. A file inside a submodule is in neither (AD-100)."""
    return _listed_paths(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *roots
    )


def tracked_paths(root: Path, revision: str, roots: tuple[str, ...]) -> frozenset[str]:
    """Every file `revision` tracks under `roots`, whatever its archive later leaves out."""
    return _listed_paths(root, "ls-tree", "-r", "-z", "--name-only", revision, "--", *roots)


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
