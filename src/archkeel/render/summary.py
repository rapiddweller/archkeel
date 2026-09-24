# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explain command results in the words shared by the HTML and terminal views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from archkeel.ir.measurements import compare_measurements
from archkeel.ir.model import DraftedComponentSize, RunResult

State: TypeAlias = Literal["pass", "fail", "info", "unknown"]
Comparison: TypeAlias = tuple[str, str, str, str]
# AD-100: a rejected run names this many unresolved call sites; the JSON result names all.
_CALL_SITES_SHOWN: Final = 5


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
    # AD-35: the terminal's one claim line. The HTML shows the same claims as full tables.
    claims: str = ""
    # AD-100: a heading, then one line per unresolved call site; empty without failures.
    call_sites: tuple[str, ...] = ()


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


def report_lacks_decisions(result: RunResult) -> bool:
    """Whether a completed report rests on a target that leaves pairs undecided (AD-23)."""
    return result.command == "report" and result.exit_code == 0 and bool(result.open_decisions)


def check_leaves_a_verdict_undecided(result: RunResult) -> bool:
    """Whether a passing check carries a verdict nothing decided (AD-72).

    The exit code stops at FAIL by design, so it cannot answer this on its own: a run that
    decided nothing wrong and a run that could not decide everything both leave it at 0.
    """
    return (
        result.command == "check"
        and result.exit_code == 0
        and any(value == "UNKNOWN" for _label, _key, value in _check_verdict_values(result))
    )


def report_leaves_rules_undecided(result: RunResult) -> bool:
    """Whether a completed report or validation could not decide its declared rules."""
    return (
        result.command in {"report", "validate"}
        and result.exit_code == 0
        and result.declared_rules == "UNKNOWN"
    )


def _decision_badge(result: RunResult) -> Badge:
    if report_violates_rules(result) or report_lacks_decisions(result):
        return badge("FAIL")
    if check_leaves_a_verdict_undecided(result) or report_leaves_rules_undecided(result):
        return badge("UNKNOWN")
    if result.exit_code == 0:
        return Badge("pass", "✓", "PASS")
    if result.exit_code == 1:
        return Badge("fail", "×", "REJECT")
    return Badge("unknown", "?", "NOT CHECKED")


def _agent_decisions_line(result: RunResult) -> str:
    """Name agent-decided rules, edges and interfaces awaiting the architect (AD-50)."""
    if not result.agent_decisions or not result.agent_decisions[0]:
        return ""
    agent, total = result.agent_decisions
    return f"\n\n{agent} of {total} decisions made by the agent, awaiting the architect."


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


def _report_filter_line(result: RunResult) -> str:
    """Name the filter narrowing a rendered report, so a partial count is never read as the
    total (AD-60). The one sentence terminal and HTML share; JSON carries the same filter in
    `report_filter`, so all three name it the same way."""
    report_filter = result.report_filter
    if report_filter is None:
        return ""
    facets = []
    if report_filter.only_violations:
        facets.append("only violations")
    if report_filter.only_calls:
        facets.append("only calls")
    if report_filter.rule is not None:
        facets.append(f"rule {report_filter.rule}")
    if report_filter.component is not None:
        facets.append(f"component {report_filter.component}")
    if result.filtered_calls is not None:
        listed = len(result.filtered_calls)
        return (
            f"\n\nFiltered ({', '.join(facets)}): {listed} unresolved or partially resolved "
            "call(s) listed."
        )
    shown = len(result.filtered_violations) if result.filtered_violations is not None else 0
    total = result.measurements.scalars.violations if result.measurements is not None else shown
    return f"\n\nFiltered ({', '.join(facets)}): {shown} of {total} violation(s) shown."


def _claims_line(result: RunResult) -> str:
    """Name what each review claim found, never as a verdict (AD-26, AD-35); silent when absent."""
    claims = result.claims
    if claims is None:
        return ""
    counted = ", ".join(
        f"{'unknown' if value is None else value} {label}"
        for label, value in (
            ("unreferenced symbol(s)", claims.unreferenced_symbols),
            ("component(s) larger than their level", claims.oversized_components),
            ("unread binding(s)", claims.unread_bindings),
            ("repetition(s) outside an owner", claims.repeated_logic),
            ("type(s) crossing many component boundaries", claims.type_fanin),
        )
    )
    return f"Review claims, never a verdict: {counted}."


