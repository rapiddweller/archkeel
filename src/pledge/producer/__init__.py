# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the existing Python producer in its own trusted checkout."""

import os
import subprocess
import sys
from pathlib import Path

from pledge.ir.codec import canonical_json_bytes, decode_json, parse_observation
from pledge.ir.model import Diagnostic, DiagnosticKind, Observation, ObservationResult

from .runtime import runtime_diagnostic

_BRIDGE = """
import json, platform, sys
from pathlib import Path
from script.architecture.report import analyze_snapshot
request = json.load(sys.stdin)
model, code = analyze_snapshot(
    Path(request['source_root']), git_head=request['git_head'], dirty=request['dirty'],
    contract_root=Path(request['contract_root']), contract_path=Path(request['contract']),
    roots=tuple(request['roots']), namespace=request['namespace'], analyzer_root=Path.cwd(),
)
model['python_version'] = platform.python_version()
json.dump({'model': model, 'exit_code': code}, sys.stdout, sort_keys=True)
"""


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
                "Use the pinned producer that reports rule applicability coverage.",
            )
        )
    if model.coverage.status == "FAIL" and not diagnostics:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage",
                "The producer reported incomplete coverage without a cause.",
                "Inspect the producer coverage and repair its inputs.",
            )
        )
    return tuple(diagnostics)


def observe(
    source_root: Path,
    *,
    producer_root: Path,
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
                    "Correct scan.roots in pledge.toml.",
                )
            for path in directory.rglob("*.py"):
                if not path.resolve().is_relative_to(source_root):
                    return _failure(
                        "parse_error",
                        str(path),
                        "Source path escapes repository.",
                        "Remove the source symlink or correct the scan scope.",
                    )
        if not (producer_root / "script/architecture/report.py").is_file():
            return _failure(
                "missing_tool",
                str(producer_root),
                "The Python producer is unavailable.",
                "Supply the trusted producer checkout with --producer-root.",
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
            [sys.executable, "-B", "-c", _BRIDGE],
            cwd=producer_root.resolve(),
            input=canonical_json_bytes(request).decode(),
            text=True,
            capture_output=True,
            timeout=60,
            env={
                **os.environ,
                "PYTHONPATH": str(producer_root.resolve()),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        if result.returncode:
            return _failure(
                "parse_error",
                str(producer_root),
                f"Producer execution failed: {result.stderr.strip()}",
                "Repair the producer failure and run report again.",
            )
        response = decode_json(result.stdout)
        if not isinstance(response, dict) or set(response) != {"model", "exit_code"}:
            raise ValueError("invalid producer response envelope")
        code = response["exit_code"]
        if type(code) is not int or code not in (0, 2):
            raise ValueError("invalid producer exit code")
        model = parse_observation(response["model"])
        diagnostics = _diagnostics(model, runtime_diagnostic(source_root, model.python_version))
        if code == 2 and not diagnostics:
            diagnostics = (
                Diagnostic(
                    "parse_error",
                    "producer response",
                    "Producer exit 2 has no reported coverage cause.",
                    "Repair the producer response.",
                ),
            )
        return ObservationResult(model, model.coverage, diagnostics)
    except subprocess.TimeoutExpired:
        return _failure(
            "timeout",
            str(producer_root),
            "The producer did not complete within 60 seconds.",
            "Resolve the producer timeout and retry.",
        )
    except OSError as error:
        return _failure(
            "missing_tool",
            str(producer_root),
            f"The producer could not be executed: {error}",
            "Restore the producer checkout and Python executable.",
        )
    except (ValueError, TypeError, KeyError) as error:
        return _failure(
            "parse_error",
            "producer response",
            f"The observation could not be decoded: {error}",
            "Repair the producer output to match the IR schema.",
        )
