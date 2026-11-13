# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep measurement levels nominal without confusing rule or topology levels."""

import ast
import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.ir import structure

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/structure-level-types.md"
IR_GUARD = "IR-STRUCTURE-LEVEL-CONTROL"
RENDER_GUARD = "RENDER-STRUCTURE-LEVEL-CONTROL"


def _levels():
    level = structure.StructureLevel
    assert isinstance(level, type) and issubclass(level, Enum), "own nominal measurement levels"
    assert {item.value for item in level} == {"component", "package"}
    return level


@pytest.mark.parametrize("raw", ["component", "package"])
def test_legacy_metric_inputs_normalize_to_the_existing_owned_level_and_keep_json(raw):
    level = _levels()
    metric = structure.StructureMetric("app", raw, 2, 1, 0, 0, 3, 1)
    assert metric.level is level(raw)
    assert get_type_hints(structure.StructureMetric)["level"] is level
    assert get_type_hints(structure.scope_metrics)["level"] is level
    assert json.loads(json.dumps(asdict(metric))) == {
        "scope": "app",
        "level": raw,
        "modules": 2,
        "inner_edges": 1,
        "fan_in": 0,
        "fan_out": 0,
        "calls": 3,
        "unresolved": 1,
    }


@pytest.mark.parametrize("raw", ["module", "future", "", None, 3])
def test_metric_ingress_rejects_values_outside_its_own_level_domain(raw):
    with pytest.raises((TypeError, ValueError)):
        structure.StructureMetric("app", raw, 2, 1, 0, 0, None, None)


def _repository(tmp_path, *, mutation=None, relocate=False):
    target = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    target.pop("$schema", None)
    render = json.loads((ROOT / "docs/architecture/contracts/render.json").read_text())
    entities = [
        item
        for item in target["declarations"]["uml"]["entities"]
        if item["id"].startswith("IR-STRUCTURE-") or item["id"] == "IR-COMPARISON-structure"
    ]
    assert entities, "the consumed structure port needs independently authored intent"
    target["components"] = [
        {
            "id": "TARGET-ARCHITECTURE",
            "label": "architecture",
            "role": "component",
            "packages": ["archkeel.ir.structure"],
            "responsibilities": ["Own pure structure measurements and their closed level."],
            "forbidden_responsibilities": [],
            "provenance": [DOC],
        },
        {
            "id": "renderer",
            "label": "renderer",
            "role": "component",
            "packages": ["archkeel.render.html"],
            "responsibilities": ["Present the measured scope levels without reinterpreting them."],
            "forbidden_responsibilities": [],
            "provenance": [DOC],
        },
    ]
    target["rules"] = [
        item
        for item in [*target["rules"], *render["rules"]]
        if item["id"] in {IR_GUARD, RENDER_GUARD}
    ]
    assert {item["id"] for item in target["rules"]} == {IR_GUARD, RENDER_GUARD}
    root_intent = json.loads((ROOT / "architecture-contract.json").read_text())
    target["rules"].append(
        next(rule for rule in root_intent["rules"] if rule["id"] == "TYPES-ENUM-IN-MODEL")
    )
    target["declarations"]["uml"]["entities"] = entities
    target["declarations"]["uml"]["relationships"] = []
    target["declarations"]["uml"]["scopes"] = []
    target["declarations"]["modules"] = []
    owner = (ROOT / "src/archkeel/ir/structure.py").read_text()
    renderer = (ROOT / "src/archkeel/render/html.py").read_text()
    tree = ast.parse(renderer)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_structure_overview_body"
    )
    renderer = (
        "from archkeel.ir.structure import StructureLevel as _StructureLevel\n"
        + ast.get_source_segment(renderer, function)
        + "\n"
    )
    if relocate:
        declaration = next(
            node
            for node in ast.parse(owner).body
            if isinstance(node, ast.ClassDef) and node.name == "StructureLevel"
        )
        enum_source = ast.get_source_segment(owner, declaration)
        assert enum_source is not None and owner.count(enum_source) == 1
        owner = owner.replace(enum_source, "")
        renderer = "from enum import StrEnum\n" + enum_source + "\n" + renderer
    if mutation is not None:
        path, old, new = mutation
        source = owner if path == "owner" else renderer
        assert source.count(old) == 1, "mutate exactly one actual consumed port or control"
        source = source.replace(old, new)
        if path == "owner":
            owner = source
        else:
            renderer = source
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/render/__init__.py": "",
        "archkeel/ir/structure.py": owner,
        "archkeel/render/html.py": renderer,
        "contract.json": json.dumps(target),
        DOC: (ROOT / DOC).read_text(),
        "docs/architecture/comparison-support-types.md": (
            ROOT / "docs/architecture/comparison-support-types.md"
        ).read_text(),
        "docs/architecture/language-adapter-target.md": "Pure governance models.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)
