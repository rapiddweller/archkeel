# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shell side of the dual run of slices S2 to S4 (AD-372, AD-374, AD-378): the settings, the
edge comparison and the check of the frame status."""

from __future__ import annotations

import zlib
from typing import Any

import pytest

from tools import dual_run
from tools.dual_run_oracle import Selection


def _edge(identifier: str, count: int, rank: int) -> dict[str, Any]:
    data = {"level": "module", "count": count, "source_rank": rank, "target_rank": rank + 1}
    return {"id": identifier, "rule_ids": [], "kind": "module_dependency", "data": data}


def test_the_full_edge_rows_compare_with_their_ranks_and_name_each_difference() -> None:
    """AD-374: the `dependency_edges` rows of the engine compare field by field with the rows of
    the Python engine, the ranks of slice S3 included."""
    python = [_edge("EDGE-1", 1, 0), _edge("EDGE-2", 2, 3)]
    reply = {"self_test": {"reply": {"files": 3}}}
    equal = {**reply, "sections": {"dependency_edges": python}}
    assert dual_run.edge_differences("c", python, equal) == []
    dropped = {**reply, "sections": {"dependency_edges": python[:1]}}
    assert [d.scope for d in dual_run.edge_differences("c", python, dropped)] == ["edges"]
    # A rank alone is a difference.
    ranked = {**reply, "sections": {"dependency_edges": [python[0], _edge("EDGE-2", 2, 4)]}}
    assert dual_run.edge_differences("c", python, ranked)[0].id == "EDGE-2"
    unranked = {**python[1], "data": {"level": "module", "count": 2}}
    without = {**reply, "sections": {"dependency_edges": [python[0], unranked]}}
    assert dual_run.edge_differences("c", python, without)[0].id == "EDGE-2"
    # The old field `edges` is not read: an engine without the section differs, unless its
    # refusal of the reply is already named.
    old = {**reply, "edges": python}
    assert dual_run.edge_differences("c", python, old)[0].detail.endswith("no edge rows")
    refused = {"self_test": {"reply": {"refused": "no"}}}
    assert dual_run.edge_differences("c", python, refused) == []


def test_the_shell_sends_the_namespace_and_the_standard_library_of_the_reply_profile() -> None:
    """AD-372: the shell reads the configuration and owns the profile table, not the core."""
    name = "s2/complete-a-builtin-import-is-exempt"
    case = next(c for c in dual_run.corpus_cases() if c.id == name)
    with dual_run.materialized(case) as root:
        request = dual_run.engine_request(case, root, Selection())
    assert request["protocol"] == "archkeel-dual-run-2"
    assert (request["namespace"], request["profile"], request["standard_library"]) == (
        "shop",
        "",
        [],
    )
    rust = b'{"facts": {"profile": "archkeel-rust-imports"}}'
    expected = ("archkeel-rust-imports", ["alloc", "core", "std"])
    assert dual_run.reply_profile(rust) == expected
    assert dual_run.reply_profile(zlib.compress(rust)) == expected
    assert dual_run.reply_profile(b"not json") == ("", [])
    assert dual_run.reply_profile(b'{"facts": {"profile": "unknown"}}') == ("", [])


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({}, None),
        ({"status": "PASS"}, "the status is PASS, the rows give FAIL"),
        ({"violations": {}}, "the rule A is FAIL with 0 violations and reason False"),
        ({"explained": {}}, "the rule B is UNKNOWN with 0 violations and reason False"),
        ({"explained": {"B": "why", "C": "why"}}, "the rule C has an explaining row but no status"),
    ],
)
def test_a_frame_status_follows_from_its_rows_and_each_status_has_its_row(
    change: dict[str, Any], problem: str | None
) -> None:
    """AD-378, L-23: a FAIL rule without a violation row, an UNKNOWN rule without a reason and a
    status that the rows do not give are inconsistent frames, never compared."""
    frame: dict[str, Any] = {
        "status": "FAIL",
        "rules": {"A": ["complete_assignment", "FAIL"], "B": ["root_layout", "UNKNOWN"]},
        "explained": {"B": "why"},
        "violations": {"A": 2},
        "unsupported": {"rules": {}},
        "self_test": {"contract": {"rules": {}}, "reply": {"files": 1}},
    }
    frame.update(change)
    assert dual_run.unexplained(frame) == problem
    assert dual_run.unexplained({"rules": {}}) is None
    passed = {**frame, "status": "PASS", "rules": {"A": ["root_layout", "PASS"]}}
    passed.update({"explained": {}, "violations": {}})
    assert dual_run.unexplained(passed) is None
    assert dual_run.unexplained({**passed, "unsupported": {"rules": {"X": "why"}}}) is not None
