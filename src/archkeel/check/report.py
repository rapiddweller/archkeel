# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Literal

from archkeel.ir.baseline import (
    ViolationFingerprint,
    cycle_contractions,
    observed_violations,
    require_declared_filter,
    select_violations,
)
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_json,
    parse_validation_baseline,
    result_bytes,
)
from archkeel.ir.decisions import (
    agent_decisions,
    open_decisions,
    review_claims,
    violation_counts,
)
from archkeel.ir.model import (
    BaselineViolationComparison,
    CallRow,
    Diagnostic,
    DiagnosticError,
    Observation,
    ObservationResult,
    ReportFilter,
    RuleAssessment,
    RunResult,
)
from archkeel.ir.rule_assessment import rule_assessments

from .git import git_bytes
from .ports import Analyzer, ScanConfig
from .ratchets import call_rows, calls_measured, unknown_positions_by_rule
from .run import inspect_observation
from .snapshot import resolve_commit


def _baseline_report(
    root: Path,
    baseline: Path,
    model: Observation,
    current_rules: dict[str, RuleAssessment],
) -> tuple[str, tuple[BaselineViolationComparison, ...]]:
    baseline_file = baseline if baseline.is_absolute() else root / baseline
    baseline_file = baseline_file.resolve()
    try:
        baseline_file.relative_to(root.resolve())
        known = parse_validation_baseline(decode_json(baseline_file.read_bytes()))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read baseline {baseline}: {error}") from error
    known_counts: Counter[ViolationFingerprint] = Counter(
        {item.fingerprint: item.count for item in known.violations}
    )
    current = observed_violations(model)
    current_counts: Counter[ViolationFingerprint] = Counter(
        {item.fingerprint: item.count for item in current}
    )
    cycle_rules = frozenset(
        record.id
        for record in model.records("declarations") or ()
        if record.evidence_class.value == "DECLARED_RULE" and record.kind == "no_component_cycles"
    )
    contracted = cycle_contractions(known.violations, current, cycle_rules=cycle_rules)
    comparisons = _baseline_comparisons(known_counts, current_counts, contracted, current_rules)
    return str(baseline_file.relative_to(root.resolve())), comparisons


def _baseline_comparisons(
    known_counts: Counter[ViolationFingerprint],
    current_counts: Counter[ViolationFingerprint],
    contracted: frozenset[ViolationFingerprint],
    current_rules: dict[str, RuleAssessment],
) -> tuple[BaselineViolationComparison, ...]:
    return tuple(
        BaselineViolationComparison(
            fingerprint.rules,
            fingerprint.subjects,
            before,
            min(before, after),
            after,
            0 if fingerprint in contracted else max(after - before, 0),
            max(before - after, 0) if _resolved_is_proven(fingerprint.rules, current_rules) else 0,
            _baseline_status(fingerprint, before, after, contracted, current_rules),
        )
        for fingerprint in sorted(
            known_counts.keys() | current_counts.keys(),
            key=lambda item: (item.rules, item.subjects),
        )
        for before, after in (
            (known_counts.get(fingerprint, 0), current_counts.get(fingerprint, 0)),
        )
    )


def _resolved_is_proven(
    rule_ids: tuple[str, ...], current_rules: dict[str, RuleAssessment]
) -> bool:
    return all(
        (assessment := current_rules.get(rule_id)) is not None
        and assessment.evaluation_proven
        and assessment.status in {"PASS", "FAIL"}
        and assessment.undecided == 0
        for rule_id in rule_ids
    )


def _baseline_status(
    fingerprint: ViolationFingerprint,
    before: int,
    after: int,
    contracted: frozenset[ViolationFingerprint],
    current_rules: dict[str, RuleAssessment],
) -> Literal["known", "new", "reduced", "resolved", "contracted", "unknown"]:
    if after < before and not _resolved_is_proven(fingerprint.rules, current_rules):
        return "unknown"
    if fingerprint in contracted:
        return "contracted"
    if after > before:
        return "new"
    if after == 0 and before > 0:
        return "resolved"
    if after < before:
        return "reduced"
    return "known"


def unknown_result(command: str, subject: str, error: Exception) -> RunResult:
    if isinstance(error, DiagnosticError):
        diagnostic = error.diagnostic
    else:
        diagnostic = Diagnostic(
            "timeout" if isinstance(error, subprocess.TimeoutExpired) else "parse_error",
            subject,
            f"The {command} result cannot be established: {error}",
            "Repair the reported input or execution failure and retry.",
        )
    return RunResult(command, 2, diagnostics=(diagnostic,))


