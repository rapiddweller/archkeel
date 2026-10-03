# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the actual collector runtime with its declared requirement."""

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from archkeel.ir.model import Diagnostic, RuntimeInfo


def runtime_diagnostic(runtime: RuntimeInfo) -> Diagnostic | None:
    label = "requires-python" if runtime.name == "python" else "required-runtime"
    subject = f"{runtime.name} {runtime.version}; {label} {runtime.required or 'unavailable'}"
    remedy = f"Run the collector with a {runtime.name} matching its declared requirement."
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
    return Diagnostic(
        "runtime_mismatch",
        subject,
        "AST may differ from target runtime; parse errors may be parser limitations, "
        "not source defects",
        remedy,
    )
