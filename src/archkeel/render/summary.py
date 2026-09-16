# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explain command results in the words shared by the HTML and terminal views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from archkeel.ir.measurements import compare_measurements
from archkeel.ir.model import RunResult

State: TypeAlias = Literal["pass", "fail", "info", "unknown"]
Comparison: TypeAlias = tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class Badge:
    state: State
    symbol: str
    label: str


@dataclass(frozen=True, slots=True)
class VerdictRow:
    label: str
    key: str
    value: str
    reason: str


@dataclass(frozen=True, slots=True)
class Summary:
    decision: Badge
    sentence: str
    verdicts: tuple[VerdictRow, ...]
    regressions: tuple[Comparison, ...]


def badge(value: str) -> Badge:
    if value == "PASS":
        return Badge("pass", "✓", "PASS")
    if value == "FAIL":
        return Badge("fail", "×", "FAIL")
    if value == "n/a":
        return Badge("info", "i", "NOT APPLICABLE")
    return Badge("unknown", "?", "NOT CHECKED")


def report_violates_rules(result: RunResult) -> bool:
    """Whether a completed report found violations its exit code does not express (AD-14)."""
    return result.command == "report" and result.exit_code == 0 and result.declared_rules == "FAIL"


def _decision_badge(result: RunResult) -> Badge:
    if report_violates_rules(result):
        return badge("FAIL")
    if result.exit_code == 0:
        return Badge("pass", "✓", "PASS")
    if result.exit_code == 1:
        return Badge("fail", "×", "REJECT")
    return Badge("unknown", "?", "NOT CHECKED")


def _agent_decisions_line(result: RunResult) -> str:
    """Name agent-decided rules still awaiting the architect (AD-16); silent when none."""
    if not result.agent_decisions or not result.agent_decisions[0]:
        return ""
    agent, total = result.agent_decisions
    return f"\n\n{agent} of {total} rules decided by the agent, awaiting the architect."


def _open_decisions_lines(result: RunResult) -> str:
    """Name the open decisions left, heaviest observed edges first; never their rule JSON."""
    if not result.open_decisions:
        return ""
    header = f"\n\n{len(result.open_decisions)} open decision(s) remain."
    heaviest = [item for item in result.open_decisions if item.observed][:5]
    if not heaviest:
        return header
    lines = "\n".join(
        f"  {item.source} -> {item.target}: {item.import_sites} import site(s)" for item in heaviest
    )
    return f"{header} Heaviest observed:\n{lines}"


def report_summary(result: RunResult) -> Summary:
    """Summarize a report or validate result, which never evaluates an expectation."""
    sentence = {
        0: "All requested deterministic checks completed.",
        1: "One or more deterministic checks rejected the candidate.",
        2: "Nothing was checked: the evidence needed for a decision is missing or invalid.",
    }[result.exit_code]
    if report_violates_rules(result):
        found = (
            f"{result.measurements.scalars.violations} declared-rule violation(s) found"
            if result.measurements is not None
            else "Declared rules are violated"
        )
        sentence = (
            f"{found}; report records violations without gating (exit code stays 0). "
            "Run archkeel check to gate on rule violations."
        )
    observation_reason = (
        "All configured source files were read and parsed."
        if result.observation_complete == "PASS"
        else "The configured source scope could not be observed completely."
    )
    rules_reason = {
        "PASS": "No declared-rule violation was found.",
        "FAIL": "At least one declared rule was violated.",
        "UNKNOWN": "Declared rules could not be evaluated completely.",
    }[result.declared_rules]
    expectation_reason = {
        "PASS": "The candidate matches its published expectation.",
        "FAIL": "The candidate does not match its published expectation.",
        "UNKNOWN": "The expectation could not be evaluated completely.",
        "n/a": "Report mode does not evaluate a published expectation.",
    }[result.expectation_fulfilled]
    verdicts = (
        VerdictRow(
            "Scan complete", "observation_complete", result.observation_complete, observation_reason
        ),
        VerdictRow("Rules followed", "declared_rules", result.declared_rules, rules_reason),
        VerdictRow(
            "Change as declared",
            "expectation_fulfilled",
            result.expectation_fulfilled,
            expectation_reason,
        ),
    )
    sentence += _open_decisions_lines(result) + _agent_decisions_line(result)
    return Summary(_decision_badge(result), sentence, verdicts, ())


