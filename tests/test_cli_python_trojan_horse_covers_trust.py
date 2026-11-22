# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1052, AD-1056, AD-1058, `docs/known-limits.md` (a covered module is trusted).

A covered module is trusted not to hand the bound name to an uncovered module. Python 3.12 imports
the secret module in each plant below, and the rule gives PASS under the declared reach. The
differential run of #1968 counts these three as the feature: the project states the trust in
`covers`. The plants pin the limit so that it cannot widen without a failing test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_python_trojan_horse_name import (
    BLOB,
    MODEL,
    PAGE,
    imports_secret,
    pickle_declaration,
    rows,
    run,
)

OTHER = "src/app/service/other.py"
USE = f".loads({BLOB})\n"
CASES = {
    "the covered module re-exports the attribute": (
        {
            MODEL: "import pickle\n",
            OTHER: "import app.service.model as m\nUSE = m.pickle\n",
            PAGE: "import app.service.other as o\no.USE" + USE,
        },
        ["app.service.other"],
    ),
    "covers lists the page itself": (
        {
            MODEL: "import pickle\n",
            PAGE: "import app.service.model as model\nmodel.pickle" + USE,
        },
        ["app.client.page"],
    ),
    "the covered module imports the name under another name": (
        {
            MODEL: "import pickle\n",
            OTHER: "from app.service.model import pickle as USE\n",
            PAGE: "import app.service.other as o\no.USE" + USE,
        },
        ["app.service.other"],
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_covered_module_that_hands_the_name_on_passes_under_the_declared_reach(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    files, covers = CASES[name]
    result = run(tmp_path, dict(files), [pickle_declaration() | {"covers": covers}], release_core)

    assert imports_secret(tmp_path)
    assert rows(result)["CLIENT-NO-SECRET"] == "PASS", result["frame"]
    assert result["frame"]["assumed"]["CLIENT-NO-SECRET"], result["frame"]
