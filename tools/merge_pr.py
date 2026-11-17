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
# AD-736: the owner rule "ask before you delete anything", enforced by the tool.
NET_REMOVAL_LIMIT = 300
RATCHET_FILES = ("native/expected-gaps.json", "native/expected-growth.json")
RATCHET_REMOVAL_LIMIT = 50
DELETION_LABEL = "deletion-approved"
RATCHET_LABEL = "ratchet-lead"


@dataclass(frozen=True)
class Reason:
    code: str
    detail: str
    verdict: str = REFUSE


@dataclass
class Changes:
    """What the pull request changes: its files, its labels and the entries of the ratchet files.

    `files` holds `{filename, status, additions, deletions}` of the pull request API. `entries`
    maps a ratchet file to (entries at the merge base, entries at the head).
    """

    files: list[dict] = field(default_factory=list)
    labels: set[str] = field(default_factory=set)
    entries: dict[str, tuple[int, int]] = field(default_factory=dict)


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


def decide(
    pr: dict,
    required: list[str],
    runs: dict[str, tuple[str, str]],
    changes: Changes | None = None,
) -> Decision:
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
    if changes is not None:
        for code, detail in deletions(changes):
            d.add(REFUSE, code, detail)
    if pr["mergeStateStatus"] == "BLOCKED" and d.verdict == MERGE:
        # GitHub updates the state a few seconds after the last required check turned green. If
        # it stays BLOCKED, a rule of the branch other than a check blocks the merge.
        d.add(
            WAIT,
            "blocked",
            "GitHub still reports BLOCKED with green checks: retry, then look at the rules",
        )
    return d


def deletions(changes: Changes) -> list[tuple[str, str]]:
    """The refusals of the deletion guard: a removed file, a net removal, a ratchet removal."""
    found: list[tuple[str, str]] = []
    removed = [item["filename"] for item in changes.files if item.get("status") == "removed"]
    net = sum(int(item["deletions"]) - int(item["additions"]) for item in changes.files)
    if (removed or net > NET_REMOVAL_LIMIT) and DELETION_LABEL not in changes.labels:
        names = ", ".join(removed[:3]) + (" and more" if len(removed) > 3 else "")
        what = f"deletes {len(removed)} file(s) ({names}) and " if removed else ""
        found.append(
            (
                "deletion_unapproved",
                f"the pull request {what}removes {net} lines net (limit {NET_REMOVAL_LIMIT}): "
                f"ask the lead; only the lead sets '{DELETION_LABEL}' after owner approval",
            )
        )
    for path, (before, after) in sorted(changes.entries.items()):
        if before - after > RATCHET_REMOVAL_LIMIT and RATCHET_LABEL not in changes.labels:
            found.append(
                (
                    "ratchet_removal_unapproved",
                    f"{path} loses {before - after} entries (limit {RATCHET_REMOVAL_LIMIT}): "
                    f"only the lead sets the label '{RATCHET_LABEL}'",
                )
            )
    return found


def entry_count(text: str) -> int:
    """The entries of a ratchet file: gaps, violations, rules, unknown reasons, raised items."""
    document = json.loads(text)
    return sum(len(v) for k, v in document.items() if isinstance(v, (list, dict)))


def read_changes(run: Gh, number: str, pr: dict) -> Changes:
    """Read the file list, the labels and the ratchet files at the merge base and at the head."""
    text = run(
        "api",
        f"repos/{{owner}}/{{repo}}/pulls/{number}/files",
        "--paginate",
        "--jq",
        ".[] | {filename, status, additions, deletions}",
    )
    files = [json.loads(line) for line in text.splitlines() if line.strip()]
    labels = json.loads(run("pr", "view", number, "--json", "labels"))["labels"]
    changes = Changes(files=files, labels={item["name"] for item in labels})
    touched = [item["filename"] for item in files if item["filename"] in RATCHET_FILES]
    if not touched:
        return changes
    compare = f"repos/{{owner}}/{{repo}}/compare/{pr['baseRefName']}...{pr['headRefOid']}"
    base = json.loads(run("api", compare, "--jq", "{sha: .merge_base_commit.sha}"))["sha"]

    def content(path: str, ref: str) -> str:
        url = f"repos/{{owner}}/{{repo}}/contents/{path}?ref={ref}"
        return run("api", "-H", "Accept: application/vnd.github.raw", url)

    for path in touched:
        changes.entries[path] = (
            entry_count(content(path, base)),
            entry_count(content(path, pr["headRefOid"])),
        )
    return changes


def check_runs(run: Gh, sha: str) -> dict[str, tuple[str, str]]:
    """The newest run of each check name on the commit: (status, conclusion).

    A re-run adds a second check run with the same name. The newest one counts (the highest id),
    whether it is done or still running: an older green run does not stand for a newer red one,
    and a fresh green re-run is not hidden by an older red one (#1653).
    """
    text = run(
        "api",
        f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs",
        "--paginate",
        "--jq",
        '.check_runs[] | [.id, .name, .status, (.conclusion // "")] | @tsv',
    )
    newest: dict[str, tuple[int, str, str]] = {}
    for line in text.splitlines():
        if line:
            run_id, name, status, conclusion = line.split("\t")
            if name not in newest or int(run_id) > newest[name][0]:
                newest[name] = (int(run_id), status, conclusion)
    return {name: (status, conclusion) for name, (_id, status, conclusion) in newest.items()}


FIELDS = "state,isDraft,mergeable,mergeStateStatus,headRefOid,baseRefName,changedFiles"


def assess(run: Gh, number: str) -> tuple[Decision, dict, tuple[list[str], str]]:
    """Read the pull request and decide: the decision, the pull request and the required set."""
    pr = json.loads(run("pr", "view", number, "--json", FIELDS))
    required = required_checks(run, pr["baseRefName"])
    changes = read_changes(run, number, pr)
    return decide(pr, required[0], check_runs(run, pr["headRefOid"]), changes), pr, required


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
