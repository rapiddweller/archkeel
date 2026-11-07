# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check that the files a collector selected stay inside the scope of the request."""

from pathlib import PurePosixPath

from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import ProtocolError
from archkeel.ir.profiles import is_test_source
from archkeel.ir.protocol import CollectionRequest


def check_selected_files(facts: SourceFacts, request: CollectionRequest) -> None:
    """Raise when a selected file leaves the roots or is a test source that the scope excludes."""
    roots = tuple(PurePosixPath(root) for root in request.scope.roots)
    selected = facts.coverage.selected_files
    if any(
        not any(PurePosixPath(path).is_relative_to(root) for root in roots) for path in selected
    ):
        raise ProtocolError("collector selected files escape requested scope")
    if request.scope.exclude_test_sources and any(
        is_test_source(path, request.resolver.language) for path in selected
    ):
        raise ProtocolError("collector selected a test source excluded by Explore scope")
