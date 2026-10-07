# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the actual collector runtime with its declared requirement."""

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from archkeel.ir.model import Diagnostic, RuntimeInfo


def runtime_diagnostic(runtime: RuntimeInfo) -> Diagnostic | None:
    label = "requires-python" if runtime.name == "python" else "required-runtime"
    metadata = "pyproject.toml" if runtime.name == "python" else "runtime metadata"
    subject = f"{runtime.name} {runtime.version}; {label} {runtime.required or 'unavailable'}"
    remedy = f"Run the collector with a {runtime.name} matching its declared requirement."
    if runtime.name == "python" and runtime.requirement_state == "metadata_missing":
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} is missing",
            "The supported Python range is not declared.",
            "Add [project].requires-python to pyproject.toml with the repository's "
            "supported range.",
        )
    if runtime.name == "python" and runtime.requirement_state == "metadata_invalid":
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} is invalid",
            "The supported Python range cannot be read.",
            "Repair pyproject.toml as valid TOML and declare [project].requires-python.",
        )
    if runtime.name == "python" and (
        runtime.requirement_state == "requirement_missing"
        or runtime.required is None
        and runtime.requirement_state == "declared"
    ):
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} has no [project].requires-python",
            "The supported Python range is not declared.",
            "Add [project].requires-python to pyproject.toml with the repository's "
            "supported range.",
        )
    if runtime.name == "python" and runtime.requirement_state == "requirement_invalid":
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} has an invalid [project].requires-python",
            "The supported Python range is malformed.",
            "Set [project].requires-python in pyproject.toml to a non-empty PEP 440 range.",
        )
    try:
        if runtime.required is None:
            raise ValueError("runtime requirement is missing")
        alternatives = runtime.required.split("||")
        if any(not value.strip() for value in alternatives):
            raise ValueError("runtime requirement has an empty alternative")
        ranges = tuple(SpecifierSet(value.strip()) for value in alternatives)
        actual = Version(runtime.version)
        if any(required.contains(actual) for required in ranges):
            return None
        lower = min(
            (
                Version(item.version)
                for required in ranges
                for item in required
                if item.operator in {">=", "~="}
            ),
            default=None,
        )
        if runtime.name == "python" and lower is not None:
            remedy = (
                "Run Archkeel with a matching Python, for example: "
                f"uvx --python {lower.major}.{lower.minor} archkeel <command>"
            )
        comparison = "<" if lower is not None and actual < lower else "does not satisfy"
        subject = f"{runtime.name} {runtime.version} {comparison} {label} {runtime.required}"
    except ValueError as error:
        subject += f" ({error})"
        remedy = (
            "Set [project].requires-python in pyproject.toml to a valid PEP 440 range."
            if runtime.name == "python"
            else "Correct the declared runtime requirement."
        )
    return Diagnostic(
        "runtime_mismatch",
        subject,
        "AST may differ from target runtime; parse errors may be parser limitations, "
        "not source defects",
        remedy,
    )
