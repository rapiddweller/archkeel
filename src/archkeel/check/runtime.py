# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the actual collector runtime with its declared requirement."""

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from archkeel.ir.model import Diagnostic, RuntimeInfo

_PYTHON_REQUIREMENT_REMEDY = (
    "Use a valid PEP 440 range in [project].requires-python or a supported positive-major "
    "Poetry caret constraint."
)


def runtime_diagnostic(runtime: RuntimeInfo) -> Diagnostic | None:
    metadata = _python_metadata_diagnostic(runtime)
    if metadata is not None:
        return metadata
    return _declared_runtime_diagnostic(runtime)


def _python_metadata_diagnostic(runtime: RuntimeInfo) -> Diagnostic | None:
    if runtime.name != "python":
        return None
    metadata = "pyproject.toml"
    if runtime.requirement_state == "metadata_missing":
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} is missing",
            "The supported Python range is not declared.",
            "Add [project].requires-python to pyproject.toml with the repository's "
            "supported range.",
        )
    if runtime.requirement_state == "metadata_invalid":
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} is invalid",
            "The supported Python range cannot be read.",
            "Repair pyproject.toml as valid TOML and declare [project].requires-python.",
        )
    if runtime.requirement_state == "requirement_missing" or (
        runtime.requirement_state == "declared" and runtime.required is None
    ):
        return Diagnostic(
            "runtime_mismatch",
            f"{metadata} has no [project].requires-python",
            "The supported Python range is not declared.",
            "Add [project].requires-python to pyproject.toml with the repository's "
            "supported range.",
        )
    if runtime.requirement_state == "requirement_invalid":
        return Diagnostic(
            "runtime_mismatch",
            "pyproject.toml Python requirement is invalid or unsupported",
            "The supported Python range cannot be validated.",
            _PYTHON_REQUIREMENT_REMEDY,
        )
    return None


def _declared_runtime_diagnostic(runtime: RuntimeInfo) -> Diagnostic | None:
    label = "requires-python" if runtime.name == "python" else "required-runtime"
    subject = f"{runtime.name} {runtime.version}; {label} {runtime.required or 'unavailable'}"
    remedy = f"Run the collector with a {runtime.name} matching its declared requirement."
    try:
        ranges = _parse_ranges(runtime.required, allow_alternatives=runtime.name != "python")
    except ValueError as error:
        if runtime.name == "python":
            subject = "pyproject.toml Python requirement is invalid or unsupported"
        else:
            subject += f" ({error})"
        remedy = (
            _PYTHON_REQUIREMENT_REMEDY
            if runtime.name == "python"
            else "Correct the declared runtime requirement."
        )
    else:
        try:
            actual = Version(runtime.version)
        except InvalidVersion as error:
            subject += f" ({error})"
            remedy = "Run the collector with a valid runtime version."
        else:
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
    return Diagnostic(
        "runtime_mismatch",
        subject,
        "AST may differ from target runtime; parse errors may be parser limitations, "
        "not source defects",
        remedy,
    )


def _parse_ranges(required: str | None, *, allow_alternatives: bool) -> tuple[SpecifierSet, ...]:
    if required is None:
        raise ValueError("runtime requirement is missing")
    alternatives = required.split("||") if allow_alternatives else [required]
    if any(not value.strip() for value in alternatives):
        raise ValueError("runtime requirement has an empty alternative")
    return tuple(SpecifierSet(value.strip()) for value in alternatives)


def has_invalid_python_requirement(runtime: RuntimeInfo) -> bool:
    """Classify malformed declared Python metadata at the Core boundary."""
    if runtime.name != "python" or runtime.required is None:
        return False
    try:
        _parse_ranges(runtime.required, allow_alternatives=False)
    except ValueError:
        return True
    return False
