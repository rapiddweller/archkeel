# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Squash-merge a pull request only when its required checks are green (AD-676).

`python tools/merge_pr.py <number>`. It refuses unless the pull request is open, not a draft,
mergeable and up to date with its base, and each required check of the base branch has the
conclusion `success` on the head commit (not `skipped`, not missing, not pending). It never uses
`--admin` and never bypasses a hook. It merges with `--match-head-commit`, so a push after the
check cannot land. After the merge it reads the landing: a squash commit that changes no file
while the pull request changed files is an error (the empty landings of 2026-11-16).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable

Gh = Callable[..., str]
DEFAULT_REQUIRED = ("PR gate",)


def gh(*args: str) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout


def required_checks(run: Gh, base: str) -> list[str]:
    """The required status checks of the base branch; the default when GitHub lists none."""
    try:
        text = run(
            "api", f"repos/{{owner}}/{{repo}}/branches/{base}/protection/required_status_checks"
        )
        names = json.loads(text).get("contexts") or []
    except SystemExit:
        names = []
    return list(names) or list(DEFAULT_REQUIRED)


def refusals(pr: dict, required: list[str], runs: dict[str, str]) -> list[str]:
    """Each reason why the pull request must not merge now."""
    found = []
    if pr["state"] != "OPEN":
        found.append(f"the pull request is {pr['state']}")
    if pr["isDraft"]:
        found.append("the pull request is a draft")
    if pr["mergeable"] != "MERGEABLE":
        found.append(f"the pull request is {pr['mergeable']}: resolve the conflict")
    if pr["mergeStateStatus"] == "BEHIND":
        found.append("the head is behind its base: rebase it on main and let the checks run again")
    found += [
        f"required check '{name}' is {runs.get(name, 'missing')}, not success"
        for name in required
        if runs.get(name) != "success"
    ]
    return found


def check_conclusions(run: Gh, sha: str) -> dict[str, str]:
    text = run(
        "api",
        f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs",
        "--paginate",
        "--jq",
        ".check_runs[] | [.name, (.conclusion // .status)] | @tsv",
    )
    pairs = (line.split("\t") for line in text.splitlines() if line)
    return {name: state for name, state in pairs}


def landed(run: Gh, number: str, expected_files: int) -> str | None:
    """An error text when the merge commit of the pull request changes no file."""
    merged = json.loads(run("pr", "view", number, "--json", "mergeCommit"))
    oid = (merged.get("mergeCommit") or {}).get("oid")
    if not oid:
        return "GitHub names no merge commit"
    files = json.loads(run("api", f"repos/{{owner}}/{{repo}}/commits/{oid}"))["files"]
    if expected_files and not files:
        return (
            f"the merge commit {oid} changes no file, but the pull request changed {expected_files}"
        )
    return None


def main(argv: list[str], run: Gh = gh) -> int:
    number = argv[0]
    fields = "state,isDraft,mergeable,mergeStateStatus,headRefOid,baseRefName,changedFiles"
    pr = json.loads(run("pr", "view", number, "--json", fields))
    required = required_checks(run, pr["baseRefName"])
    reasons = refusals(pr, required, check_conclusions(run, pr["headRefOid"]))
    for reason in reasons:
        print(f"refused: {reason}", file=sys.stderr)
    if reasons:
        return 1
    run("pr", "merge", number, "--squash", "--match-head-commit", pr["headRefOid"])
    problem = landed(run, number, int(pr["changedFiles"]))
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    print(f"merged {number} at {pr['headRefOid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
