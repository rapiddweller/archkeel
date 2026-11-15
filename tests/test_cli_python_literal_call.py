# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-520: a Python import call never gives a PASS that release 4.0.1 refuses.

Consumer: a CI job that reads the UML target row of a Python project whose `one.py` declares the
edge `one -> t` and reaches `t` by an import call. 4.0.1 reads import statements only, so its row
is FAIL for every form. The core gives FAIL for the two proven literal calls (the call is a real
edge, but not the statement that the target declares) and UNKNOWN for each form that it does not
prove. It never gives PASS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from python_literal_forms import FORMS, Form
from test_cli_core_only_scan import command
from test_cli_core_uml_review import PLANTS, ROW, project


def plant(form: Form) -> tuple:
    base = PLANTS["r1-python-importlib-declared"][0]
    return (base[0], {**base[1], "app/a/one.py": form.source}, base[2], base[3])


@pytest.mark.parametrize("form", FORMS, ids=[form.name for form in FORMS])
def test_a_call_gives_the_row_of_4_0_1_or_unknown_and_never_a_pass(
    release_core: Path, tmp_path: Path, form: Form
) -> None:
    done = command(release_core, project(tmp_path, plant(form)), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    frame = result["frame"]
    assert frame["rules"][ROW] == ["uml_target", form.core], (form.name, frame.get("explained"))
    assert form.four == "FAIL" and frame["rules"][ROW][1] != "PASS"
    if form.proven:
        assert "only a call-form import" in json.dumps(frame["details"][ROW])
