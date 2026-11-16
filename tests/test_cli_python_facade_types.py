# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-580: a public entry that a declared signature names is used, as in release 4.0.1.

Consumer: a team whose component publishes a type and a function that takes it. Nobody outside
the component imports the type. The core must not name `interface.usage_unknown` for it. It keeps
the row where the signature is not a proven declared one: a private function, a string, a name
under `TYPE_CHECKING`, a decorated function.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from corpus_support import commit_tree as commit
from python_facade_plant import ITEM, Variant, build, variants
from test_cli_native_python_imports import verdict

CASES = variants()


@pytest.mark.parametrize("variant", CASES, ids=[variant.name for variant in CASES])
def test_a_declared_signature_reaches_the_entry_it_names(
    release_core: Path, tmp_path: Path, variant: Variant
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    build(root, variant)
    commit(root)
    result = verdict(release_core, root)
    found = {
        row["subject"].rsplit(":", 2)[-2:][0] + ":" + row["subject"].rsplit(":", 1)[-1]
        for row in result["gaps"]
        if re.match(r"hygiene:interface\.usage_unknown:", row["subject"])
    }
    if variant.core is None:
        assert found == set(), found
    else:
        assert found == {ITEM}, found
    # The core never clears an entry that 4.0.1 refuses.
    assert variant.core is not None or variant.four is None
