# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Persist observations and expose typed command results to the CLI."""

import subprocess
from dataclasses import replace
from pathlib import Path

from codekeel.ir.codec import canonical_report_bytes, result_bytes
from codekeel.ir.model import Diagnostic, DiagnosticError, RunResult
from codekeel.producer import observe

from .git import git_bytes
from .html import render_html
from .ports import Producer, ScanConfig
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
    output: Path | None = None,
    producer: Producer = observe,
) -> RunResult:
    result = producer(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head=resolve_commit(root, "HEAD"),
        dirty=bool(git_bytes(root, "status", "--porcelain", "--untracked-files=all")),
        contract_root=root,
    )
    model = result.observation
    artifact = None
    if model is not None:
        path = output or root / "test-artifacts/architecture/architecture.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_report_bytes(model))
        resolved = path.resolve()
        root = root.resolve()
        artifact = (
            str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)
        )
    if result.diagnostics:
        command_result = RunResult(
            "report",
            2,
            diagnostics=result.diagnostics,
            coverage=result.coverage,
            artifact=artifact,
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
                artifact=artifact,
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
                artifact=artifact,
                python_version=model.python_version,
            )
    if model is not None:
        html_path = path.with_name("interactive.html")
        html_path.write_bytes(
            render_html(
                command_result,
                model,
                repository=root.name,
                architecture_href=path.name,
            )
        )
    return command_result
