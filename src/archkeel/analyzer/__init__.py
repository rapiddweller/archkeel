# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the bundled Python analyzer in an isolated process."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    RawJson,
)
from archkeel.ir.codec import canonical_json_bytes as _canonical_json_bytes
from archkeel.ir.codec import decode_json as _decode_json
from archkeel.ir.codec import parse_observation as _parse_observation
from archkeel.ir.model import Diagnostic, DiagnosticKind, Observation, ObservationResult
from archkeel.ir.profiles import PROFILES, Language

from .embedded.contract import ContractError, load_contract
from .runtime import runtime_diagnostic


def _failure(kind: DiagnosticKind, subject: str, claim: str, remedy: str) -> ObservationResult:
    return ObservationResult(None, None, (Diagnostic(kind, subject, claim, remedy),))


def _contract_failure(path: Path) -> ObservationResult | None:
    try:
        load_contract(path)
    except ContractVersionError as error:
        return _failure(
            "parse_error",
            path.name,
            f"Contract schema {error.actual} cannot be validated as {CONTRACT_SCHEMA_VERSION}.",
            "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
        )
    except ContractError as error:
        return _failure(
            "parse_error",
            path.name,
            f"The architecture contract cannot be decoded: {error}",
            "Correct the contract structure and run report again.",
        )
    return None


# AD-97: a contract item the profile cannot decide is refused, never read as PASS.
_RULE_FAILURES: Final[dict[str, tuple[DiagnosticKind, str]]] = {
    "rule-without-subjects": (
        "rule_without_subjects",
        "Correct the rule selectors or scan scope.",
    ),
    "rule-unsupported-by-profile": (
        "rule_unsupported_by_profile",
        "Remove the rule or declaration, or run a profile that supports it.",
    ),
}
_SOURCE_NAME: Final[dict[Language, str]] = {"python": "Python", "dart": "Dart"}
_SOURCE_REMEDY: Final[dict[Language, str]] = {
    "python": "Inspect the reported failure using the declared target runtime; "
    "rerun after resolving its cause.",
    "dart": "Correct the reported directive, URI, part declaration or pubspec name; "
    "rerun after resolving its cause.",
}


def _diagnostics(
    model: Observation, runtime: Diagnostic | None, language: Language
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for failure in model.coverage.failures:
        rule_failure = _RULE_FAILURES.get(failure.kind)
        if rule_failure is None and runtime is not None:
            diagnostics.append(runtime)
            continue
        kind, remedy = rule_failure or ("parse_error", _SOURCE_REMEDY[language])
        diagnostics.append(
            Diagnostic(
                kind,
                ", ".join(failure.rule_ids or failure.subjects) or failure.id,
                f"Scan completeness cannot be established: {failure.title}",
                remedy,
            )
        )
    if runtime is not None and runtime not in diagnostics:
        diagnostics.append(runtime)
    if model.coverage.files_discovered == 0:
        diagnostics.append(
            Diagnostic(
                "scope_empty",
                ", ".join(model.source.scope) or "scan.roots",
                f"The configured scope contains no observable {_SOURCE_NAME[language]} files.",
                f"Set scan.roots to an existing {_SOURCE_NAME[language]} source directory.",
            )
        )
    if model.coverage.rules is None:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                "coverage.rules",
                "Rule applicability coverage is missing.",
                "Reinstall a complete Archkeel distribution.",
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
    language: Language = "python",
) -> ObservationResult:
    source_root = source_root.resolve()
    suffix = PROFILES[language].source_suffix
    try:
        contract_file = contract_root / contract
        if failure := _contract_failure(contract_file):
            return failure
        for root in roots:
            directory = source_root / root
            if not directory.is_dir():
                return _failure(
                    "scope_empty",
                    root,
                    "The scan root does not exist.",
                    "Correct scan.roots in archkeel.toml.",
                )
            for path in directory.rglob(f"*{suffix}"):
                if not path.resolve().is_relative_to(source_root):
                    return _failure(
                        "parse_error",
                        str(path),
                        "Source path escapes repository.",
                        "Remove the source symlink or correct the scan scope.",
                    )
        request: dict[str, RawJson] = {
            "source_root": str(source_root),
            "git_head": git_head,
            "dirty": dirty,
            "contract_root": str(contract_root.resolve()),
            "contract": contract,
            "roots": roots,
            "namespace": namespace,
            "language": language,
        }
        result = subprocess.run(
            [sys.executable, "-B", "-m", "archkeel.analyzer.bridge"],
            cwd=source_root,
            input=_canonical_json_bytes(request).decode(),
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
        response = _decode_json(result.stdout)
        if not isinstance(response, dict) or set(response) != {"model", "exit_code"}:
            raise ValueError("invalid analyzer response envelope")
        code = response["exit_code"]
        if type(code) is not int or code not in (0, 2):
            raise ValueError("invalid analyzer exit code")
        model = _parse_observation(response["model"])
        # The declared Python range says nothing about a Dart package (AD-97).
        runtime = (
            runtime_diagnostic(source_root, model.python_version) if language == "python" else None
        )
        diagnostics = _diagnostics(model, runtime, language)
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
            "Restore the Archkeel installation and Python executable.",
        )
    except (ValueError, TypeError, KeyError) as error:
        return _failure(
            "parse_error",
            "analyzer response",
            f"The observation could not be decoded: {error}",
            "Repair the analyzer output to match the IR schema.",
        )