def render_result(result: RunResult) -> bytes:
    return result_bytes(result)


def observe_repository(
    root: Path, config: ScanConfig, analyzer: Analyzer, *, contract_root: Path | None = None
) -> ObservationResult:
    """Observe the configured working tree through an injected analyzer."""
    return analyzer(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=resolve_commit(root, "HEAD"),
        dirty=bool(git_bytes(root, "status", "--porcelain", "--untracked-files=all")),
        contract_root=contract_root or root,
        language=config.language,
    )


def _selected_calls(model: Observation, report_filter: ReportFilter) -> tuple[CallRow, ...]:
    """AD-100: `--only calls`, narrowed by `--component` to the calls its modules make.

    A profile that does not measure calls has none to list, and an empty list would read as a
    count it never took: refused like an unsupported rule (AD-97).
    """
    if not calls_measured(model):
        raise DiagnosticError(
            Diagnostic(
                "rule_unsupported_by_profile",
                "--only calls",
                f"The {model.analyzer.name} profile does not measure calls, so it has none "
                "to list.",
                "Drop --only calls; only the Python profile lists unresolved calls.",
            )
        )
    require_declared_filter(model, report_filter)
    return tuple(
        row
        for row in call_rows(model)
        if report_filter.component is None or row.component == report_filter.component
    )


def _report_filter(
    only_violations: bool, rule: str | None, component: str | None, only_calls: bool
) -> ReportFilter | None:
    if only_violations or only_calls or rule is not None or component is not None:
        return ReportFilter(only_violations, rule, component, only_calls)
    return None


def _incomplete_report_result(result: ObservationResult) -> RunResult:
    model = result.observation
    return RunResult(
        "report",
        2,
        diagnostics=result.diagnostics,
        coverage=result.coverage,
        python_version=model.python_version if model is not None else None,
        rule_assessments=(
            rule_assessments(
                model,
                undecided_by_rule=unknown_positions_by_rule(model),
                complete=False,
            )
            if model is not None
            else None
        ),
    )


def run_report(
    root: Path,
    *,
    config: ScanConfig,
    analyzer: Analyzer,
    only_violations: bool = False,
    rule: str | None = None,
    component: str | None = None,
    only_calls: bool = False,
    baseline: Path | None = None,
) -> tuple[RunResult, bytes | None]:
    """Observe once; report filters and baselines only change the human-readable projection."""
    report_filter = _report_filter(only_violations, rule, component, only_calls)
    result = observe_repository(root, config, analyzer)
    model = result.observation
    architecture = canonical_report_bytes(model) if model is not None else None
    if result.diagnostics or model is None:
        command_result = _incomplete_report_result(result)
    else:
        try:
            measurements, declared = inspect_observation(model)
            filtered_violations = (
                select_violations(model, report_filter)
                if report_filter is not None and not only_calls
                else None
            )
            filtered_calls = (
                _selected_calls(model, report_filter)
                if report_filter is not None and only_calls
                else None
            )
        except ValueError as error:
            command_result = replace(
                unknown_result("report", "observation", error),
                coverage=model.coverage,
                python_version=model.python_version,
            )
        else:
            counted = violation_counts(model)
            assessments = rule_assessments(
                model, undecided_by_rule=unknown_positions_by_rule(model)
            )
            current_rules = {item.id: item for item in assessments}
            comparisons: tuple[BaselineViolationComparison, ...] | None = None
            baseline_name: str | None = None
            if baseline is not None:
                baseline_name, comparisons = _baseline_report(root, baseline, model, current_rules)
            command_result = RunResult(
                "report",
                0,
                observation_complete="PASS",
                declared_rules=declared,
                expectation_fulfilled="n/a",
                coverage=model.coverage,
                measurements=measurements,
                python_version=model.python_version,
                agent_decisions=agent_decisions(model),
                open_decisions=open_decisions(model),
                claims=review_claims(model),
                violations_by_rule=counted.by_rule,
                violations_by_component_pair=counted.by_component_pair,
                report_filter=report_filter,
                filtered_violations=filtered_violations,
                filtered_calls=filtered_calls,
                rule_assessments=assessments,
                baseline_path=baseline_name,
                baseline_comparisons=comparisons,
            )
    return command_result, architecture
