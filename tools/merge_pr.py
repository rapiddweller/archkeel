# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Squash-merge a pull request only when its required checks are green (AD-676, AD-736).

`python tools/merge_pr.py <number> [--json] [--wait SECONDS]`. One decision table (`decide`) gives
a verdict for the pull request: MERGE, WAIT or REFUSE, each with reason codes and the next step.
The check table of GitHub keeps `status` (queued, in progress, completed) apart from `conclusion`
(success, failure, ...): a check that is not completed is WAIT, a completed check that is not a
success is REFUSE. UNKNOWN in `mergeable` or `mergeStateStatus` is WAIT: GitHub has not computed it.
The tool never uses `--admin` and never bypasses a hook. It merges with `--match-head-commit`, so a
push after the check cannot land. After the merge it reads the landing: a squash commit that
changes no file while the pull request changed files is an error (the empty landings of 2026-11-16).

Exit codes: 0 merged, 1 refused, 2 empty landing, 3 wait, 4 merged but the landing is not yet
visible. `tools/merge_check.py` uses the same table and adds its local file checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Gh = Callable[..., str]
MERGE, WAIT, REFUSE = "MERGE", "WAIT", "REFUSE"
DEFAULT_REQUIRED = ("PR gate",)
PENDING = {"queued", "in_progress", "pending", "waiting", "requested"}
EXIT = {MERGE: 0, REFUSE: 1, WAIT: 3}


@dataclass(frozen=True)
class Reason:
    code: str
    detail: str
    verdict: str = REFUSE


@dataclass
class Decision:
    verdict: str = MERGE
    reasons: list[Reason] = field(default_factory=list)

    def add(self, verdict: str, code: str, detail: str) -> None:
        """REFUSE beats WAIT, and WAIT beats MERGE."""
        order = {MERGE: 0, WAIT: 1, REFUSE: 2}
        if order[verdict] > order[self.verdict]:
            self.verdict = verdict
        self.reasons.append(Reason(code, detail, verdict))


def gh(*args: str) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout


def required_checks(run: Gh, base: str) -> tuple[list[str], str]:
    """The required status checks of the base branch and their source: protection or default."""
    try:
        path = f"repos/{{owner}}/{{repo}}/branches/{base}/protection/required_status_checks"
        names = json.loads(run("api", path)).get("contexts") or []
    except SystemExit:
        names = []
    return (list(names), "protection") if names else (list(DEFAULT_REQUIRED), "default")


def decide(pr: dict, required: list[str], runs: dict[str, tuple[str, str]]) -> Decision:
    """The decision table. `runs` maps a check name to (status, conclusion), both lower case."""
    d = Decision()
    if pr["state"] != "OPEN":
        d.add(REFUSE, "not_open", f"the pull request is {pr['state']}: nothing to merge")
    if pr["isDraft"]:
        d.add(REFUSE, "draft", "mark the pull request ready for review (gh pr ready)")
    if pr["mergeable"] == "CONFLICTING" or pr["mergeStateStatus"] == "DIRTY":
        d.add(REFUSE, "conflict", "the head conflicts with its base: rebase it on main and push")
    elif pr["mergeable"] == "UNKNOWN" or pr["mergeStateStatus"] == "UNKNOWN":
        d.add(WAIT, "mergeability_unknown", "GitHub has not computed the merge state: retry")
    for name in required:
        if name not in runs:
            d.add(REFUSE, "check_missing", f"no run of '{name}' on the head: push or re-run it")
            continue
        status, conclusion = runs[name]
        if status != "completed":
            d.add(WAIT, "check_pending", f"'{name}' is {status or 'pending'}: wait for it")
        elif conclusion != "success":
            d.add(REFUSE, "check_failed", f"'{name}' concluded {conclusion}: fix it and push")
    if pr["mergeStateStatus"] == "BLOCKED" and d.verdict == MERGE:
        d.add(REFUSE, "blocked", "GitHub reports the merge state BLOCKED by a rule of the branch")
    return d


def check_runs(run: Gh, sha: str) -> dict[str, tuple[str, str]]:
    text = run(
        "api",
        f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs",
        "--paginate",
        "--jq",
        '.check_runs[] | [.name, .status, (.conclusion // "")] | @tsv',
    )
    found: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        if line:
            name, status, conclusion = line.split("\t")
            found[name] = (status, conclusion)
    return found


FIELDS = "state,isDraft,mergeable,mergeStateStatus,headRefOid,baseRefName,changedFiles"


def assess(run: Gh, number: str) -> tuple[Decision, dict, tuple[list[str], str]]:
    """Read the pull request and decide: the decision, the pull request and the required set."""
    pr = json.loads(run("pr", "view", number, "--json", FIELDS))
    required = required_checks(run, pr["baseRefName"])
    return decide(pr, required[0], check_runs(run, pr["headRefOid"])), pr, required


def landed(run: Gh, number: str, expected_files: int) -> tuple[int, str | None]:
    """0 when the merge commit changes files; 2 for an empty landing; 4 if it is not visible yet."""
    merged = json.loads(run("pr", "view", number, "--json", "mergeCommit"))
    oid = (merged.get("mergeCommit") or {}).get("oid")
    if not oid:
        return 4, "GitHub names no merge commit yet: look again with gh pr view"
    try:
        files = json.loads(run("api", f"repos/{{owner}}/{{repo}}/commits/{oid}"))["files"]
    except SystemExit:
        return 4, f"the merge commit {oid} is not readable yet: look again"
    if expected_files and not files:
        return 2, f"the merge commit {oid} changes no file, but the pull request changed files"
    return 0, None


def report(decision: Decision, pr: dict, required: tuple[list[str], str], as_json: bool) -> None:
    if as_json:
        document = {
            "verdict": decision.verdict,
            "reasons": [{"code": r.code, "detail": r.detail} for r in decision.reasons],
            "required": {"names": required[0], "source": required[1]},
            "head": pr["headRefOid"],
        }
        print(json.dumps(document))
        return
    for reason in decision.reasons:
        print(f"{decision.verdict.lower()}: [{reason.code}] {reason.detail}", file=sys.stderr)
    print(f"required checks ({required[1]}): {', '.join(required[0])}", file=sys.stderr)


def main(argv: list[str], run: Gh = gh, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description="Merge a pull request only on green.")
    parser.add_argument("number")
    parser.add_argument("--json", action="store_true", help="print the decision as JSON")
    parser.add_argument("--wait", type=int, default=0, help="seconds to loop while WAIT")
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.wait
    decision, pr, required = assess(run, args.number)
    while decision.verdict == WAIT and time.monotonic() < deadline:
        sleep(10)
        decision, pr, required = assess(run, args.number)
    if decision.verdict != MERGE:
        report(decision, pr, required, args.json)
        return EXIT[decision.verdict]
    run("pr", "merge", args.number, "--squash", "--match-head-commit", pr["headRefOid"])
    code, problem = landed(run, args.number, int(pr["changedFiles"]))
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return code
    if args.json:
        report(decision, pr, required, True)
    else:
        print(f"merged {args.number} at {pr['headRefOid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
