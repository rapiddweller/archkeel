# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1061: the self-check of a PR is compared with the self-check of its base commit.

Each case runs `tools/self_check_diff.py` as a process on two real results of the core. The files
in `tests/selfcheck_fixtures/` come from `archkeel validate --config archkeel.toml --json` on the
tiny Rust project `tiny/` (a git repository): `base.json` is that run, `plus-one-gap.json` is the
run after `plus-contract.json` replaces its contract. The second contract lists one more public
name that no import reaches, which gives one more gap. Other cases edit these two real files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "selfcheck_fixtures"
TOOL = Path(os.environ.get("SELF_CHECK_DIFF_TOOL", ROOT / "tools/self_check_diff.py"))
RULE = "TINY-INTERFACE-BOUNDARY"
LINE = "Ratchet growth: {n} items: the scan reads a new public name"


def real(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def save(tmp_path: Path, name: str, result: dict[str, Any] | str) -> str:
    path = tmp_path / name
    path.write_text(result if isinstance(result, str) else json.dumps(result), encoding="utf-8")
    return str(path)


def run(
    tmp_path: Path,
    base: str,
    pr: str,
    *,
    labels: str = "",
    body: str = "",
    extra: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(TOOL), base, pr, "--labels", labels, *extra]
    if body:
        args += ["--body-file", save(tmp_path, "body.txt", body)]
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def worse(status: str) -> Callable[[dict[str, Any]], None]:
    def edit(result: dict[str, Any]) -> None:
        result["frame"]["rules"][RULE][1] = status

    return edit


def unknown_reason(result: dict[str, Any]) -> None:
    worse("UNKNOWN")(result)
    result["frame"]["unknown_kinds"] = {RULE: "scope_incomplete"}


def violation(result: dict[str, Any]) -> None:
    worse("FAIL")(result)
    row = {"source": "a", "target": "b", "cause": "forbidden", "evidence": []}
    result["frame"]["details"] = {RULE: [row]}
    result["frame"]["violations"] = {RULE: 1}
    result["exit_code"] = 1


def red(done: subprocess.CompletedProcess[str], *named: str) -> None:
    assert done.returncode == 1, done.stdout + done.stderr
    for text in named:
        assert text in done.stdout, done.stdout


def test_equal_results_are_green(tmp_path: Path) -> None:
    done = run(
        tmp_path,
        save(tmp_path, "b.json", real("base.json")),
        save(tmp_path, "p.json", real("base.json")),
    )
    assert done.returncode == 0, done.stdout
    assert "grown 0, removed 0" in done.stdout


def test_one_new_gap_is_red_and_named(tmp_path: Path) -> None:
    done = run(tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "plus-one-gap.json"))
    red(done, "GROWN 1 new gaps [interface.usage_unknown]", "inventory.stock", "grown 1")


def test_removal_only_is_green(tmp_path: Path) -> None:
    done = run(tmp_path, str(FIXTURES / "plus-one-gap.json"), str(FIXTURES / "base.json"))
    assert done.returncode == 0, done.stdout
    assert "grown 0, removed 1" in done.stdout


def test_a_removed_gap_does_not_offset_an_added_gap(tmp_path: Path) -> None:
    other = real("base.json")
    other["gaps"][0]["subject"] = other["gaps"][0]["subject"].replace("public/0", "public/7")
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", other))
    red(done, "grown 1, removed 1", "ratchet-lead")


def test_a_reworded_reason_is_one_new_and_one_removed_gap(tmp_path: Path) -> None:
    other = real("base.json")
    other["gaps"][0]["reason"] = other["gaps"][0]["reason"].replace(
        "Remove the entry", "Delete the entry"
    )
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", other))
    red(done, "Delete the entry", "grown 1, removed 1", "reworded reason")


def test_a_gap_counts_for_each_occurrence(tmp_path: Path) -> None:
    twice = real("base.json")
    twice["gaps"] = twice["gaps"] * 2
    red(run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", twice)), "grown 1")


@pytest.mark.parametrize(
    ("base_edit", "pr_edit", "named"),
    [
        (None, worse("UNKNOWN"), f"GROWN rule status: {RULE} PASS -> UNKNOWN"),
        (worse("UNKNOWN"), unknown_reason, f"GROWN UNKNOWN reason: {RULE}: scope_incomplete"),
    ],
)
def test_a_worse_status_or_a_new_unknown_reason_is_red(
    tmp_path: Path,
    base_edit: Callable[[dict[str, Any]], None] | None,
    pr_edit: Callable[[dict[str, Any]], None],
    named: str,
) -> None:
    base, pr = real("base.json"), real("base.json")
    if base_edit:
        base_edit(base)
    pr_edit(pr)
    red(run(tmp_path, save(tmp_path, "b.json", base), save(tmp_path, "p.json", pr)), named)


@pytest.mark.parametrize(
    ("edit", "named"),
    [
        (violation, "'a', 'b', 'forbidden']"),
        (worse("FAIL"), f"rule {RULE} is FAIL"),
        (lambda r: r.update(exit_code=0), "exit code 0 differs from 2"),
        (lambda r: r.update(refusal={"kind": "core_error", "message": "x"}), "refusal: core_error"),
    ],
)
def test_the_pr_result_alone_must_be_clean(
    tmp_path: Path, edit: Callable[[dict[str, Any]], None], named: str
) -> None:
    pr = real("base.json")
    edit(pr)
    red(run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr)), named)


