# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from collections.abc import Callable
from dataclasses import replace

import pytest
from rich.console import Console
from test_expectation import _delta_payload
from test_html_report import FAILED_CHECK

from archkeel.ir.codec import parse_delta
from archkeel.ir.measurements import Measurements, RatchetScalars
from archkeel.ir.model import (
    AllowedDependencyRule,
    Diagnostic,
    DraftedComponentSize,
    ForbiddenDependencyRule,
    OpenDecision,
    RatchetObservations,
    ReviewClaims,
    RuleAssessment,
    RunResult,
)
from archkeel.render.summary import Summary, check_summary, init_summary, report_summary
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
_REPORT_FAIL = RunResult(
    "report",
    0,
    "PASS",
    "FAIL",
    "n/a",
    measurements=Measurements(RatchetScalars(2, 0, 0, 0, 0, 0), 0, "n/a"),
)
_RESULTS = {
    "report-pass": report_summary(RunResult("report", 0, "PASS", "PASS", "n/a")),
    "report-fail": report_summary(_REPORT_FAIL),
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
        "report-fail": _REPORT_FAIL,
        "report-unverifiable": RunResult("report", 2, diagnostics=(_DIAGNOSTIC,)),
        "check-reject": replace(FAILED_CHECK, delta=_DELTA, failures=("regressed",)),
    }[case]
    narrow = _render(result, summary, 80)
    assert all(len(line) <= 80 for line in narrow.splitlines())
    wide = _render(result, summary, 400)
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


@pytest.mark.parametrize("code", ["graph.drift", "rule.violated", "decision.open"])
def test_terminal_panel_names_its_validation_code(code: str) -> None:
    diagnostic = Diagnostic(
        "contract_invalid",
        "contract",
        "The contract needs a decision.",
        "Review the target.",
        "/components",
        code,
    )
    result = RunResult("report", 2, diagnostics=(diagnostic,))
    rendered = _render(result, report_summary(result), 80)
    assert f"Diagnostic · {code}" in rendered
    assert "Diagnostic · contract_invalid" not in rendered


def test_terminal_view_does_not_interpret_markup_in_evidence() -> None:
    diagnostic = replace(_DIAGNOSTIC, subject="[bold]src[/bold]")
    result = RunResult("report", 2, diagnostics=(diagnostic,))
    assert "[bold]src[/bold]" in _render(result, report_summary(result), 200)


def test_report_headline_fails_on_declared_rule_violations_even_though_exit_code_is_zero() -> None:
    """AD-14: the exit code alone must never drive the report headline."""
    summary = _RESULTS["report-fail"]
    assert _REPORT_FAIL.exit_code == 0
    assert summary.decision.label == "FAIL"
    assert summary.decision.state == "fail"
    assert "2 declared-rule violation(s) found" in summary.sentence
    assert "report records violations without gating" in summary.sentence


def test_init_headline_is_unchanged_by_the_report_decision_fix() -> None:
    """AD-14 only changes report; init keeps its onboarding sentence and pass badge."""
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        artifact="architecture-contract.json",
    )
    summary = init_summary(result)
    assert summary.decision.label == "PASS"
    assert summary.sentence == "Draft written. Run archkeel validate to list every decision left."
    assert len(summary.verdicts) == 1


def test_terminal_view_names_the_largest_drafted_component() -> None:
    """AD-38: the architect gets a size to consolidate with, not just a list of names."""
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        artifact="architecture-contract.json",
        draft_sizes=(
            DraftedComponentSize("embedded", 18, 40),
            DraftedComponentSize("bridge", 2, 1),
            DraftedComponentSize("runtime", 1, 0),
        ),
    )
    summary = init_summary(result)
    assert (
        "`embedded` is the largest drafted component: 18 module(s), 40 inner edge(s)."
        in summary.sentence
    )
    assert all(len(line) <= 80 for line in _render(result, summary, 80).splitlines())


def test_terminal_view_says_no_drafted_component_stands_out_on_a_tie() -> None:
    """A tie for the most modules names no single component as the one to consolidate."""
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        artifact="architecture-contract.json",
        draft_sizes=(DraftedComponentSize("a", 5, 2), DraftedComponentSize("b", 5, 3)),
    )
    summary = init_summary(result)
    assert "No drafted component stands out in size." in summary.sentence


def test_terminal_view_names_agent_decisions_awaiting_the_architect() -> None:
    """AD-50: validate and report say how many decisions the agent made, not just PASS."""
    result = RunResult("report", 0, "PASS", "PASS", "n/a", agent_decisions=(3, 10))
    summary = report_summary(result)
    assert "3 of 10 decisions made by the agent, awaiting the architect." in summary.sentence
    wide = _render(result, summary, 400)
    assert "3 of 10 decisions made by the agent, awaiting the architect." in wide


