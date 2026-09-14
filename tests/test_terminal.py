# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import replace

import pytest
from rich.console import Console
from test_expectation import _delta_payload
from test_html_report import FAILED_CHECK

from archkeel.ir.codec import parse_delta
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import Diagnostic, RatchetObservations, RunResult
from archkeel.render.summary import Summary, check_summary, report_summary
from archkeel.render.terminal import print_result

_DIAGNOSTIC = Diagnostic(
    "missing_tool", "git", "The source revision cannot be established.", "Install Git and retry."
)
_DELTA = replace(
    parse_delta(_delta_payload()),
    ratchets=RatchetObservations(
        "SUPPORTED",
        Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 2, "measured"),
        Measurements(RatchetScalars(0, 0, 0, 0, 1, 0), 1, "measured"),
    ),
)
_RESULTS = {
    "report-pass": report_summary(RunResult("report", 0, "PASS", "PASS", "n/a")),
    "report-unverifiable": report_summary(RunResult("report", 2, diagnostics=(_DIAGNOSTIC,))),
    "check-reject": check_summary(replace(FAILED_CHECK, delta=_DELTA, failures=("regressed",))),
}


def _render(result: RunResult, summary: Summary, width: int) -> str:
    console = Console(record=True, width=width, color_system=None)
    print_result(result, summary, artifacts=("out/architecture.json",), console=console)
    return console.export_text()


@pytest.mark.parametrize("case", sorted(_RESULTS))
def test_terminal_view_fits_80_columns_and_uses_the_shared_wording(case: str) -> None:
    summary = _RESULTS[case]
    result = {
        "report-pass": RunResult("report", 0, "PASS", "PASS", "n/a"),
        "report-unverifiable": RunResult("report", 2, diagnostics=(_DIAGNOSTIC,)),
        "check-reject": replace(FAILED_CHECK, delta=_DELTA, failures=("regressed",)),
    }[case]
    narrow = _render(result, summary, 80)
    assert all(len(line) <= 80 for line in narrow.splitlines())
    wide = _render(result, summary, 200)
    assert summary.sentence in wide
    assert summary.decision.label in wide
    assert all(row.reason in wide and row.key in wide for row in summary.verdicts)
    assert "out/architecture.json" in wide


def test_terminal_view_shows_regressions_failures_and_diagnostics() -> None:
    reject = _render(
        replace(FAILED_CHECK, delta=_DELTA, failures=("regressed",)), _RESULTS["check-reject"], 200
    )
    assert "calls_unresolved" in reject and "0 → 1" in reject and "• regressed" in reject
    unverifiable = _render(
        RunResult("report", 2, diagnostics=(_DIAGNOSTIC,)), _RESULTS["report-unverifiable"], 200
    )
    assert "Diagnostic · missing_tool" in unverifiable and "Install Git and retry." in unverifiable


def test_terminal_view_does_not_interpret_markup_in_evidence() -> None:
    diagnostic = replace(_DIAGNOSTIC, subject="[bold]src[/bold]")
    result = RunResult("report", 2, diagnostics=(diagnostic,))
    assert "[bold]src[/bold]" in _render(result, report_summary(result), 200)
