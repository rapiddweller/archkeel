# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-100: a change in unresolved calls names the call sites behind the count (#131)."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from rich.console import Console
from test_architecture_demo import CONFIG, _prepare_repo
from test_measurement_budgets import _baseline, _contract_with_budgets

from archkeel.analyzer import observe
from archkeel.check.ratchets import unresolved_call_changes
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.ir.measurements import MeasurementBudget
from archkeel.ir.model import Observation, RunResult, UnresolvedCallChange
from archkeel.render.html import render_architecture_html
from archkeel.render.summary import report_summary
from archkeel.render.terminal import print_result

_PROBE_PATH = "shop/app/probe_unresolved.py"
_CALLER = "shop.app.probe_unresolved.probe"
_UNBOUND = "name has no statically indexed binding"


def _probe(*body: str) -> str:
    return "def probe() -> None:\n" + "".join(f"    {line}\n" for line in body)


def _observe(root: Path, files: dict[str, str]) -> Observation:
    for relative, content in files.items():
        (root / relative).write_text(content)
    observed = observe(
        root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="0" * 40,
        dirty=False,
        contract_root=root,
    )
    assert observed.observation is not None, observed.diagnostics
    return observed.observation


def _added(lines: tuple[int, ...], before: int = 0, after: int = 1) -> UnresolvedCallChange:
    return UnresolvedCallChange(
        "added", _CALLER, "_unbound_probe", _UNBOUND, "app", _PROBE_PATH, lines, before, after
    )


def test_an_added_unresolved_call_names_its_caller_line_reason_and_component(
    tmp_path: Path,
) -> None:
    root = _prepare_repo(tmp_path, {})
    before = _observe(root, {})
    after = _observe(root, {_PROBE_PATH: _probe("_unbound_probe()")})

    assert unresolved_call_changes(before, after) == (_added((2,)),)
    assert unresolved_call_changes(after, before) == (
        replace(_added((2,)), change="removed", before=1, after=0),
    )


def test_moving_an_unresolved_call_adds_and_removes_nothing(tmp_path: Path) -> None:
    root = _prepare_repo(tmp_path, {})
    before = _observe(root, {_PROBE_PATH: _probe("_unbound_probe()")})
    moved = _observe(root, {_PROBE_PATH: "\n\n\n" + _probe("VALUE = 1", "_unbound_probe()")})

    assert unresolved_call_changes(before, moved) == ()


def test_identical_calls_in_one_caller_are_counted_not_told_apart(tmp_path: Path) -> None:
    """Which of two identical calls is new is undecidable, so both lines are named."""
    root = _prepare_repo(tmp_path, {})
    before = _observe(root, {_PROBE_PATH: _probe("_unbound_probe()")})
    after = _observe(root, {_PROBE_PATH: _probe("_unbound_probe()", "_unbound_probe()")})

    assert unresolved_call_changes(before, after) == (_added((2, 3), 1, 2),)


def _against_repo(
    tmp_path: Path, *budgets: str, base_files: dict[str, str] | None = None
) -> tuple[Path, str, Path]:
    root = _prepare_repo(
        tmp_path / "repo",
        {"architecture-contract.json": _contract_with_budgets(*budgets), **(base_files or {})},
    )
    baseline = _baseline(root, MeasurementBudget("calls_unresolved", 7))
    for args in (["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "baseline"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    (root / _PROBE_PATH).write_text(_probe("_unbound_probe()"))
    return root, base, baseline


def test_validate_against_names_the_call_behind_a_calls_unresolved_rise(tmp_path: Path) -> None:
    root, base, baseline = _against_repo(tmp_path, "calls_unresolved")

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline, against=base)

    assert result.failures == ("measurement budget exceeded in calls_unresolved: 7->8",)
    assert result.unresolved_call_changes == (_added((2,)),)
    # Without --against there is no second revision to name the site from.
    alone, _ = run_validate(root, CONFIG, observe, baseline=baseline)
    assert alone.failures == result.failures
    assert alone.unresolved_call_changes is None


def test_validate_against_compares_calls_only_under_a_calls_unresolved_budget(
    tmp_path: Path,
) -> None:
    root, base, _ = _against_repo(tmp_path)

    result, _ = run_validate(root, CONFIG, observe, against=base)

    assert result.unresolved_call_changes is None


def test_an_unobservable_against_revision_leaves_the_sites_unnamed_not_the_finding(
    tmp_path: Path,
) -> None:
    """The sites explain a finding; a revision that cannot be scanned never decides one."""
    broken = "shop/app/broken.py"
    root, base, baseline = _against_repo(
        tmp_path, "calls_unresolved", base_files={broken: "def broken(:\n"}
    )
    (root / broken).unlink()

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline, against=base)

    assert result.failures == ("measurement budget exceeded in calls_unresolved: 7->8",)
    assert result.unresolved_call_changes is None


