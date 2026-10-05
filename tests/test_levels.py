# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-34: a declared inside is derived from the same observation as the level above it."""

from typing import Any

from test_delta import _model

from archkeel.ir.codec import parse_observation
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import Observation


def test_the_inside_of_check_carries_its_sub_components_and_their_edges(
    self_observation: Observation,
) -> None:
    levels = {level.parent: level for level in inside_levels(self_observation)}
    assert sorted(levels) == [
        "analyzer",
        "analyzer:dart",
        "analyzer:python",
        "check",
        "ir",
        "render",
    ]
    level = levels["check"]
    assert [(item.label, len(item.modules)) for item in level.components] == [
        ("declarations", 1),
        ("evaluation", 10),
        ("inputs", 7),
        ("observation", 2),
        ("regression", 3),
        ("workflows", 13),
    ]
    assert [(edge.source, edge.target, edge.import_sites) for edge in level.edges] == [
        ("declarations", "evaluation", 1),
        ("observation", "declarations", 5),
        ("observation", "evaluation", 2),
        ("observation", "inputs", 3),
        ("regression", "inputs", 2),
        ("workflows", "declarations", 1),
        ("workflows", "evaluation", 2),
        ("workflows", "inputs", 32),
        ("workflows", "regression", 16),
    ]


def test_a_module_no_sub_component_owns_is_carried_not_dropped(
    self_observation: Observation,
) -> None:
    """Every observed check module stays owned by one declared sub-component."""
    level = next(item for item in inside_levels(self_observation) if item.parent == "check")
    assert level.unassigned == ()
    modules_by_component = {item.label: item.modules for item in level.components}
    assert "archkeel.check" in modules_by_component["inputs"]
    assert sum("archkeel.check" in modules for modules in modules_by_component.values()) == 1


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
