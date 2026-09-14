# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build typed report results and canonical observation bytes."""

import subprocess
from dataclasses import replace
from pathlib import Path

from archkeel.ir.codec import canonical_report_bytes, result_bytes
from archkeel.ir.model import Diagnostic, DiagnosticError, RunResult

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


def run_report(
    root: Path,
    *,
    config: ScanConfig,
    analyzer: Analyzer,
) -> tuple[RunResult, bytes | None]:
    result = analyzer(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=resolve_commit(root, "HEAD"),
        dirty=bool(git_bytes(root, "status", "--porcelain", "--untracked-files=all")),
        contract_root=root,
    )
    model = result.observation
    architecture = canonical_report_bytes(model) if model is not None else None
    if result.diagnostics:
        command_result = RunResult(
            "report",
            2,
            diagnostics=result.diagnostics,
            coverage=result.coverage,
            python_version=model.python_version if model is not None else None,
        )
    else:
        assert model is not None
        try:
            measurements, declared = inspect_observation(model)
        except ValueError as error:
            command_result = replace(
                unknown_result("report", "observation", error),
                coverage=model.coverage,
                python_version=model.python_version,
            )
        else:
            command_result = RunResult(
                "report",
                0,
                observation_complete="PASS",
                declared_rules=declared,
                expectation_fulfilled="n/a",
                coverage=model.coverage,
                measurements=measurements,
                python_version=model.python_version,
            )
    return command_result, architecture
