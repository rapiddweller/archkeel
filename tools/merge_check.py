# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check a pull request before its merge: its base, its conflicts and its changed files.

Run `make merge-check PR=<number>` before each merge. The check needs `gh` and network access.
It fails when the head conflicts with main, or when the head changes another set of files than
GitHub lists for the pull request. A branch that is behind main is only a warning: the process
does not require an up-to-date branch. A file that main changed in its last merges is a warning
only when the pull request removes lines from it: that is what a revert looks like. An append is
a normal change.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

BASE = "origin/main"
RECENT_MERGES = 10


class MergeCheckError(Exception):
    """A step of the check cannot run. The message names the step."""


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.errors)


def _git(repo: Path, *args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode not in ok:
        raise MergeCheckError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _names(output: str) -> set[str]:
    return {name for name in output.split("\0") if name}


def is_ancestor(repo: Path, base: str, head: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", base, head, ok=(0, 1)).returncode == 0


def conflicting_files(repo: Path, base: str, head: str) -> list[str]:
    """The files that conflict when `head` merges into `base`; an empty list when none does."""
    result = _git(
        repo,
        "merge-tree",
        "--write-tree",
        "--name-only",
        "--no-messages",
        base,
        head,
        ok=(0, 1),
    )
    if result.returncode == 0:
        return []
    # The first line is the tree object. The conflicted paths follow, one per line.
    return [line for line in result.stdout.splitlines()[1:] if line]


@dataclass
class Changes:
    """The files that the branch changes since it left `base`, with rename detection on."""

    paths: set[str] = field(default_factory=set)
    # New path -> old path, for each renamed file. GitHub lists the same pairs as previous_filename.
    renamed_from: dict[str, str] = field(default_factory=dict)

    @property
    def touched(self) -> set[str]:
        """Every path that the branch touches: the new and the old path of each rename."""
        return self.paths | set(self.renamed_from.values())


def branch_changes(repo: Path, base: str, head: str) -> Changes:
    """Read `git diff --name-status`. A rename gives the new path and the old path."""
    output = _git(repo, "diff", "--name-status", "-z", "-M", f"{base}...{head}").stdout
    tokens = [token for token in output.split("\0") if token]
    changes = Changes()
    index = 0
    while index < len(tokens):
        status = tokens[index]
        if status[:1] in ("R", "C"):
            old, new = tokens[index + 1], tokens[index + 2]
            index += 3
            changes.paths.add(new)
            if status[:1] == "R":
                changes.renamed_from[new] = old
        else:
            changes.paths.add(tokens[index + 1])
            index += 2
    return changes


def files_with_removed_lines(repo: Path, base: str, head: str) -> set[str]:
    """The files from which the branch removes lines. A binary file counts as a removal."""
    output = _git(repo, "diff", "--numstat", "-z", "--no-renames", f"{base}...{head}").stdout
    names = set()
    for entry in output.split("\0"):
        parts = entry.split("\t", 2)
        if len(parts) == 3 and parts[1] != "0":
            names.add(parts[2])
    return names


def recently_changed(repo: Path, base: str) -> set[str]:
    """The files that the last merges on `base` changed."""
    output = _git(
        repo,
        "log",
        f"-{RECENT_MERGES}",
        "--first-parent",
        "--no-renames",
        "--name-only",
        "-z",
        "--format=",
        base,
    ).stdout
    return _names(output)


def check(
    repo: Path,
    base: str,
    head: str,
    pr_files: list[str],
    renamed_from: Mapping[str, str] | None = None,
) -> Report:
    """Compare `head` with `base` and with the files that GitHub lists for the pull request.

    `renamed_from` maps each new path that GitHub lists as renamed to its previous path.
    """
    report = Report()
    if not is_ancestor(repo, base, head):
        report.warnings.append(f"{base} is not an ancestor of the head: the branch is behind")
    for name in conflicting_files(repo, base, head):
        report.errors.append(f"conflict with {base}: {name}")
    # Both sides give the touched paths. A rename touches its old and its new path, so git and
    # GitHub agree whether they report a rename or a delete and an add.
    local = branch_changes(repo, base, head)
    listed = set(pr_files) | set((renamed_from or {}).values())
    for name in sorted(local.touched - listed):
        report.errors.append(f"changed in the branch but not listed by GitHub: {name}")
    for name in sorted(listed - local.touched):
        report.errors.append(f"listed by GitHub but not changed in the branch: {name}")
    # Only the new path counts: removing the old path of a rename is a move, not a revert.
    removed = files_with_removed_lines(repo, base, head)
    for name in sorted(local.paths & recently_changed(repo, base) & removed):
        report.warnings.append(
            f"{name} also changed on {base} in its last {RECENT_MERGES} merges and the branch "
            "removes lines from it: check for a revert"
        )
    return report


def _gh(*args: str) -> str:
    """Run `gh` and return its standard output. Any failure raises MergeCheckError."""
    command = f"gh {' '.join(args)}"
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except OSError as error:
        raise MergeCheckError(f"{command} cannot run: {error}") from error
    if result.returncode != 0:
        raise MergeCheckError(f"{command} failed: {result.stderr.strip()}")
    return result.stdout


def parse_pr_files(output: str) -> tuple[list[str], dict[str, str]]:
    """Read the file lines of `gh api ... --jq`: one JSON object per file.

    Return the listed paths and, for each renamed file, its new path mapped to its previous path.
    """
    paths: list[str] = []
    renamed_from: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            path = str(item["path"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise MergeCheckError(f"unexpected line from gh api: {line!r}") from error
        paths.append(path)
        if item.get("status") == "renamed" and item.get("previous"):
            renamed_from[path] = str(item["previous"])
    return paths, renamed_from


def pr_view(number: int) -> tuple[str, list[str], dict[str, str]]:
    """The head commit, the listed file paths and the renames that GitHub lists for the PR."""
    try:
        head = str(json.loads(_gh("pr", "view", str(number), "--json", "headRefOid"))["headRefOid"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise MergeCheckError(f"gh pr view {number} gave no head commit") from error
    jq = ".[] | {path: .filename, status: .status, previous: .previous_filename}"
    files = _gh(
        "api", "--paginate", "--jq", jq, "repos/{owner}/{repo}/pulls/" + str(number) + "/files"
    )
    paths, renamed_from = parse_pr_files(files)
    return head, paths, renamed_from


def fetch_pr(repo: Path, number: int) -> str:
    """Fetch `origin/main` and the pull request head; return the fetched head commit."""
    _git(repo, "fetch", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin", f"pull/{number}/head")
    return _git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()


def main(argv: list[str] | None = None, *, repo: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a pull request before its merge.")
    parser.add_argument("number", type=int, help="pull request number")
    args = parser.parse_args(argv)
    root = repo if repo is not None else Path.cwd()
    try:
        expected_head, pr_files, renamed_from = pr_view(args.number)
        head = fetch_pr(root, args.number)
        if head != expected_head:
            raise MergeCheckError(
                f"the head of PR {args.number} moved while the check ran: run the check again"
            )
        report = check(root, BASE, head, pr_files, renamed_from)
    except MergeCheckError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for message in report.errors:
        print(f"error: {message}")
    for message in report.warnings:
        print(f"warning: {message}")
    print(
        f"merge-check PR {args.number}: {len(report.errors)} error(s), "
        f"{len(report.warnings)} warning(s)"
    )
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
