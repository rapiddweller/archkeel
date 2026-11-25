# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1064: the shell gate compares the rule ids with the contract and with the base contract.

Each case runs `tools/self_check_shell.py` as a process. The result is a real core result
(`selfcheck_fixtures/base.json`) with no gap; the contract files are small documents of rule ids.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from self_check_support import FIXTURES, RULE, TOOL, many_gaps, real, red, run, save

TOOL = Path(os.environ.get("SELF_CHECK_SHELL_TOOL", TOOL.with_name("self_check_shell.py")))
LINE = "Ratchet growth (shell): {n} items: the contract drops a rule on purpose"
NATIVE = "Ratchet growth: {n} items: the scan reads new public names"


def result() -> dict[str, Any]:
    found = real("base.json")
    found["gaps"] = []
    found["frame"]["collection_gaps"] = []
    found["exit_code"] = 0
    return found


def contract(tmp_path: Path, name: str, ids: list[Any]) -> str:
    return save(tmp_path, name, {"rules": [{"id": one} for one in ids]})


def gate(
    tmp_path: Path,
    ids: list[Any],
    base: list[Any] | None,
    *,
    document: dict[str, Any] | None = None,
    labeled: bool = False,
    body: str = "",
    extra: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RATCHET_LABELED": "true" if labeled else "false"}
    env.pop("RATCHET_BODY_FILE", None)
    env.pop("SHELL_BASE_CONTRACT", None)
    if base is not None:
        env["SHELL_BASE_CONTRACT"] = contract(tmp_path, "base-contract.json", base)
    if body:
        env["RATCHET_BODY_FILE"] = save(tmp_path, "body.txt", body)
    args = [sys.executable, str(TOOL), save(tmp_path, "r.json", document or result())]
    args += [contract(tmp_path, "contract.json", ids), *extra]
    return subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)


def test_equal_rules_and_an_equal_base_are_green(tmp_path: Path) -> None:
    done = gate(tmp_path, [RULE], [RULE])
    assert done.returncode == 0, done.stdout
    assert done.stdout.splitlines()[-1] == "shell self-check gate: GREEN"


def test_a_new_rule_is_no_growth(tmp_path: Path) -> None:
    document = result()
    document["frame"]["rules"]["TINY-NEW"] = ["x", "PASS"]
    done = gate(tmp_path, [RULE, "TINY-NEW"], [RULE], document=document)
    assert done.returncode == 0, done.stdout


def test_a_rule_removed_since_the_base_is_red_and_named(tmp_path: Path) -> None:
    done = gate(tmp_path, [RULE], [RULE, "SHELL-GONE"])
    red(done, "GROWN rule removed: SHELL-GONE", "needs the label ratchet-lead", "RED (exit 1)")
    assert "make self-validate-shell" in done.stdout


@pytest.mark.parametrize(
    ("labeled", "body", "named"),
    [
        (True, LINE.format(n=1), ""),
        (True, LINE.format(n=2), "the grown count is 1"),
        (True, "", "has no plain line"),
        (False, LINE.format(n=1), "needs the label"),
    ],
)
def test_the_removal_passes_only_with_the_label_and_the_right_count(
    tmp_path: Path, labeled: bool, body: str, named: str
) -> None:
    done = gate(tmp_path, [RULE], [RULE, "SHELL-GONE"], labeled=labeled, body=body)
    if named:
        red(done, named)
    else:
        assert done.returncode == 0, done.stdout


def test_report_only_prints_the_removal_and_exits_0(tmp_path: Path) -> None:
    done = gate(tmp_path, [RULE], [RULE, "SHELL-GONE"], extra=("--report-only",))
    assert done.returncode == 0 and "GROWN rule removed: SHELL-GONE" in done.stdout


def test_a_base_contract_that_cannot_be_read_is_red_with_the_reason(tmp_path: Path) -> None:
    done = gate(tmp_path, [RULE], None, extra=("--base", "origin/nothing"))
    red(done, "the base contract is unavailable", "origin/nothing")
    done = gate(tmp_path, [RULE], None)
    red(done, "no base ref; set PR_BASE or SHELL_BASE_CONTRACT=<file>")
    bad = save(tmp_path, "bad.json", "not json")
    env = {**os.environ, "SHELL_BASE_CONTRACT": bad}
    args = [sys.executable, str(TOOL), save(tmp_path, "r.json", result())]
    args += [contract(tmp_path, "c.json", [RULE])]
    done = subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)
    red(done, "is not a contract with rules")


def test_no_compare_skips_the_base_only(tmp_path: Path) -> None:
    done = gate(tmp_path, [RULE], None, extra=("--no-compare",))
    assert done.returncode == 0, done.stdout
    assert gate(tmp_path, [], None, extra=("--no-compare",)).returncode == 1


def test_a_rule_without_a_row_or_a_row_without_a_rule_is_red(tmp_path: Path) -> None:
    red(
        gate(tmp_path, [RULE, "SHELL-DROPPED"], [RULE]),
        "rule SHELL-DROPPED of the contract has no row",
    )
    red(gate(tmp_path, [], [RULE]), f"rule {RULE} is in the result and not in the contract")


def test_a_duplicate_id_in_the_contract_is_red(tmp_path: Path) -> None:
    red(gate(tmp_path, [RULE, RULE], [RULE]), f"rule id {RULE} is listed twice in the contract")


