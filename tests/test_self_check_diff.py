# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1061: the self-check of a PR is compared with the self-check of its base commit.

Each case runs `tools/self_check_diff.py` as a process on two real results of the core. The files
in `tests/selfcheck_fixtures/` come from `archkeel validate --config archkeel.toml --json` on the
tiny Rust project `tiny/` (a git repository): `base.json` is that run, `plus-one-gap.json` is the
run after `plus-contract.json` replaces its contract. The second contract lists one more public
name that no import reaches, which gives one more gap. `scan-shrank.json` is the run after
`exclude_test_sources = true` is added to `tiny/archkeel.toml` and `#[cfg(test)]` is put before
`mod stock;` in `tiny/src/lib.rs`: the scan reads 3 files, not 4, and the gaps stay equal. Other
cases edit these real files.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from self_check_support import (
    FIXTURES,
    RULE,
    TOOL,
    real,
    red,
    run,
    save,
    unknown_reason,
    violation,
    worse,
)


def green(done: subprocess.CompletedProcess[str], *named: str) -> None:
    assert done.returncode == 0, done.stdout + done.stderr
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


def test_one_new_gap_is_green_and_named(tmp_path: Path) -> None:
    done = run(tmp_path, str(FIXTURES / "base.json"), str(FIXTURES / "plus-one-gap.json"))
    green(done, "GROWN 1 new gaps [interface.usage_unknown]", "inventory.stock", "grown 1")


def test_removal_only_is_green(tmp_path: Path) -> None:
    base = real("plus-one-gap.json")
    pr = real("base.json")
    pr["frame"]["self_test"]["collect"]["contract_files"] = base["frame"]["self_test"]["collect"][
        "contract_files"
    ]
    done = run(tmp_path, save(tmp_path, "base.json", base), save(tmp_path, "pr.json", pr))
    assert done.returncode == 0, done.stdout
    assert "grown 0, removed 1" in done.stdout


def test_a_removed_gap_does_not_offset_an_added_gap(tmp_path: Path) -> None:
    other = real("base.json")
    other["gaps"][0]["subject"] = other["gaps"][0]["subject"].replace("public/0", "public/7")
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", other))
    assert done.returncode == 0, done.stdout
    assert "grown 1, removed 1" in done.stdout


def test_a_reworded_reason_is_one_new_and_one_removed_gap(tmp_path: Path) -> None:
    other = real("base.json")
    other["gaps"][0]["reason"] = other["gaps"][0]["reason"].replace(
        "Remove the entry", "Delete the entry"
    )
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", other))
    green(done, "Delete the entry", "grown 1, removed 1", "reworded reason")


def test_a_gap_counts_for_each_occurrence(tmp_path: Path) -> None:
    twice = real("base.json")
    twice["gaps"] = twice["gaps"] * 2
    green(run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", twice)), "grown 1")


@pytest.mark.parametrize(
    ("base_edit", "pr_edit", "named"),
    [
        (None, worse("UNKNOWN"), f"rule status: {RULE} PASS -> UNKNOWN"),
        (worse("UNKNOWN"), unknown_reason, f"UNKNOWN reason: {RULE}: scope_incomplete"),
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


def test_a_refused_base_is_red_until_the_label_is_set(tmp_path: Path) -> None:
    refused = real("base.json")
    refused["refusal"] = {"kind": "core_error", "message": "x"}
    base, pr = save(tmp_path, "b.json", refused), str(FIXTURES / "base.json")
    red(run(tmp_path, base, pr), "is a refusal", "nothing is compared")
    done = run(tmp_path, base, pr, labels="ratchet-lead")
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


def test_a_new_gap_needs_no_label_and_is_printed_in_the_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        str(FIXTURES / "plus-one-gap.json"),
        extra=("--summary-file", str(summary)),
    )
    assert done.returncode == 0, done.stdout
    assert "gap growth: 1 items (top kinds interface.usage_unknown x1)" in done.stdout
    assert "gap growth: 1 items" in summary.read_text()


def test_a_worse_rule_status_fails_without_the_label_and_passes_with_it(tmp_path: Path) -> None:
    pr = real("base.json")
    unknown_reason(pr)
    pr["exit_code"] = 2
    base, path = str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr)
    red(run(tmp_path, base, path), "rule status", "blocking items need the label ratchet-lead")
    assert run(tmp_path, base, path, labels="ratchet-lead").returncode == 0
    assert run(tmp_path, base, path, labels="deletion-approved").returncode == 1


def test_a_gap_cannot_give_a_pass() -> None:
    """The counter-example of AD-1221: a result with a gap and a PASS rule has a false exit code."""
    sys.path.insert(0, str(TOOL.parent))
    from self_check_diff import absolute, condense

    result = condense(real("base.json"))
    assert result["gaps"] and result["exit_code"] == 2
    assert absolute(result) == []
    assert any(
        "exit code 0 differs from 2" in line for line in absolute({**result, "exit_code": 0})
    )


def test_the_label_does_not_matter_without_blocking_items(tmp_path: Path) -> None:
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
    red(run(tmp_path, base, pr), "unusable base: set the label ratchet-lead to pass")
    done = run(tmp_path, base, pr, labels="ratchet-lead")
    assert done.returncode == 0, done.stdout
    assert "nothing is compared" in done.stdout


def test_a_scan_that_reads_fewer_files_is_growth_even_when_the_gaps_are_equal(
    tmp_path: Path,
) -> None:
    """A `[scan]` exclusion hides gaps by scanning less: the real result shows files 4 -> 3."""
    assert real("base.json")["frame"]["self_test"]["reply"]["files"] == 4
    base, shrunk = str(FIXTURES / "base.json"), str(FIXTURES / "scan-shrank.json")
    red(run(tmp_path, base, shrunk), "scope shrank: files 4 -> 3", "grown 1")
    done = run(tmp_path, base, shrunk, labels="ratchet-lead")
    assert done.returncode == 0, done.stdout
    assert run(tmp_path, shrunk, base).returncode == 0


def test_a_scan_with_no_file_count_is_a_shrunk_scope(tmp_path: Path) -> None:
    pr = real("base.json")
    del pr["frame"]["self_test"]
    red(run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr)), "files 4 -> ?")


