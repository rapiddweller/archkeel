# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-34: a declared inside is derived from the same observation as the level above it."""

import json
from pathlib import Path
from typing import Any

from test_delta import _model

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.levels import inside_levels

ROOT = Path(__file__).resolve().parents[1]


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def test_the_inside_of_check_carries_its_sub_components_and_their_edges() -> None:
    levels = inside_levels(_self_observation())
    assert [level.parent for level in levels] == ["check"]
    level = levels[0]
    assert [(item.label, len(item.modules)) for item in level.components] == [
        ("entry", 4),
        ("foundation", 5),
        ("policy", 3),
    ]
    assert [(edge.source, edge.target, edge.import_sites) for edge in level.edges] == [
        ("entry", "foundation", 21),
        ("entry", "policy", 6),
        ("policy", "foundation", 2),
    ]


def test_a_module_no_sub_component_owns_is_carried_not_dropped() -> None:
    """The package __init__ belongs to no layer; a module that vanished between two levels
    would be the one thing this tool exists to prevent."""
    level = inside_levels(_self_observation())[0]
    assert level.unassigned == ("archkeel.check",)
    owned = {name for item in level.components for name in item.modules}
    assert "archkeel.check" not in owned


def _declaration(identifier: str, kind: str, title: str, subjects: list[str], **data: Any):
    return {
        "id": identifier,
        "evidence_class": "DECLARED_RULE",
        "area": "components",
        "kind": kind,
        "title": title,
        "subjects": subjects,
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": data,
    }


def _two_sub_components_model() -> dict[str, Any]:
    """An inside of two sub-components with one module import running between them."""
    return _model(
        git_head="a" * 40,
        declarations=[
            _declaration("COMP-CORE", "component_responsibility", "core", ["sample.core"]),
            _declaration(
                "core:COMP-A",
                "inside_component_responsibility",
                "a",
                ["sample.core.a"],
                parent_id="core",
                requires=[],
            ),
            _declaration(
                "core:COMP-B",
                "inside_component_responsibility",
                "b",
                ["sample.core.b"],
                parent_id="core",
                requires=[],
            ),
        ],
        modules=[
            _declaration("MOD-A", "module", "a", [], qualified_name="sample.core.a"),
            _declaration("MOD-B", "module", "b", [], qualified_name="sample.core.b"),
        ],
        dependency_edges=[
            _declaration(
                "EDGE-A-B",
                "dependency_edge",
                "a to b",
                [],
                level="module",
                source="sample.core.a",
                target="sample.core.b",
                count=3,
            )
        ],
    )


def test_module_imports_between_two_sub_components_become_one_crossing() -> None:
    """The derivation reports structure only; whether the crossing is allowed is a violation
    record the analyzer writes, so no verdict is restated here."""
    level = inside_levels(parse_observation(_two_sub_components_model()))[0]
    assert [(edge.source, edge.target, edge.import_sites) for edge in level.edges] == [
        ("a", "b", 3)
    ]


def test_an_observation_without_a_declared_inside_has_no_level() -> None:
    assert inside_levels(parse_observation(_model(git_head="a" * 40))) == ()