def test_a_duplicate_id_in_the_result_is_red(tmp_path: Path) -> None:
    text = json.dumps(result())
    row = json.dumps(result()["frame"]["rules"][RULE])
    doubled = text.replace(f'"{RULE}": {row}', f'"{RULE}": {row}, "{RULE}": {row}', 1)
    assert doubled != text
    env = {**os.environ, "SHELL_BASE_CONTRACT": contract(tmp_path, "b.json", [RULE])}
    args = [sys.executable, str(TOOL), save(tmp_path, "r.json", doubled)]
    args += [contract(tmp_path, "c.json", [RULE])]
    done = subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)
    red(done, f"rule id {RULE} is listed twice in the result")


@pytest.mark.parametrize("bad", [None, 7, "", ["x"]])
def test_a_null_or_non_string_id_is_red(tmp_path: Path, bad: Any) -> None:
    red(gate(tmp_path, [RULE, bad], [RULE]), "not a non-empty string")
    red(gate(tmp_path, [RULE], [RULE, bad]), "not a non-empty string")


def test_a_result_that_is_not_clean_is_red(tmp_path: Path) -> None:
    refused = {"refusal": {"kind": "core_error", "message": "x"}, "exit_code": 2}
    red(gate(tmp_path, [RULE], [RULE], document=refused), "the PR result is a refusal")
    gap = real("base.json")
    red(gate(tmp_path, [RULE], [RULE], document=gap), "no gap")
    assert FIXTURES.is_dir()


def test_the_base_contract_comes_from_the_merge_base_in_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    env.pop("SHELL_BASE_CONTRACT", None)
    env["RATCHET_LABELED"] = "false"

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    def tool(*args: str, name: str = "c.json") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), str(tmp_path / "r.json"), name, *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    git("init", "-q")
    (tmp_path / "r.json").write_text(json.dumps(result()), encoding="utf-8")
    (repo / "c.json").write_text(json.dumps({"rules": [{"id": RULE}, {"id": "GONE"}]}))
    git("add", "-A")
    git("commit", "-qm", "base")
    (repo / "c.json").write_text(json.dumps({"rules": [{"id": RULE}]}))
    git("commit", "-qam", "head")
    red(tool("--base", "HEAD~1"), "GROWN rule removed: GONE")
    assert tool("--base", "HEAD").returncode == 0
    git("mv", "c.json", "d.json")
    git("commit", "-qm", "move")
    red(tool("--base", "HEAD~1", name="d.json"), "the base contract is unavailable", "d.json")


def native_run(tmp_path: Path, body: str, labeled: bool = True) -> subprocess.CompletedProcess[str]:
    """The real native tool: three new gaps against the base."""
    pr = save(tmp_path, "n.json", many_gaps(3))
    return run(
        tmp_path,
        str(FIXTURES / "base.json"),
        pr,
        labels="ratchet-lead" if labeled else "",
        body=body,
    )


def shell_run(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    return gate(tmp_path, [RULE], [RULE, "SHELL-GONE"], labeled=True, body=body)


BOTH = NATIVE.format(n=3) + "\n" + LINE.format(n=1)


def test_one_body_with_both_lines_approves_both_gates(tmp_path: Path) -> None:
    assert native_run(tmp_path, BOTH).returncode == 0
    assert shell_run(tmp_path, BOTH).returncode == 0
    assert native_run(tmp_path, LINE.format(n=1) + "\n" + NATIVE.format(n=3)).returncode == 0


def test_only_the_native_line_leaves_the_shell_gate_red_and_names_its_line(tmp_path: Path) -> None:
    body = NATIVE.format(n=3)
    assert native_run(tmp_path, body).returncode == 0
    red(shell_run(tmp_path, body), "no plain line `Ratchet growth (shell): 1 items: <reason>`")


def test_only_the_shell_line_leaves_the_native_gate_red(tmp_path: Path) -> None:
    body = LINE.format(n=1)
    assert shell_run(tmp_path, body).returncode == 0
    red(native_run(tmp_path, body), "no plain line `Ratchet growth: 3 items: <reason>`")


def test_each_gate_counts_its_own_line(tmp_path: Path) -> None:
    red(native_run(tmp_path, NATIVE.format(n=1) + "\n" + LINE.format(n=1)), "the grown count is 3")
    red(shell_run(tmp_path, NATIVE.format(n=3) + "\n" + LINE.format(n=3)), "the grown count is 1")


def test_two_lines_of_one_kind_are_red_and_the_other_kind_does_not_count(tmp_path: Path) -> None:
    twice = BOTH + "\n" + LINE.format(n=1)
    red(shell_run(tmp_path, twice), "2 `Ratchet growth (shell)` lines; keep exactly one")
    assert native_run(tmp_path, twice).returncode == 0
    twice = BOTH + "\n" + NATIVE.format(n=3)
    red(native_run(tmp_path, twice), "2 `Ratchet growth` lines; keep exactly one")
    assert shell_run(tmp_path, twice).returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        LINE.format(n=1).replace("Ratchet growth (shell)", "Ratchet growth  (shell)"),
        LINE.format(n=1).replace("(shell)", "(Shell)"),
        "x " + LINE.format(n=1),
        f"> {LINE.format(n=1)}",
        "Ratchet growth (shell): 01 items: the contract drops a rule on purpose",
        "Ratchet growth (shell): 1 items: short",
    ],
)
def test_the_shell_line_stays_strict(tmp_path: Path, body: str) -> None:
    assert shell_run(tmp_path, body).returncode == 1


def test_a_shell_line_does_not_satisfy_the_native_gate_and_the_reverse(tmp_path: Path) -> None:
    red(native_run(tmp_path, LINE.format(n=3)), "no plain line")
    red(shell_run(tmp_path, NATIVE.format(n=1)), "no plain line")