def test_a_pr_result_with_a_violation_stays_red_with_approval(tmp_path: Path) -> None:
    pr = real("base.json")
    violation(pr)
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        save(tmp_path, "p.json", pr),
        labels="ratchet-lead",
        body=LINE.format(n=2),
    )
    red(done, "violation:")


@pytest.mark.parametrize(
    "bad",
    ["", "{", "[]", '{"frame": 1}', "not json"],
    ids=["empty", "cut", "list", "shape", "text"],
)
def test_an_empty_or_corrupt_base_is_red_and_names_the_file(tmp_path: Path, bad: str) -> None:
    base = save(tmp_path, "base-result.json", bad)
    done = run(tmp_path, base, str(FIXTURES / "base.json"))
    red(done, "base result is unusable", "base-result.json")


def test_a_missing_base_is_red_and_names_the_file(tmp_path: Path) -> None:
    done = run(tmp_path, str(tmp_path / "no-base.json"), str(FIXTURES / "base.json"))
    red(done, "no-base.json is missing")


def test_a_refused_base_is_red_until_the_growth_is_approved(tmp_path: Path) -> None:
    refused = real("base.json")
    refused["refusal"] = {"kind": "core_error", "message": "x"}
    base, pr = save(tmp_path, "b.json", refused), str(FIXTURES / "base.json")
    red(run(tmp_path, base, pr), "is a refusal", "nothing is compared")
    red(run(tmp_path, base, pr, labels="ratchet-lead"), "Ratchet growth")
    red(run(tmp_path, base, pr, labels="ratchet-lead", body=LINE.format(n=5)), "grown count is 1")
    done = run(tmp_path, base, pr, labels="ratchet-lead", body=LINE.format(n=1))
    assert done.returncode == 0, done.stdout


def test_a_base_for_another_commit_is_red(tmp_path: Path) -> None:
    sys.path.insert(0, str(TOOL.parent))
    from self_check_diff import condense

    base = save(tmp_path, "b.json", condense(real("base.json"), sha="a" * 40, tree="t1"))
    red(
        run(tmp_path, base, str(FIXTURES / "base.json"), extra=("--base-sha", "b" * 40)),
        "is for " + "a" * 40,
    )
    done = run(tmp_path, base, str(FIXTURES / "base.json"), extra=("--base-sha", "a" * 40))
    assert done.returncode == 0, done.stdout


def test_a_base_of_another_native_tree_is_compared_and_both_trees_print(tmp_path: Path) -> None:
    sys.path.insert(0, str(TOOL.parent))
    from self_check_diff import condense

    base = save(tmp_path, "b.json", condense(real("base.json"), sha="a" * 12, tree="treeone"))
    pr = save(tmp_path, "p.json", condense(real("base.json"), sha="b" * 12, tree="treetwo"))
    done = run(tmp_path, base, pr)
    assert done.returncode == 0, done.stdout
    assert "native tree treeone" in done.stdout and "native tree treetwo" in done.stdout


@pytest.mark.parametrize(
    ("labels", "body", "green", "named"),
    [
        ("ratchet-lead", LINE.format(n=1), True, ""),
        ("ratchet-lead", "text\n" + LINE.format(n=1) + "\nmore", True, ""),
        ("ratchet-lead", "", False, "no line"),
        ("ratchet-lead", LINE.format(n=2), False, "grown count is 1"),
        ("", LINE.format(n=1), False, "needs the label ratchet-lead"),
        ("deletion-approved", LINE.format(n=1), False, "needs the label ratchet-lead"),
        ("", "", False, "needs the label ratchet-lead"),
        ("ratchet-lead", "Ratchet growth: 1 items: short", False, "no line"),
    ],
)
def test_growth_passes_only_with_the_label_and_the_exact_count(
    tmp_path: Path, labels: str, body: str, green: bool, named: str
) -> None:
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        str(FIXTURES / "plus-one-gap.json"),
        labels=labels,
        body=body,
    )
    if green:
        assert done.returncode == 0, done.stdout
    else:
        red(done, named)


def test_the_label_and_the_line_do_not_matter_without_growth(tmp_path: Path) -> None:
    done = run(
        tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "base.json"), labels="ratchet-lead"
    )
    assert done.returncode == 0, done.stdout


def test_two_results_of_one_commit_must_be_equal(tmp_path: Path) -> None:
    for first, second, code in (
        ("base.json", "base.json", 0),
        ("base.json", "plus-one-gap.json", 1),
    ):
        done = subprocess.run(
            [sys.executable, str(TOOL), "same", str(FIXTURES / first), str(FIXTURES / second)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert done.returncode == code, done.stdout


def test_an_unusable_base_needs_the_label_even_when_the_pr_has_nothing_to_approve(
    tmp_path: Path,
) -> None:
    clean = real("base.json")
    clean["gaps"] = []
    clean["exit_code"] = 0
    pr, base = save(tmp_path, "p.json", clean), save(tmp_path, "b.json", "")
    red(run(tmp_path, base, pr), "unusable base: set the label ratchet-lead")
    done = run(tmp_path, base, pr, labels="ratchet-lead")
    assert done.returncode == 0, done.stdout
    assert "nothing is compared" in done.stdout