def test_a_rule_that_disappears_is_growth(tmp_path: Path) -> None:
    """A removed PASS rule, for example one deleted from the contract, is not green and silent."""
    pr = real("base.json")
    del pr["frame"]["rules"][RULE]
    pr["frame"]["rules"]["OTHER-RULE"] = ["interface_boundary", "PASS"]
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr))
    red(done, f"rule removed: {RULE}", "grown 1")
    done = run(
        tmp_path,
        str(FIXTURES / "base.json"),
        save(tmp_path, "p.json", pr),
        labels="ratchet-lead",
    )
    assert done.returncode == 0, done.stdout


@pytest.mark.parametrize(
    "broken",
    [
        lambda r: r.update(frame=None),
        lambda r: r.update(frame=[]),
        lambda r: r.pop("frame"),
        lambda r: r["frame"].update(rules={}),
        lambda r: r["frame"].pop("rules"),
    ],
    ids=["frame-none", "frame-list", "frame-missing", "rules-empty", "rules-missing"],
)
def test_a_degenerate_core_output_is_never_green(
    tmp_path: Path, broken: Callable[[dict[str, Any]], None]
) -> None:
    pr = real("base.json")
    broken(pr)
    pr["exit_code"] = 2
    base = str(FIXTURES / "base.json")
    done = run(tmp_path, base, save(tmp_path, "p.json", pr), labels="ratchet-lead")
    assert done.returncode == 1, done.stdout
    assert "the PR result is unusable" in done.stdout or "has no rules" in done.stdout


def test_a_degenerate_base_is_unusable(tmp_path: Path) -> None:
    base = real("base.json")
    base["frame"] = None
    red(
        run(tmp_path, save(tmp_path, "b.json", base), str(FIXTURES / "base.json")),
        "base result is unusable",
    )


def test_results_of_two_commits_are_not_the_same_commit(tmp_path: Path) -> None:
    sys.path.insert(0, str(TOOL.parent))
    from self_check_diff import condense

    one = save(tmp_path, "1.json", condense(real("base.json"), sha="a" * 40))
    two = save(tmp_path, "2.json", condense(real("base.json"), sha="b" * 40))
    done = subprocess.run(
        [sys.executable, str(TOOL), "same", one, two], capture_output=True, text=True
    )
    assert done.returncode == 1 and "sha" in done.stdout


def test_a_net_zero_scope_swap_is_growth_when_the_scan_table_differs(tmp_path: Path) -> None:
    """#1980: the same file count and fewer gaps; a `[scan]` change is the only trace."""
    sys.path.insert(0, str(TOOL.parent))
    from self_check_diff import condense

    base = condense(real("base.json"), "a" * 40, "t", {"roots": ["src"]})
    swapped = real("base.json")
    swapped["gaps"] = []
    swapped["exit_code"] = 0
    pr = condense(swapped, "b" * 40, "t", {"roots": ["src"], "exclude": ["src/stock.rs"]})
    base_file, pr_file = save(tmp_path, "b.json", base), save(tmp_path, "p.json", pr)
    red(run(tmp_path, base_file, pr_file), "scope changed: the [scan] table differs", "grown 1")
    assert (
        run(tmp_path, base_file, save(tmp_path, "q.json", {**pr, "scan": base["scan"]})).returncode
        == 0
    )


def test_a_rule_row_of_the_wrong_shape_is_an_unusable_result(tmp_path: Path) -> None:
    pr = real("base.json")
    pr["frame"]["rules"] = {"r1": ["x"]}
    done = run(tmp_path, str(FIXTURES / "base.json"), save(tmp_path, "p.json", pr))
    red(done, "the PR result is unusable", "is corrupt")
    assert "Traceback" not in done.stderr
