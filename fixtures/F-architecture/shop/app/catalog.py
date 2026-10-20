# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Application-owned store option vocabulary and read adapter."""

from __future__ import annotations

from enum import StrEnum


class OptionKey(StrEnum):
    """Named options accepted by an application store read."""

    PAGE_SIZE = "page_size"
    RETIRED = "retired"


def read_option(key: str) -> str:
    """Read one option key through the application-facing adapter."""
    return key
