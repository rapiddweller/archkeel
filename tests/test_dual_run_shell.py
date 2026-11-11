# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shell side of the dual run of slice S2 (AD-372): the settings and the edge comparison."""

from __future__ import annotations

import zlib
from typing import Any

from tools import dual_run
from tools.dual_run_oracle import Selection


def _edge(identifier: str, count: int, rank: int) -> dict[str, Any]:
    data = {"level": "module", "count": count, "source_rank": rank, "target_rank": rank + 1}
    return {"id": identifier, "rule_ids": [], "kind": "module_dependency", "data": data}


def _without_ranks(row: dict[str, Any]) -> dict[str, Any]:
    data = {k: v for k, v in row["data"].items() if k not in dual_run.RANK_FIELDS}
    return {**row, "data": data}


def test_the_edge_rows_compare_without_the_ranks_and_name_each_difference() -> None:
    """AD-372: the edge lists compare on every case while the ranks of S3 are not ported."""
    python = [_edge("EDGE-1", 1, 0), _edge("EDGE-2", 2, 3)]
    reply = {"self_test": {"reply": {"files": 3}}}
    equal = {**reply, "edges": [_without_ranks(row) for row in python]}
    assert dual_run.edge_differences("c", python, equal) == []
    dropped = {**reply, "edges": equal["edges"][:1]}
    assert [d.scope for d in dual_run.edge_differences("c", python, dropped)] == ["edges"]
    changed = {**reply, "edges": [equal["edges"][0], _without_ranks(_edge("EDGE-2", 1, 0))]}
    assert dual_run.edge_differences("c", python, changed)[0].id == "EDGE-2"
    with_ranks = {**reply, "edges": python}
    assert dual_run.edge_differences("c", python, with_ranks)
    # An engine without edge rows differs, unless its refusal of the reply is already named.
    assert dual_run.edge_differences("c", python, reply)[0].detail.endswith("no edge rows")
    refused = {"self_test": {"reply": {"refused": "no"}}}
    assert dual_run.edge_differences("c", python, refused) == []


def test_the_shell_sends_the_namespace_and_the_standard_library_of_the_reply_profile() -> None:
    """AD-372: the shell reads the configuration and owns the profile table, not the core."""
    name = "s2/complete-a-builtin-import-is-exempt"
    case = next(c for c in dual_run.corpus_cases() if c.id == name)
    with dual_run.materialized(case) as root:
        request = dual_run.engine_request(case, root, Selection())
    assert request["protocol"] == "archkeel-dual-run-2"
    assert (request["namespace"], request["standard_library"]) == ("shop", [])
    rust = b'{"facts": {"profile": "archkeel-rust-imports"}}'
    assert dual_run.standard_library(rust) == ["alloc", "core", "std"]
    assert dual_run.standard_library(zlib.compress(rust)) == ["alloc", "core", "std"]
    assert dual_run.standard_library(b"not json") == []
    assert dual_run.standard_library(b'{"facts": {"profile": "unknown"}}') == []