def init_summary(result: RunResult) -> Summary:
    """Summarize onboarding, whose drafted rules are evaluated later by validate."""
    report = report_summary(result)
    sentence = (
        "Draft written. Run archkeel validate to list every decision left."
        + _open_decisions_lines(result)
        if result.exit_code == 0
        else report.sentence
    )
    return Summary(report.decision, sentence, report.verdicts[:1], ())


def check_summary(result: RunResult) -> Summary:
    """Summarize a check result with its five verdicts and regression comparisons."""
    regressions = _check_regressions(result)
    verdicts = tuple(
        VerdictRow(label, key, value, _check_verdict_reason(result, key, value, regressions))
        for label, key, value in _check_verdict_values(result)
    )
    return Summary(_decision_badge(result), check_decision_sentence(result), verdicts, regressions)


def _check_verdict_values(result: RunResult) -> tuple[tuple[str, str, str], ...]:
    return (
        ("Scan complete", "observation_complete", result.observation_complete),
        ("Rules followed", "declared_rules", result.declared_rules),
        ("Change as declared", "expectation_fulfilled", result.expectation_fulfilled),
        ("Git order", "git_predicate", result.git_predicate or "UNKNOWN"),
        ("Publication order", "host_order", result.host_order or "UNKNOWN"),
    )


def _check_regressions(result: RunResult) -> tuple[Comparison, ...]:
    ratchets = result.delta.ratchets if result.delta is not None else None
    if (
        ratchets is None
        or ratchets.status != "SUPPORTED"
        or ratchets.baseline is None
        or ratchets.head is None
    ):
        return ()
    comparisons = compare_measurements(ratchets.baseline, ratchets.head)
    return tuple(sorted(comparisons, key=lambda item: item[3] != "FAIL"))


def _check_verdict_reason(
    result: RunResult,
    key: str,
    value: str,
    comparisons: tuple[Comparison, ...],
) -> str:
    if value == "UNKNOWN":
        return {
            "observation_complete": "The scan could not be completed.",
            "declared_rules": "The rules could not be evaluated.",
            "expectation_fulfilled": "The declared change could not be checked.",
            "git_predicate": "The commit order could not be established.",
            "host_order": "The publication time could not be established.",
        }[key]
    if value == "FAIL":
        failed = sum(status == "FAIL" for *_, status in comparisons)
        return {
            "declared_rules": "At least one declared rule was violated.",
            "expectation_fulfilled": (
                f"{failed} of {len(comparisons)} regression checks failed."
                if failed
                else "One or more expectation checks failed."
            ),
            "git_predicate": "Git ancestry or the expectation path failed validation.",
            "host_order": "Expectation published after first submission.",
        }[key]
    if key == "observation_complete" and result.coverage is not None:
        return f"All {result.coverage.files_parsed} files parsed."
    return {
        "observation_complete": "The configured source scope was parsed.",
        "declared_rules": "No declared-rule violation was found.",
        "expectation_fulfilled": "No undeclared change or regression was found.",
        "git_predicate": "Git predicates verified.",
        "host_order": "Published before candidate submission.",
    }[key]


def check_decision_sentence(result: RunResult) -> str:
    """Explain a check decision from structured result fields."""
    if result.exit_code == 2:
        diagnostic = result.diagnostics[0]
        return f"Do not merge: {diagnostic.kind} — {diagnostic.unknown_claim}"
    if result.exit_code == 0:
        return "Merge: all five verdicts passed and no regression check failed."
    failed = [row for row in _check_regressions(result) if row[3] == "FAIL"]
    if failed:
        reasons = [
            f"{name} {before} → {after}"
            if name == "unresolved_ratio"
            else f"{name} rose {before} → {after}"
            for name, before, after, _ in failed
        ]
        shown = reasons[:3]
        if len(reasons) > 3:
            shown.append(f"+{len(reasons) - 3} more")
        detail = shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} and {shown[-1]}"
        return f"Do not merge: {detail}."
    if result.host_order == "FAIL":
        return (
            "Do not merge: the expectation was not published before the first candidate submission."
        )
    failed_verdicts = sum(value == "FAIL" for _, _, value in _check_verdict_values(result))
    return f"Do not merge: {failed_verdicts} of five verdicts failed."
