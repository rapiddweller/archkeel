# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path

from archkeel.ir.baseline import (
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
    RunResult,
)
from archkeel.ir.rule_assessment import rule_assessments

from .git import git_bytes
from .ports import Analyzer, ScanConfig
from .ratchets import call_rows, calls_measured
from .run import inspect_observation
from .snapshot import resolve_commit


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
    """Observe, evaluate and, when a filter argument narrows it, select what the report shows.

    `cli` hands in the three plain arguments it parsed, never a `ReportFilter`: composing a
    typed `ir` value is this function's job, the same split `cli` already keeps with every
    other command (AD-60). The filter never reaches `canonical_report_bytes`: `architecture
    .json` is built from `model` before any filter argument is even read, so a filtered run
    writes the same bytes an unfiltered one would. A `rule` or `component` naming nothing this
    observation declares raises `DiagnosticError` inside `select_violations`, caught below
    exactly like `inspect_observation`'s own `ValueError`, so an unknown filter value is a
    named exit-2 diagnostic, never a silently empty report.
    """
    report_filter = (
        ReportFilter(only_violations, rule, component, only_calls)
        if only_violations or only_calls or rule is not None or component is not None
        else None
    )
    result = observe_repository(root, config, analyzer)
    model = result.observation
    architecture = canonical_report_bytes(model) if model is not None else None
    if result.diagnostics or model is None:
        command_result = RunResult(
            "report",
            2,
            diagnostics=result.diagnostics,
            coverage=result.coverage,
            python_version=model.python_version if model is not None else None,
        )
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
            comparisons: tuple[BaselineViolationComparison, ...] | None = None
            baseline_name: str | None = None
            if baseline is not None:
                baseline_file = baseline if baseline.is_absolute() else root / baseline
                baseline_file = baseline_file.resolve()
                try:
                    baseline_file.relative_to(root.resolve())
                    known = parse_validation_baseline(decode_json(baseline_file.read_bytes()))
                except (OSError, ValueError) as error:
                    raise ValueError(f"cannot read baseline {baseline}: {error}") from error
                known_counts = Counter({item.fingerprint: item.count for item in known.violations})
                current = observed_violations(model)
                current_counts = Counter({item.fingerprint: item.count for item in current})
                cycle_rules = frozenset(
                    record.id
                    for section in model.sections
                    for record in section.records
                    if record.evidence_class.value == "DECLARED_RULE"
                    and record.kind == "no_component_cycles"
                )
                contracted = cycle_contractions(known.violations, current, cycle_rules=cycle_rules)
                comparisons = tuple(
                    BaselineViolationComparison(
                        fingerprint.rules,
                        fingerprint.subjects,
                        min(before, after),
                        after,
                        0 if fingerprint in contracted else max(after - before, 0),
                        max(before - after, 0),
                        (
                            "contracted"
                            if fingerprint in contracted
                            else "new"
                            if after > before
                            else "resolved"
                            if after == 0 and before > 0
                            else "reduced"
                            if after < before
                            else "known"
                        ),
                    )
                    for fingerprint in sorted(
                        known_counts.keys() | current_counts.keys(),
                        key=lambda item: (item.rules, item.subjects),
                    )
                    for before, after in (
                        (known_counts.get(fingerprint, 0), current_counts.get(fingerprint, 0)),
                    )
                )
                baseline_name = str(baseline_file.relative_to(root.resolve()))
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
                rule_assessments=rule_assessments(model),
                baseline_path=baseline_name,
                baseline_comparisons=comparisons,
            )
    return command_result, architecture
