# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The languages that Archkeel reads and the profile name that each collector reports."""

from enum import StrEnum


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


def require_supported_project(language: Language | SourceProfile) -> None:
    if language in {Language.PYTHON, SourceProfile.PYTHON, Language.DART, SourceProfile.DART}:
        name = "Python" if language in {Language.PYTHON, SourceProfile.PYTHON} else "Dart"
        raise UnsupportedProjectError(
            f"{name} projects are not supported in this version; use archkeel 4.0.1"
        )
