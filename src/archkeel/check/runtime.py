# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the actual parser with the scanned project's declared Python range."""

import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from archkeel.ir.model import Diagnostic


def runtime_diagnostic(root: Path, python_version: str | None) -> Diagnostic | None:
    subject = f"python {python_version or 'unknown'}; requires-python unavailable"
    remedy = "Run Archkeel with a Python matching the target's requires-python."
    try:
        path: Path = root / "pyproject.toml"
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("pyproject.toml escapes the scanned root")
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
        required = project.get("requires-python") if isinstance(project, dict) else None
        if not isinstance(required, str) or not required.strip():
            raise ValueError("requires-python is missing")
        specifiers = SpecifierSet(required)
        subject = f"python {python_version or 'unknown'}; requires-python {required}"
        # Only lower bounds name a concrete runtime; wildcard or exclusive bounds do not.
        lower = max(
            (Version(item.version) for item in specifiers if item.operator in {">=", "~="}),
            default=None,
        )
        if lower is not None:
            remedy = (
                "Run Archkeel with a matching Python, for example: "
                f"uvx --python {lower.major}.{lower.minor} archkeel <command>"
            )
        if python_version is not None:
            actual = Version(python_version)
            if specifiers.contains(actual):
                return None
            comparison = (
                "<"
                if any(
                    item.operator in {">=", ">", "~="} and actual < Version(item.version)
                    for item in specifiers
                )
                else "does not satisfy"
            )
            subject = f"python {python_version} {comparison} requires-python {required}"
    except (OSError, ValueError) as error:
        subject += f" ({error})"
    return Diagnostic(
        "runtime_mismatch",
        subject,
        "AST may differ from target runtime; parse errors may be parser limitations, "
        "not source defects",
        remedy,
    )
