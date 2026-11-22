# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: a cycle that rests on a declared reach names the declaration and the module edge.

Consumer: a person who reads a FAIL of a cycle rule and must find which declaration of the
contract closes the cycle. The step of the cycle that has no observed import lists the declared
edge: the declaration id, the module of its site and the module that it may load. Python runs the
truth: the declared load is a real import of the evaluated text.
"""

from __future__ import annotations

from pathlib import Path

from test_cli_native_python_imports import command, rows
from test_cli_python_trojan_horse_reach import TROJAN_HORSE, declaration, scanned, truth

MODEL = "src/app/service/model.py"


def test_a_cycle_through_a_declared_load_names_the_declaration_and_the_edge(
    release_core: Path, tmp_path: Path
) -> None:
    result = scanned(
        release_core, tmp_path, {MODEL: TROJAN_HORSE}, [declaration(loads=["app.client.page"])]
    )
    assert rows(result)["CYCLES"] == "FAIL", result
    load = "import app.service.model, sys; print('app.client.page' in sys.modules)"
    assert truth(tmp_path, "__import__('app.client.page')", load) == "True"

    cycles = result["frame"]["explain"]["cycles"]["CYCLES"]["items"]
    declared = [edge for step in cycles[0]["path"] for edge in step.get("declared", [])]
    assert declared == [
        {
            "declaration": "D-EVAL",
            "source": "app.service.model",
            "target": "app.client.page",
        }
    ], cycles
    observed = [step for step in cycles[0]["path"] if not step.get("possible")]
    assert observed and all("declared" not in step for step in observed), cycles

    text = command(release_core, tmp_path, "--text").stdout
    assert "app.service.model -> app.client.page, declared by D-EVAL" in text, text
