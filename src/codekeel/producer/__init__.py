# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the bundled Python analyzer in an isolated process."""

import os
import subprocess
import sys
from pathlib import Path

from codekeel.ir.codec import canonical_json_bytes, decode_json, parse_observation
from codekeel.ir.model import Diagnostic, DiagnosticKind, Observation, ObservationResult

from .runtime import runtime_diagnostic


def _failure(kind: DiagnosticKind, subject: str, claim: str, remedy: str) -> ObservationResult:
    return ObservationResult(None, None, (Diagnostic(kind, subject, claim, remedy),))


def _diagnostics(model: Observation, runtime: Diagnostic | None) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for failure in model.coverage.failures:
        if failure.kind != "rule-without-subjects" and runtime is not None:
            diagnostics.append(runtime)
            continue
        missing_subjects = failure.kind == "rule-without-subjects"
        diagnostics.append(
            Diagnostic(
                "rule_without_subjects" if missing_subjects else "parse_error",
                ", ".join(failure.rule_ids or failure.subjects) or failure.id,
                f"Scan completeness cannot be established: {failure.title}",
                "Correct the rule selectors or scan scope."
                if missing_subjects
                else "Inspect the reported failure using the declared target runtime; "
                "rerun after resolving its cause.",
            )
        )
    if runtime is not None and runtime not in diagnostics:
        diagnostics.append(runtime)
    if model.coverage.files_discovered == 0:
        diagnostics.append(
            Diagnostic(
                "scope_empty",
                ", ".join(model.source.scope) or "scan.roots",
                "The configured scope contains no observable Python files.",
                "Set scan.roots to an existing Python source directory.",
            )
        )
    if model.coverage.rules is None:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage.rules",
                "Rule applicability coverage is missing.",
                "Reinstall a complete Codekeel distribution.",
            )
        )
    if model.coverage.status == "FAIL" and not diagnostics:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage",
                "The analyzer reported incomplete coverage without a cause.",
                "Inspect the analyzer coverage and repair its inputs.",
            )
        )
    return tuple(diagnostics)


def observe(
    source_root: Path,
    *,
    roots: tuple[str, ...],
    namespace: str,
    contract: str,
    git_head: str,
    dirty: bool,
    contract_root: Path,
) -> ObservationResult:
    source_root = source_root.resolve()
    try:
        for root in roots:
            directory = source_root / root
            if not directory.is_dir():
                return _failure(
                    "scope_empty",
                    root,
                    "The scan root does not exist.",
                    "Correct scan.roots in codekeel.toml.",
                )
            for path in directory.rglob("*.py"):
                if not path.resolve().is_relative_to(source_root):
                    return _failure(
                        "parse_error",
                        str(path),
                        "Source path escapes repository.",
                        "Remove the source symlink or correct the scan scope.",
                    )
        request = {
            "source_root": str(source_root),
            "git_head": git_head,
            "dirty": dirty,
            "contract_root": str(contract_root.resolve()),
            "contract": contract,
            "roots": roots,
            "namespace": namespace,
        }
        result = subprocess.run(
            [sys.executable, "-B", "-m", "codekeel.producer.bridge"],
            cwd=source_root,
            input=canonical_json_bytes(request).decode(),
            text=True,
            capture_output=True,
            timeout=60,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        if result.returncode:
            return _failure(
                "parse_error",
                "bundled Python analyzer",
                f"Analyzer execution failed: {result.stderr.strip()}",
                "Repair the analyzer failure and run report again.",
            )
        response = decode_json(result.stdout)
        if not isinstance(response, dict) or set(response) != {"model", "exit_code"}:
            raise ValueError("invalid analyzer response envelope")
        code = response["exit_code"]
        if type(code) is not int or code not in (0, 2):
            raise ValueError("invalid analyzer exit code")
        model = parse_observation(response["model"])
        diagnostics = _diagnostics(model, runtime_diagnostic(source_root, model.python_version))
        if code == 2 and not diagnostics:
            diagnostics = (
                Diagnostic(
                    "parse_error",
                    "analyzer response",
                    "Analyzer exit 2 has no reported coverage cause.",
                    "Repair the analyzer response.",
                ),
            )
        return ObservationResult(model, model.coverage, diagnostics)
    except subprocess.TimeoutExpired:
        return _failure(
            "timeout",
            "bundled Python analyzer",
            "The analyzer did not complete within 60 seconds.",
            "Resolve the analyzer timeout and retry.",
        )
    except OSError as error:
        return _failure(
            "missing_tool",
            sys.executable,
            f"The analyzer could not be executed: {error}",
            "Restore the Codekeel installation and Python executable.",
        )
    except (ValueError, TypeError, KeyError) as error:
        return _failure(
            "parse_error",
            "analyzer response",
            f"The observation could not be decoded: {error}",
            "Repair the analyzer output to match the IR schema.",
        )