def test_terminal_view_omits_the_agent_decisions_line_when_none_remain() -> None:
    result = RunResult("report", 0, "PASS", "PASS", "n/a", agent_decisions=(0, 10))
    assert "made by the agent" not in report_summary(result).sentence


def test_terminal_view_counts_every_review_claim_without_a_verdict() -> None:
    """AD-35: the command that computes a claim names it, instead of leaving it to the page."""
    result = RunResult("report", 0, "PASS", "PASS", "n/a", claims=ReviewClaims(2, 3, 0, None, 1))
    summary = report_summary(result)
    assert "2 unreferenced symbol(s)" in summary.claims
    assert "3 component(s) larger than their level" in summary.claims
    assert "0 unread binding(s)" in summary.claims
    # AD-5: a claim that could not be derived says so; it never reports zero findings.
    assert "unknown repetition(s) outside an owner" in summary.claims
    assert "1 type(s) crossing many component boundaries" in summary.claims
    assert summary.decision.label == "PASS" and result.exit_code == 0
    assert "2 unreferenced symbol(s)" in _render(result, summary, 200)
    assert all(len(line) <= 80 for line in _render(result, summary, 80).splitlines())


_ROOTS_REASON = "All source files under shop were read and parsed."


@pytest.mark.parametrize(
    ("result", "summarize"),
    [
        (RunResult("validate", 0, "PASS", "PASS", "n/a", scan_roots=("shop",)), report_summary),
        (replace(FAILED_CHECK, scan_roots=("shop",)), check_summary),
    ],
    ids=["validate", "check"],
)
def test_scan_complete_names_the_roots_it_read(
    result: RunResult, summarize: Callable[[RunResult], Summary]
) -> None:
    """AD-101: every command that scans says which roots, so a PASS never covers the tests."""
    (scan, *_) = summarize(result).verdicts
    assert scan.reason == _ROOTS_REASON
    assert scan.reason in _render(result, summarize(result), 200)


def test_scan_complete_without_recorded_roots_keeps_its_old_reason() -> None:
    unscoped = report_summary(RunResult("report", 0, "PASS", "PASS", "n/a")).verdicts[0]
    assert unscoped.reason == "All configured source files were read and parsed."
    (check_scan, *_) = check_summary(FAILED_CHECK).verdicts
    assert check_scan.reason == "The configured source scope was parsed."


def test_terminal_view_omits_the_claim_line_when_no_claim_was_derived() -> None:
    assert report_summary(RunResult("report", 0, "PASS", "PASS", "n/a")).claims == ""


def test_terminal_svg_export_keeps_adjacent_styled_text_on_fallback_columns(
    tmp_path, monkeypatch
) -> None:
    """The documented fallback font keeps styled badge and reason runs separated."""
    from xml.etree import ElementTree

    from rich.cells import cell_len

    from tools import terminal_svg

    check_text = "× REJECT Do not merge: calls_unresolved rose 0 → 1"
    inside_text = "✓ PASS All source files under sample were read."
    monkeypatch.setattr(
        terminal_svg,
        "capture",
        lambda command, *, expected_exit_code, required_output=(): (
            "× \x1b[31mREJECT\x1b[0m Do not merge: calls_unresolved rose 0 → 1"
        ),
    )
    monkeypatch.setattr(
        terminal_svg,
        "capture_inside_violation",
        lambda: "✓ \x1b[32mPASS\x1b[0m All source files under sample were read.",
    )
    (tmp_path / "commands.json").write_text(
        '[{"command":"archkeel check --root fixture --config archkeel.toml","exit_code":1}]',
        encoding="utf-8",
    )

    exported_paths = terminal_svg.export(tmp_path)
    assert [path.name for path in exported_paths] == [
        "fixture-check-terminal.svg",
        "archkeel-shop-inside-violation.svg",
    ]
    char_width = 20 * 0.61
    for path, expected in zip(exported_paths, (check_text, inside_text), strict=True):
        root = ElementTree.parse(path).getroot()
        text_runs = [
            run
            for run in root.findall(".//{http://www.w3.org/2000/svg}text")
            if not run.attrib.get("class", "").endswith("-title") and run.text != "\n"
        ]
        actual = "".join(run.text or "" for run in text_runs).replace("\u00a0", " ")
        assert actual == expected
        column = 0
        for run in text_runs:
            width = cell_len(run.text or "")
            assert float(run.attrib["x"]) == pytest.approx(column * char_width)
            assert float(run.attrib["textLength"]) == pytest.approx(width * char_width)
            assert run.attrib["lengthAdjust"] == "spacingAndGlyphs"
            column += width


