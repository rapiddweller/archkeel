# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2067: a topology that repeats an identity is refused, and the refusal names the identity."""

from __future__ import annotations

import pytest

from archkeel.cli.core_json import CoreError
from archkeel.cli.core_topology import LIMITS, frame_topology


def _edge(edge_id: str, count: int) -> dict[str, object]:
    return {
        "id": edge_id,
        "source": "unowned",
        "target": "external",
        "resolution": "external",
        "count": count,
        "evidence": [],
        "evidence_total": 0,
        "rules": [],
    }


def _frame(edges: list[dict[str, object]]) -> dict[str, object]:
    topology = {
        "version": 1,
        "complete": True,
        "truncated": False,
        "gaps": [],
        "budgets": dict(LIMITS),
        "total": {
            "components": 0,
            "modules": 0,
            "edges": 0,
            "component_edges": len(edges),
            "evidence_per_edge": 0,
            "requires": 0,
            "layers": 0,
        },
        "components": [],
        "modules": [],
        "edges": [],
        "component_edges": edges,
        "requires": [],
        "layers": [],
    }
    return {"topology": topology, "scope": "complete"}


def test_a_repeated_component_edge_is_refused_with_its_list_and_id() -> None:
    frame = _frame([_edge("EDGE-1", 2), _edge("EDGE-2", 1), _edge("EDGE-1", 3)])
    with pytest.raises(CoreError, match="repeated identity in component_edges: EDGE-1"):
        frame_topology(frame, {})


def test_distinct_identities_are_read() -> None:
    topology = frame_topology(_frame([_edge("EDGE-1", 2), _edge("EDGE-2", 1)]), {})
    assert topology is not None
    assert [edge.id for edge in topology.component_edges] == ["EDGE-1", "EDGE-2"]