def _terminal(result: RunResult) -> str:
    console = Console(record=True, width=200, color_system=None)
    print_result(result, report_summary(result), artifacts=(), console=console)
    return console.export_text()


def test_terminal_names_call_sites_only_on_failure_and_caps_the_list() -> None:
    changes = tuple(replace(_added((line,)), caller=f"{_CALLER}{line}") for line in range(1, 8))
    failed = RunResult("validate", 1, failures=("regressed",), unresolved_call_changes=changes)

    shown = _terminal(failed)

    assert "Unresolved call sites: 7 added, 0 removed" in shown
    assert f"+ {_PROBE_PATH}:1 {_CALLER}1: _unbound_probe() [app] {_UNBOUND}" in shown
    assert f"{_CALLER}5:" in shown and f"{_CALLER}6:" not in shown
    assert "+2 more in the JSON result's unresolved_call_changes" in shown
    assert "Unresolved call sites" not in _terminal(replace(failed, exit_code=0, failures=()))


def _cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, object]]:
    code = main(list(args))
    return code, json.loads(capsys.readouterr().out)


_PROBE_ROW = {
    "caller": _CALLER,
    "component": "app",
    "expression": "_unbound_probe",
    "line": 2,
    "path": _PROBE_PATH,
    "reason": _UNBOUND,
    "status": "unresolved",
}


def test_report_only_calls_lists_every_unresolved_and_partially_resolved_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #131, first bullet: opt-in, so the default result keeps its size (AD-100)."""
    root = _prepare_repo(tmp_path, {_PROBE_PATH: _probe("_unbound_probe()")})

    code, result = _cli(capsys, "report", "--root", str(root), "--only", "calls", "--json")

    assert code == 0
    rows = result["filtered_calls"]
    coverage = result["coverage"]
    assert isinstance(rows, list) and isinstance(coverage, dict)
    assert len(rows) == coverage["calls_unresolved"] + coverage["calls_partially_resolved"]
    assert {row["status"] for row in rows} == {"unresolved", "partially_resolved"}
    assert _PROBE_ROW in rows
    assert rows == sorted(
        rows, key=lambda row: (row["path"], row["line"], row["caller"], row["expression"])
    )
    assert result["report_filter"] == {
        "only_violations": False,
        "rule": None,
        "component": None,
        "only_calls": True,
    }
    assert result["filtered_violations"] is None


def test_report_only_calls_honours_component_and_rejects_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepare_repo(tmp_path, {_PROBE_PATH: _probe("_unbound_probe()")})
    only_calls = ("report", "--root", str(root), "--only", "calls")

    code, result = _cli(capsys, *only_calls, "--component", "app", "--json")
    assert code == 0
    rows = result["filtered_calls"]
    assert isinstance(rows, list) and _PROBE_ROW in rows
    assert {row["component"] for row in rows} == {"app"}

    code, result = _cli(capsys, *only_calls, "--component", "nowhere", "--json")
    assert code == 2
    assert result["diagnostics"][0]["kind"] == "filter_unknown"  # type: ignore[index]

    # A call cites no rule, so --rule has nothing to narrow.
    code, _ = _cli(capsys, *only_calls, "--rule", "DEP-STORE-NO-MONEY", "--json")
    assert code == 2


def test_default_report_json_carries_no_call_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _prepare_repo(tmp_path, {_PROBE_PATH: _probe("_unbound_probe()")})

    code, result = _cli(capsys, "report", "--root", str(root), "--json")

    assert code == 0
    assert "filtered_calls" not in result
    assert "unresolved_call_changes" not in result


def test_only_calls_page_shows_the_call_table_instead_of_the_other_sections(
    tmp_path: Path,
) -> None:
    root = _prepare_repo(tmp_path, {_PROBE_PATH: _probe("_unbound_probe()")})
    result, architecture = run_report(root, config=CONFIG, analyzer=observe, only_calls=True)
    assert architecture is not None and result.filtered_calls is not None

    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    assert "Unresolved and partially resolved calls" in page
    assert f"<code>{_PROBE_PATH}:2</code>" in page
    assert "Declared-rule violations" not in page
    assert "Component flow" not in page
    listed = len(result.filtered_calls)
    assert (
        f"Filtered (only calls): {listed} unresolved or partially resolved call(s) listed."
        in report_summary(result).sentence
    )
