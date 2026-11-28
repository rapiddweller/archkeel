# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1537: a `forbidden_construct` rule on Python decides per module, through the release core.

The survey reads each construct of the vocabulary. A site is a FAIL. A module with no form that can
hide a site proves the absence, so the rule is PASS. A module with such a form (`f = hasattr`,
`import builtins`, `eval(..)`) holds only the rules that judge that module: not a rule of another
source, and not a module that the rule exempts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import rows
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned

PAGE = "src/app/client/page.py"

# For each construct: a site, a module with no form that can hide it, and forms that can hide it.
TABLE: dict[str, tuple[str, list[str]]] = {
    "hasattr": (
        "value = hasattr(item, 'name')\n",
        [
            "f = hasattr\n",
            "import builtins\n",
            "value = builtins.hasattr(item, 'name')\n",
            "value = eval('hasattr(item, 1)')\n",
            "value = ns['__builtins__']\n",
            "hasattr = other\nvalue = hasattr(item, 'name')\n",
        ],
    ),
    "setattr": (
        "setattr(item, 'name', 1)\n",
        [
            "f = setattr\n",
            "from builtins import setattr\n",
            "value = vars(__builtins__)['setattr']\n",
            "value = getattr(mod, 'setattr')\n",
        ],
    ),
    "delattr": (
        "delattr(item, 'name')\n",
        ["f = delattr\n", "value = globals()['delattr']\n", "value = o.delattr\n"],
    ),
    "eval": (
        "value = eval(text)\n",
        ["f = eval\n", "exec('value = eval(x)')\n", "value = o.eval(x)\n", "g = compile\n"],
    ),
    "exec": (
        "exec(text)\n",
        ["f = exec\n", "value = eval('exec(x)')\n", "o.exec(x)\n", "value = fn.__globals__\n"],
    ),
    "cast": (
        "from typing import cast\nvalue = cast(int, item)\n",
        [
            "from typing import cast as c\nf = c\n",
            "import typing\nf = typing.cast\n",
            "import typing\nf = typing\n",
            "from typing import *\n",
            "value = mod.cast(int, item)\n",
            "def f():\n    from typing import cast as k\n    return k(int, 1)\n",
        ],
    ),
    "dynamic_import": (
        "import importlib\nvalue = importlib.import_module(name)\n",
        [
            "import importlib\nf = importlib.import_module\n",
            "from importlib import import_module as m\nf = m\n",
            "f = __import__\n",
            "from importlib import *\n",
            "value = mod.import_module('x')\n",
        ],
    ),
    "dunder_dict": (
        "value = item.__dict__\n",
        ["value = getattr(item, '__dict__')\n", "value = table['__dict__']\n"],
    ),
}
CLEAN = [
    "value = 1\n",
    # A name in a table, a comparison and a mode are data: no lookup reads them.
    "NAMES = {'eval', 'hasattr', 'exec'}\nvalue = item in NAMES\n",
    "value = node.value == 'getattr'\n",
    "import ast\nvalue = ast.parse(text, mode='eval')\n",
    "# the type of the value is a note\nvalue = 1\n",
]


def _rule(rule_id: str, construct: str, **fields: Any) -> dict[str, Any]:
    return {**CONSTRUCT, "id": rule_id, "constructs": [construct], **fields}


def _row(binary: Path, root: Path, source: str, rule: dict[str, Any]) -> tuple[str, str]:
    result = scanned(binary, root, Plant({PAGE: source}, [rule], [], {}, {}))
    return rows(result)[rule["id"]], result["frame"]["explained"].get(rule["id"], "")


@pytest.mark.parametrize("construct", sorted(TABLE))
def test_a_site_is_a_fail_and_a_module_without_a_hiding_form_proves_the_absence(
    release_core: Path, tmp_path: Path, construct: str
) -> None:
    site, _ = TABLE[construct]
    rule = _rule("NO-CONSTRUCT", construct)
    assert _row(release_core, tmp_path / "site", site, rule)[0] == "FAIL"
    for number, clean in enumerate(CLEAN):
        row, why = _row(release_core, tmp_path / f"clean{number}", clean, rule)
        assert row == "PASS", (construct, clean, why)


@pytest.mark.parametrize("construct", sorted(TABLE))
def test_each_form_that_can_hide_a_site_leaves_the_rule_unknown_and_names_the_module(
    release_core: Path, tmp_path: Path, construct: str
) -> None:
    _, hiding = TABLE[construct]
    rule = _rule("NO-CONSTRUCT", construct)
    for number, source in enumerate(hiding):
        row, why = _row(release_core, tmp_path / f"hide{number}", source, rule)
        # A form that is also a site of the construct is a FAIL; no form is ever a PASS.
        assert row in {"UNKNOWN", "FAIL"}, (construct, source, why)
        if row == "UNKNOWN":
            assert "app.client.page" in why or "incomplete scope" in why, (source, why)


def test_a_hiding_form_holds_only_the_rule_that_judges_its_module(
    release_core: Path, tmp_path: Path
) -> None:
    source = "f = hasattr\n"
    here = _rule("NO-HASATTR-HERE", "hasattr", source="app.client")
    elsewhere = _rule("NO-HASATTR-ELSEWHERE", "hasattr", source="app.service")
    exempt = _rule("NO-HASATTR-EXEMPT", "hasattr", allowed_sources=["app.client"])
    exact = _rule("NO-HASATTR-EXACT", "hasattr", exact_sources=["app.client.page"])
    other = _rule("NO-GETATTR-HERE", "getattr", source="app.client")
    plant = Plant({PAGE: source}, [here, elsewhere, exempt, exact, other], [], {}, {})
    found = rows(scanned(release_core, tmp_path, plant))
    assert found["NO-HASATTR-HERE"] == "UNKNOWN"
    assert found["NO-HASATTR-ELSEWHERE"] == "PASS"
    assert found["NO-HASATTR-EXEMPT"] == "PASS"
    assert found["NO-HASATTR-EXACT"] == "PASS"
    # `f = hasattr` hides no `getattr` site: a rule on another construct is not held.
    assert found["NO-GETATTR-HERE"] == "PASS"


def test_a_site_beside_a_hiding_form_stays_a_fail(release_core: Path, tmp_path: Path) -> None:
    rule = _rule("NO-EVAL", "eval")
    assert _row(release_core, tmp_path, "value = eval(text)\ng = compile\n", rule)[0] == "FAIL"
