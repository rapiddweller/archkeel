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
