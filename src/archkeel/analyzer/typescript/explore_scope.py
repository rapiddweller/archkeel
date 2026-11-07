# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recognize the test sources that an Explore scan leaves out."""

from collections.abc import Sequence

from archkeel.ir.facts import Language
from archkeel.ir.profiles import is_test_source
from archkeel.ir.protocol import CollectionRequest

NO_PRODUCTION_SOURCE = "No production source files in scope after the test exclusion"


def is_test_path(rel: str, resolved: str | None) -> bool:
    """Judge the path as written and as resolved, so a link cannot hide a test source."""
    return is_test_source(rel, Language.TYPESCRIPT) or (
        resolved is not None and is_test_source(resolved, Language.TYPESCRIPT)
    )


def emptied_by_exclusion(
    request: CollectionRequest, files: Sequence[str], queue: Sequence[str]
) -> set[str]:
    """Return a problem when the test exclusion removed every file, so the scan is not complete."""
    if request.scope.exclude_test_sources and files and not queue:
        return {NO_PRODUCTION_SOURCE}
    return set()
