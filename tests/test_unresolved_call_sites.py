# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-100: a change in unresolved calls names the call sites behind the count (#131)."""

import errno
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from test_architecture_demo import CONFIG, _prepare_repo
from test_measurement_budgets import _baseline, _contract_with_budgets

from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.measurements import MeasurementBudget
from archkeel.ir.model import Observation, ObservationResult, RunResult, UnresolvedCallChange
from archkeel.render.summary import report_summary
from archkeel.render.terminal import print_result

_PROBE_PATH = "shop/app/probe_unresolved.py"
_ONE_SIDED_NOTE = (
    "added calls in files only the working tree holds (git-ignored, inside a submodule, or "
    "export-ignore at the --against revision) are not named"
)
_STALE_NOTE = (
    "no unresolved call differs from the --against revision; the accepted value does not match "
    "that revision's code"
)
_UNCOMPARED_NOTE = "the --against revision's calls could not be compared, so no call site is named"
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


def _exceeded(values: str, *, hint: bool = False) -> str:
    # The baseline stores the value alone; without --against the finding says which flag names
    # the sites, with it the sites themselves follow.
    finding = f"measurement budget exceeded in calls_unresolved: {values}"
    return f"{finding}; validate --against <ref> names the call sites" if hint else finding


def _added(lines: tuple[int, ...], before: int = 0, after: int = 1) -> UnresolvedCallChange:
    return UnresolvedCallChange(
        "added", _CALLER, "_unbound_probe", _UNBOUND, "app", _PROBE_PATH, lines, before, after
    )


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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _budget_repo(tmp_path: Path, files: dict[str, str], unresolved: int) -> tuple[Path, str, Path]:
    """The shop sample plus `files`, with a committed baseline pinning `unresolved`."""
    root = _prepare_repo(
        tmp_path / "repo",
        {"architecture-contract.json": _contract_with_budgets("calls_unresolved"), **files},
    )
    baseline = _baseline(root, MeasurementBudget("calls_unresolved", unresolved))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")
    return root, _git(root, "rev-parse", "HEAD"), baseline


def _against(root: Path, base: str, baseline: Path) -> RunResult:
    return run_validate(root, CONFIG, observe, baseline=baseline, against=base)[0]


_GENERATED = "shop/app/generated_pb.py"
_VENDORED = "shop/app/vendor/lib.py"


def test_a_file_name_git_cannot_decode_never_decides_the_run(tmp_path: Path) -> None:
    """A name that is not UTF-8 is a Git listing the comparison cannot read, not a crash; the
    listing covers the scan roots only, so one outside them costs nothing."""
    root, base, baseline = _budget_repo(tmp_path, {}, 7)
    try:
        (root / os.fsdecode(b"docs-caf\xe9.txt")).write_text("notes\n")
    except OSError as error:
        if error.errno == errno.EILSEQ:
            pytest.skip("Filesystem rejects non-UTF-8 filenames; this requires Linux.")
        raise
    (root / _PROBE_PATH).write_text(_probe("_unbound_probe()"))

    outside = _against(root, base, baseline)
    (root / os.fsdecode(b"shop/app/notes-caf\xe9.txt")).write_text("notes\n")
    inside = _against(root, base, baseline)

    assert outside.failures == inside.failures == (_exceeded("7->8"),)
    assert outside.unresolved_call_changes == (_added((2,)),)
    assert (inside.exit_code, inside.unresolved_call_changes) == (1, None)
    assert inside.unresolved_call_note == _UNCOMPARED_NOTE


def _miscounted(source_root: Path, **options: Any) -> ObservationResult:
    """The analyzer with one resolved call recounted as unresolved: the call records no longer
    add up to the coverage counts, while the counts themselves stay consistent."""
    observed = observe(source_root, **options)
    assert observed.observation is not None and observed.coverage is not None
    coverage = replace(
        observed.coverage,
        calls_resolved=observed.coverage.calls_resolved - 1,
        calls_unresolved=observed.coverage.calls_unresolved + 1,
    )
    return ObservationResult(
        replace(observed.observation, coverage=coverage), coverage, observed.diagnostics
    )


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


def test_report_help_says_component_narrows_violations_or_calls() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "COLUMNS": "200"},
    )

    words = " ".join(result.stdout.split())
    assert "Narrow the violations, or with --only calls the calls," in words
