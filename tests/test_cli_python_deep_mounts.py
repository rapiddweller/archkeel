# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-514, amended: an import that crosses several mount boundaries counts when each boundary
publishes it, as in release 4.0.1 (`_import_published_through_ancestors`).

Consumer: a team with a contract tree of three levels. A public entry of the innermost contract
that a module outside the whole tree imports is used. The core must not say `usage_unknown` for
it, and must say it again when one boundary stops publishing the entry.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from corpus_support import commit_tree as commit
from python_deep_mount_plant import Variant, build, variants
from test_cli_native_python_imports import verdict

CASES = variants()


@pytest.mark.parametrize("variant", CASES, ids=[variant.name for variant in CASES])
def test_a_deep_mount_counts_the_import_that_every_boundary_publishes(
    release_core: Path, tmp_path: Path, variant: Variant
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    build(root, variant)
    commit(root)
    result = verdict(release_core, root)
    found = {
        match.group(1)
        for row in result["gaps"]
        if (
            match := re.match(
                r"hygiene:interface\.usage_unknown:.*?(/components/\S+?):", row["subject"]
            )
        )
    }
    if variant.four is None:
        assert found == set(), found
        assert (result["status"], result["exit_code"]) == ("PASS", 0), result["frame"]["explained"]
    else:
        # 4.0.1 gives `interface.unused` at the pointer of the entry that the broken boundary
        # leaves unreached; the core gives `usage_unknown` there and never clears it.
        assert any(found_at.endswith(variant.four[2]) for found_at in found), (found, variant.four)
        assert result["status"] != "PASS"
