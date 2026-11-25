# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The gate of the shell self-check (AD-478, AD-1064).

Run: `python tools/self_check_shell.py <result.json> <contract.json> [--base <ref>]
[--report-only] [--no-compare] [--summary-file F]`. `make self-validate-shell` calls it.

The result must be clean (no refusal, FAIL or violation, a true exit code), have no gap, and have
all rules PASS. Its rule ids must equal the rule ids of the contract file, as lists: a duplicate or
a non-string id is red. The contract must also keep each rule id that the contract of the merge
base of `--base` and HEAD has. A rule that is gone is growth: it passes only with the label
`ratchet-lead` and the PR text line `Ratchet growth (shell): <N> items: <reason>` (RATCHET_LABELED
and RATCHET_BODY_FILE, as in the native gate). The native gate reads the line without `(shell)`.
A new rule is no growth. A base contract that cannot be
read is red with the reason. `SHELL_BASE_CONTRACT=<file>` replaces the base. `--no-compare` (the
nightly run) skips the base. `--report-only` (main CI) prints growth and exits 0 for it.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from self_check_diff import LABEL, Unusable, absolute, approval, load, report, show, summary
from self_check_gate import git


def rule_ids(text: str, name: str) -> list[str]:
    """The rule ids of a contract, in order; raise `Unusable` when the contract has no clean ids."""
    try:
        ids = [rule["id"] for rule in json.loads(text)["rules"]]
    except (ValueError, KeyError, TypeError) as error:
        raise Unusable(f"{name} is not a contract with rules ({error})") from error
    if not all(isinstance(one, str) and one for one in ids):
        raise Unusable(f"{name} has a rule whose id is not a non-empty string")
    return [str(one) for one in ids]


def doubled(counts: Counter[str]) -> list[str]:
    return sorted(name for name, count in counts.items() if count > 1)


def result_duplicates(path: str) -> list[str]:
    """The rule ids that the result file lists twice (a JSON object keeps only the last)."""
    found: list[str] = []

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        names = Counter(key for key, _ in pairs)
        found.extend(key for key, count in names.items() if count > 1)
        return dict(pairs)

    try:
        frame = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=hook)
        rules = frame.get("frame", {}).get("rules", {}) if isinstance(frame, dict) else {}
        return sorted(set(found) & set(rules))
    except (OSError, ValueError, AttributeError):
        return []


def base_ids(contract: str, ref: str) -> list[str]:
    """The rule ids of the contract at the merge base; raise `Unusable` with the reason."""
    if os.environ.get("SHELL_BASE_CONTRACT"):
        name = os.environ["SHELL_BASE_CONTRACT"]
        try:
            return rule_ids(Path(name).read_text(encoding="utf-8"), name)
        except OSError as error:
            raise Unusable(f"{name} is unreadable ({error.strerror})") from error
    if not ref:
        raise Unusable("no base ref; set PR_BASE or SHELL_BASE_CONTRACT=<file>")
    sha = git("merge-base", ref, "HEAD")
    return rule_ids(git("show", f"{sha}:{contract}"), f"{contract} at {sha[:12]}")


def check(result_path: str, contract: str, argv: list[str]) -> int:
    def option(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv else ""

    try:
        found = load(result_path)
        wanted = rule_ids(Path(contract).read_text(encoding="utf-8"), contract)
    except (Unusable, OSError) as error:
        show(f"FAIL {error}")
        return 1
    errors = absolute(found)
    if not errors:
        if set(found["rules"].values()) != {"PASS"} or found["gaps"]:
            errors.append("the result must have all rules PASS and no gap")
        errors += [
            f"rule id {name} is listed twice in the contract" for name in doubled(Counter(wanted))
        ]
        errors += [
            f"rule id {name} is listed twice in the result"
            for name in result_duplicates(result_path)
        ]
        errors += [
            f"rule {r} of the contract has no row in the result"
            for r in sorted(set(wanted) - set(found["rules"]))
        ]
        errors += [
            f"rule {r} is in the result and not in the contract"
            for r in sorted(set(found["rules"]) - set(wanted))
        ]
    if not found.get("refusal"):
        show(summary(found))
    items: list[tuple[str, str]] = []
    growth: list[str] = []
    if "--no-compare" not in argv:
        try:
            gone = sorted(set(base_ids(contract, option("--base"))) - set(wanted))
            items = [(f"GROWN rule removed: {name}",) * 2 for name in gone]
            if items:
                labels = [LABEL] if os.environ.get("RATCHET_LABELED") == "true" else []
                file = os.environ.get("RATCHET_BODY_FILE", "")
                body = (
                    Path(file).read_text(encoding="utf-8") if file and Path(file).is_file() else ""
                )
                growth = approval(len(items), labels, body, shell=True)
        except Unusable as error:
            errors.append(f"the base contract is unavailable: {error}")
    show(f"shell self-check diff: grown {len(items)}")
    report(
        items,
        errors + growth,
        "",
        option("--summary-file") or os.environ.get("GITHUB_STEP_SUMMARY", ""),
    )
    for line in errors + growth:
        show(f"FAIL {line}")
    if errors or growth:
        show("Run `make self-validate-shell` to see the same result on your machine.")
    return 1 if errors or (growth and "--report-only" not in argv) else 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    code = check(argv[0], argv[1], argv)
    print(
        "shell self-check gate: GREEN" if code == 0 else f"shell self-check gate: RED (exit {code})"
    )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
