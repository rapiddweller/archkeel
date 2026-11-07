# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recognize the test sources that an Explore scan leaves out."""

from archkeel.ir.facts import Language
from archkeel.ir.profiles import is_test_source


def is_test_path(rel: str, resolved: str | None) -> bool:
    """Judge the path as written and as resolved, so a link cannot hide a test source."""
    return is_test_source(rel, Language.TYPESCRIPT) or (
        resolved is not None and is_test_source(resolved, Language.TYPESCRIPT)
    )