_OPEN_PAIR = OpenDecision(
    source="core",
    target="cli",
    source_package="sample.core",
    target_package="sample.cli",
    observed=True,
    import_sites=3,
    forbidden_option=ForbiddenDependencyRule(
        id="DEP-CORE-NO-CLI",
        kind="forbidden_dependency",
        source="sample.core",
        target="sample.cli",
        include_type_checking=True,
        rationale="Decide this pair.",
        provenance=("docs/architecture/sample.md",),
        decided_by="architect",
    ),
    allowed_option=AllowedDependencyRule(
        id="DEP-CORE-ALLOWS-CLI",
        kind="allowed_dependency",
        source="sample.core",
        target="sample.cli",
        rationale="Decide this pair.",
        provenance=("docs/architecture/sample.md",),
        decided_by="architect",
    ),
)


@pytest.mark.parametrize("verdict", ["PASS", "FAIL", "UNKNOWN"])
def test_report_headline_keeps_the_rule_verdict_with_open_decisions(verdict: str) -> None:
    result = RunResult("report", 0, "PASS", verdict, "n/a", open_decisions=(_OPEN_PAIR,))
    summary = report_summary(result)

    assert summary.decision.state == {"PASS": "pass", "FAIL": "fail", "UNKNOWN": "unknown"}[verdict]
    assert "1 open decision(s) remain" in summary.sentence
    assert "core -> cli: 3 import site(s)" in summary.sentence
    assert "The declared target is incomplete" not in summary.sentence


def test_report_names_bounded_fail_and_unknown_rules_without_a_second_verdict() -> None:
    assessments = tuple(
        RuleAssessment(
            name, "complete_requires", status, False, 0, 0, "architect", "", (), "", "pkg", ()
        )
        for name, status in (
            ("PASS-ONE", "PASS"),
            ("UNKNOWN-ONE", "UNKNOWN"),
            ("FAIL-ONE", "FAIL"),
            ("FAIL-TWO", "FAIL"),
            ("FAIL-THREE", "FAIL"),
            ("FAIL-FOUR", "FAIL"),
        )
    )
    result = RunResult("report", 0, "PASS", "FAIL", "n/a", rule_assessments=assessments)
    summary = report_summary(result)
    assert summary.decision.label == "FAIL"
    assert "FAIL rules: FAIL-ONE, FAIL-TWO, FAIL-THREE (+1 more)." in summary.sentence
    assert "UNKNOWN rules: UNKNOWN-ONE." in summary.sentence
    assert "PASS-ONE" not in summary.sentence
    assert "archkeel validate --baseline architecture-baseline.json" in summary.sentence
    assert "--accept-new" not in summary.sentence
    assert report_summary(replace(result, declared_rules="PASS")).decision.label == "PASS"


@pytest.mark.parametrize(
    "declared, label", [("FAIL", "FAIL"), ("PASS", "REJECT"), ("UNKNOWN", "REJECT")]
)
def test_completed_validation_diagnostics_do_not_claim_nothing_checked(declared, label) -> None:
    result = replace(
        _REPORT_FAIL,
        command="validate",
        exit_code=2,
        declared_rules=declared,
        diagnostics=(_DIAGNOSTIC,),
    )
    summary = report_summary(result)
    assert summary.decision.label == label
    rendered = _render(result, summary, 80)
    assert "Nothing was checked" not in rendered
    if declared != "UNKNOWN":
        assert "NOT CHECKED" not in rendered
    assert "Scan complete" in rendered and "PASS" in rendered


@pytest.mark.parametrize(
    "module",
    ["shop.store", "platform.data_processing.repository." + "very_long_component_name_" * 4],
)
def test_unknown_ownership_reason_preserves_long_ids_and_tokens_at_80_columns(module: str) -> None:
    identifier = "platform:data_processing:repository:BOUNDARY-EXPORTED-INTERFACES" + ":INNER" * 5
    file = module.replace(".", "/") + "/__init__.py"
    reason = (
        f"{module} ({file}) has no owner in scope repository. "
        f'Assign it to one existing component using exact_modules: ["{module}"].'
    )
    assessment = RuleAssessment(
        id=identifier,
        kind="interface_boundary",
        status="UNKNOWN",
        evaluation_proven=False,
        count=0,
        undecided=0,
        decided_by="architect",
        rationale="Own the facade.",
        provenance=(),
        reason=reason,
        scope="repository",
        components=(),
    )
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", rule_assessments=(assessment,))
    narrow = _render(result, report_summary(result), 80)
    assert all(len(line) <= 80 for line in narrow.splitlines())
    assert "…" not in narrow
    compact = "".join(narrow.split())
    for value in (identifier, module, file, f'exact_modules: ["{module}"]'):
        assert "".join(value.split()) in compact
