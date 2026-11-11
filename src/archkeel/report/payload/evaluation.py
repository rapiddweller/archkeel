# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Decision of the evaluator that the payload copies (AD-361).

The evaluator decides the status, each rule verdict, its reason and its undecided positions
(AD-92), whether the run has a Target and whether the observation is complete. The producer
copies them and decides none. The Rust core writes the same fields from its own Decision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from archkeel.report.payload.codes import RULE_REASON, RULE_VERDICT

# The reason texts of the evaluator (ir.decisions) and their codes. An UNKNOWN rule with another
# text names its ownership blocker. Any other text is an error: a new reason never passes silently.
_REASONS = {
    "Permission declaration; it does not evaluate conformance.": "declaration",
    "The evaluator recorded one or more violations.": "violations",
    "The observation is incomplete; a complete evaluator scope is not proven.": "scope_incomplete",
    "No complete evaluator receipt exists for this rule and scope.": "no_receipt",
    "The evaluator left one or more positions undecided.": "undecided",
    "The evaluator completed this rule's observed scope without violations.": "evaluated",
    "Declared requires permissions follow the selected layer order.": "evaluated",
}


@dataclass(frozen=True)
class RuleRow:
    """One rule of the Decision: verdict, reason code and undecided positions."""

    id: str
    kind: str
    verdict: str
    evaluated: bool
    violations: int
    undecided: int
    reason: str
    rationale: str
    decided_by: str | None


@dataclass(frozen=True)
class Diagnostic:
    """One diagnostic of the run: why a scan or a proof is incomplete."""

    kind: str
    subject: str
    claim: str


@dataclass(frozen=True)
class Evaluation:
    """The Decision of one run.

    `target` is false when the run has no Target, as in explore (AD-285): a layout contract
    then groups the modules, and the payload treats the run as a run without a contract.
    """

    status: str
    rules: tuple[RuleRow, ...]
    target: bool = True
    observation: str = "PASS"
    diagnostics: tuple[Diagnostic, ...] = ()


def _text(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _number(item: Mapping[str, object], key: str) -> int:
    value = item.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def reason_of(verdict: str, text: str) -> str:
    """Return the reason code of one rule row of the evaluator."""
    if text in _REASONS and _REASONS[text] in RULE_REASON:
        return _REASONS[text]
    if verdict == "UNKNOWN":
        return "ownership_blocker"
    raise ValueError(f"the evaluator gives the unknown reason {text!r} for a {verdict} rule")


def _rule(item: Mapping[str, object]) -> RuleRow:
    verdict = _text(item, "status")
    if verdict not in RULE_VERDICT:
        raise ValueError(f"rule {item.get('id')!r} has the unknown verdict {verdict!r}")
    decided_by = item.get("decided_by")
    return RuleRow(
        id=_text(item, "id"),
        kind=_text(item, "kind"),
        verdict=verdict,
        evaluated=item.get("evaluation_proven") is True,
        violations=_number(item, "count"),
        undecided=_number(item, "undecided"),
        reason=reason_of(verdict, _text(item, "reason")),
        rationale=_text(item, "rationale"),
        decided_by=decided_by if isinstance(decided_by, str) else None,
    )


def evaluation(result: Mapping[str, object]) -> Evaluation:
    """Read the Decision of a command result (`archkeel report --json`)."""
    status = result.get("declared_rules")
    if status not in ("PASS", "FAIL", "UNKNOWN"):
        raise ValueError(f"the command result has the unknown declared_rules status {status!r}")
    rows = result.get("rule_assessments")
    found = result.get("diagnostics")
    observation = result.get("observation_complete")
    return Evaluation(
        status=str(status),
        rules=tuple(
            _rule(item)
            for item in (rows if isinstance(rows, list) else ())
            if isinstance(item, dict)
        ),
        target=result.get("target") != "unavailable",
        observation=observation if isinstance(observation, str) else "UNKNOWN",
        diagnostics=tuple(
            Diagnostic(_text(item, "kind"), _text(item, "subject"), _text(item, "unknown_claim"))
            for item in (found if isinstance(found, list) else ())
            if isinstance(item, dict)
        ),
    )
