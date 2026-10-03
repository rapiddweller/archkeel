# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #165: boundary finding IDs distinguish only distinct semantic findings."""

from __future__ import annotations

from archkeel.check.evaluation.rules import _boundary_type_violation_records, _Position
from archkeel.ir.model import BoundaryTypesRule, stable_id

_RULE = BoundaryTypesRule(
    "APP-TYPES",
    "boundary_types",
    "sample.app",
    "Keep the boundary typed.",
    ("docs/architecture/sample.md",),
    "architect",
)
_ITEM = {"id": "SYMBOL-ID", "evidence_ids": ["EVIDENCE-ID"]}


def _records(verdict: _Position):
    return _boundary_type_violation_records(
        _RULE,
        _ITEM,
        "sample.app",
        "sample.app.api.run",
        "return",
        "dict | object",
        verdict,
    )


def test_one_top_level_finding_keeps_its_existing_id() -> None:
    [record] = _records(_Position(violation="instead of a typed model"))

    assert record["id"] == stable_id("VIO", _RULE.id, _ITEM["id"], "return")


def test_nested_finding_keeps_its_existing_id() -> None:
    [record] = _records(
        _Position(
            violation="instead of a typed model",
            path=("payload",),
            nested_annotation="dict",
        )
    )

    assert record["id"] == stable_id(
        "VIO", _RULE.id, _ITEM["id"], "return", "payload", "dict", "instead of a typed model"
    )


def test_distinct_empty_path_findings_are_unique_deduplicated_and_order_independent() -> None:
    duplicate = ("instead of a typed model", (), "dict", 0)
    other = ("instead of a typed model", (), "object", 0)
    first = _records(_Position(violation=duplicate[0], violations=(duplicate, other, duplicate)))
    reversed_order = _records(
        _Position(violation=duplicate[0], violations=(other, duplicate, duplicate))
    )

    assert len(first) == 2
    first_ids = {record["id"] for record in first}
    assert len(first_ids) == 2
    assert [record["id"] for record in first] == [record["id"] for record in reversed_order]
    assert first_ids == {
        stable_id("VIO", _RULE.id, _ITEM["id"], "return", nested, duplicate[0])
        for nested in ("dict", "object")
    }


def test_identical_type_at_different_container_depths_keeps_distinct_findings() -> None:
    outer = ("instead of a typed model", (), "dict[str, str]", 0)
    inner = ("instead of a typed model", (), "dict[str, str]", 1)

    records = _records(_Position(violation=outer[0], violations=(outer, inner)))

    assert len({record["id"] for record in records}) == 2
    assert {record["data"].get("container_depth", 0) for record in records} == {0, 1}


def test_single_finding_inside_a_container_keeps_its_depth_free_id() -> None:
    [record] = _records(
        _Position(
            violation="holding Extra which the app does not declare",
            violations=(("holding Extra which the app does not declare", (), "Extra", 1),),
        )
    )

    assert record["id"] == stable_id("VIO", _RULE.id, _ITEM["id"], "return")
    assert record["data"]["container_depth"] == 1


def test_single_nested_finding_inside_a_container_keeps_its_depth_free_id() -> None:
    [record] = _records(
        _Position(
            violation="instead of a typed model",
            violations=(("instead of a typed model", ("payload",), "dict", 1),),
        )
    )

    assert record["id"] == stable_id(
        "VIO", _RULE.id, _ITEM["id"], "return", "payload", "dict", "instead of a typed model"
    )