def _call_site_lines(result: RunResult) -> tuple[str, ...]:
    """Name the unresolved call sites behind a run's failures, a few at most, or why none is
    named (AD-100)."""
    if not result.failures:
        return ()
    if result.unresolved_call_note is not None:
        return (f"Unresolved call sites: {result.unresolved_call_note}",)
    changes = result.unresolved_call_changes
    if not changes:
        return ()
    added = sum(item.change == "added" for item in changes)
    lines = [f"Unresolved call sites: {added} added, {len(changes) - added} removed"]
    for item in changes[:_CALL_SITES_SHOWN]:
        sign = "+" if item.change == "added" else "-"
        where = f"{item.path}:{','.join(str(line) for line in item.lines)}"
        count = f" ({item.before}->{item.after})" if item.before and item.after else ""
        lines.append(
            f"  {sign} {where} {item.caller}: {item.expression}() "
            f"[{item.component or 'no component'}] {item.reason}{count}"
        )
    if len(changes) > _CALL_SITES_SHOWN:
        lines.append(
            f"  +{len(changes) - _CALL_SITES_SHOWN} more in the JSON result's "
            "unresolved_call_changes"
        )
    return tuple(lines)


def _baseline_line(result: RunResult) -> str:
    if result.baseline_new is None or result.baseline_resolved is None:
        return ""
    return f"\n\nBaseline drift: {result.baseline_new} new, {result.baseline_resolved} resolved."


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
    elif report_lacks_decisions(result):
        # AD-23: a target that decides nothing cannot be met, so the headline must not pass.
        sentence = (
            "The declared target is incomplete, so this report cannot pass. "
            "Run archkeel validate for the worklist."
        )
    elif report_leaves_rules_undecided(result):
        sentence = (
            "The requested deterministic checks completed, but declared rules could not be "
            "evaluated completely."
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
    sentence += (
        _report_filter_line(result)
        + _open_decisions_lines(result)
        + _agent_decisions_line(result)
        + _baseline_line(result)
    )
    return Summary(
        _decision_badge(result),
        sentence,
        verdicts,
        (),
        _claims_line(result),
        _call_site_lines(result),
    )


def _largest_draft(
    sizes: tuple[DraftedComponentSize, ...],
) -> DraftedComponentSize | None:
    """Return the drafted component whose module count uniquely leads, or None (AD-38)."""
    if not sizes:
        return None
    ranked = sorted(sizes, key=lambda item: item.modules, reverse=True)
    if len(ranked) == 1 or ranked[0].modules > ranked[1].modules:
        return ranked[0]
    return None


def _draft_sizes_line(result: RunResult) -> str:
    """Name the drafted component that stands out in size, or that none does; silent when
    `init` did not measure a draft at all (AD-38)."""
    if result.draft_sizes is None:
        return ""
    largest = _largest_draft(result.draft_sizes)
    if largest is None:
        return "\n\nNo drafted component stands out in size."
    return (
        f"\n\n`{largest.label}` is the largest drafted component: "
        f"{largest.modules} module(s), {largest.inner_edges} inner edge(s)."
    )


def init_summary(result: RunResult) -> Summary:
    """Summarize onboarding, whose drafted rules are evaluated later by validate."""
    report = report_summary(result)
    sentence = (
        "Draft written. Run archkeel validate to list every decision left."
        + _open_decisions_lines(result)
        + _draft_sizes_line(result)
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
    return Summary(
        _decision_badge(result),
        check_decision_sentence(result),
        verdicts,
        regressions,
        call_sites=_call_site_lines(result),
    )


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
    if check_leaves_a_verdict_undecided(result):
        undecided = [
            label for label, _key, value in _check_verdict_values(result) if value == "UNKNOWN"
        ]
        return f"Read before merging: {' and '.join(undecided).lower()} could not be decided."
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
