# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The languages that Archkeel reads and the profile name that each collector reports."""

from enum import StrEnum

from .diagnostics import Diagnostic, DiagnosticKind


class Language(StrEnum):
    PYTHON = "python"
    DART = "dart"
    TYPESCRIPT = "typescript"
    RUST = "rust"


class SourceProfile(StrEnum):
    PYTHON = "archkeel-python-analyzer"
    DART = "archkeel-dart-analyzer"
    TYPESCRIPT = "archkeel-typescript-imports"
    RUST = "archkeel-rust-imports"


class UnsupportedProjectError(Exception):
    """The project needs a collector that this version does not support (AD-422)."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.unknown_claim)


def require_supported_project(language: Language | SourceProfile) -> None:
    if language in {Language.PYTHON, SourceProfile.PYTHON, Language.DART, SourceProfile.DART}:
        name = "Python" if language in {Language.PYTHON, SourceProfile.PYTHON} else "Dart"
        raise UnsupportedProjectError(
            Diagnostic(
                DiagnosticKind.MISSING_TOOL,
                str(language),
                f"{name} projects are not supported in this version; use archkeel 4.0.1",
                "Use archkeel 4.0.1 for Python and Dart projects.",
            )
        )
