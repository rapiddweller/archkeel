# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check a pull request before its merge: its base, its conflicts and its changed files.

Run `make merge-check PR=<number>` before each merge. The check needs `gh` and network access.
It fails when main is not an ancestor of the pull request head, when the head conflicts with
main, or when the head changes another set of files than GitHub lists for the pull request.
A file that main changed in its last merges is only a warning: it can be a revert, or a
normal change to the same file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def changed_files(repo: Path, base: str, head: str) -> set[str]:
    """The files that the branch changes since it left `base`."""
    return _names(
        _git(repo, "diff", "--name-only", "-z", "--no-renames", f"{base}...{head}").stdout
    )


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


def check(repo: Path, base: str, head: str, pr_files: list[str]) -> Report:
    """Compare `head` with `base` and with the files that GitHub lists for the pull request."""
    report = Report()
    if not is_ancestor(repo, base, head):
        report.errors.append(
            f"{base} is not an ancestor of the head: update the branch from {base}"
        )
    for name in conflicting_files(repo, base, head):
        report.errors.append(f"conflict with {base}: {name}")
    local = changed_files(repo, base, head)
    listed = set(pr_files)
    for name in sorted(local - listed):
        report.errors.append(f"changed in the branch but not listed by GitHub: {name}")
    for name in sorted(listed - local):
        report.errors.append(f"listed by GitHub but not changed in the branch: {name}")
    for name in sorted(local & recently_changed(repo, base)):
        report.warnings.append(
            f"{name} also changed on {base} in its last {RECENT_MERGES} merges: check for a revert"
        )
    return report


def pr_view(number: int) -> tuple[str, list[str]]:
    """The head commit and the changed file paths that GitHub lists for the pull request."""
    result = subprocess.run(
        ["gh", "pr", "view", str(number), "--json", "headRefOid,files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MergeCheckError(f"gh pr view {number} failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return str(data["headRefOid"]), [str(item["path"]) for item in data["files"]]


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
        expected_head, pr_files = pr_view(args.number)
        head = fetch_pr(root, args.number)
        if head != expected_head:
            raise MergeCheckError(
                f"the head of PR {args.number} moved while the check ran: run the check again"
            )
        report = check(root, BASE, head, pr_files)
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
