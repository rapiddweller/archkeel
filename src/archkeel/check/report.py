# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import subprocess
from dataclasses import replace
from pathlib import Path

from archkeel.ir.baseline import select_violations
from archkeel.ir.codec import canonical_report_bytes, result_bytes
from archkeel.ir.decisions import (
    agent_decisions,
    open_decisions,
    review_claims,
    violation_counts,
)
from archkeel.ir.model import (
    Diagnostic,
    DiagnosticError,
    ObservationResult,
    ReportFilter,
    RunResult,
)

from .git import git_bytes
from .ports import Analyzer, ScanConfig
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


def run_report(
    root: Path,
    *,
    config: ScanConfig,
    analyzer: Analyzer,
    only_violations: bool = False,
    rule: str | None = None,
    component: str | None = None,
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
        ReportFilter(only_violations, rule, component)
        if only_violations or rule is not None or component is not None
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
                select_violations(model, report_filter) if report_filter is not None else None
            )
        except ValueError as error:
            command_result = replace(
                unknown_result("report", "observation", error),
                coverage=model.coverage,
                python_version=model.python_version,
            )
        else:
            counted = violation_counts(model)
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
            )
    return command_result, architecture
