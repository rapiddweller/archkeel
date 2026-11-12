# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shell side of the dual run of slices S2 to S4 (AD-372, AD-374, AD-378): the settings, the
edge comparison and the check of the frame status; and the inside-contract tree loop (AD-379)."""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tools import dual_run, dual_run_tree
from tools.dual_run_oracle import BEYOND, Selection, compare_case


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
    assert request["protocol"] == "archkeel-dual-run-3"
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
    passed.update({"explained": {}, "violations": {}, "scope": "complete"})
    assert dual_run.unexplained(passed) is None
    # L-35b: PASS needs a complete scope, also with zero rules.
    assert dual_run.unexplained({**passed, "scope": "incomplete scope: x"}) is not None
    assert dual_run.unexplained({**passed, "rules": {}, "scope": "incomplete scope: x"}) is not None
    assert dual_run.unexplained({**passed, "rules": {}}) is None
    # A core frame without a status is refused; another engine has nothing to check.
    assert dual_run.unexplained({"engine": "archkeel-core x", "rules": {}}) is not None
    assert dual_run.unexplained({**passed, "unsupported": {"rules": {"X": "why"}}}) is not None


def test_a_pass_beyond_the_python_engine_is_named_only_over_a_kept_gap() -> None:
    """AD-384 point 7: the harness names a core PASS over a Python UNKNOWN only when the frame
    lists the rule in `beyond`, and a rule in `beyond` must be a PASS of a run that gaps hold."""
    held = "incomplete scope: 1 gaps between two modules that the contract does not allow: a -> b"
    frame: dict[str, Any] = {
        "status": "UNKNOWN",
        "rules": {"A": ["complete_assignment", "PASS"]},
        "explained": {},
        "violations": {},
        "beyond": {"A": "no one of the 1 kept pair gaps can change the rule"},
        "scope": held,
        "unsupported": {"rules": {}},
        "self_test": {"contract": {"rules": {}}, "reply": {"files": 1}},
    }
    assert dual_run.unexplained(frame) is None
    oracle = {"case": {"id": "c"}, "rules": {"A": ["complete_assignment", "UNKNOWN"]}}
    selection = Selection((), frozenset({"complete_assignment"}))
    found = compare_case(oracle, frame, selection)
    assert [d.detail for d in found] == [BEYOND + frame["beyond"]["A"]]
    # Without `beyond` the same PASS is a plain difference.
    plain = compare_case(oracle, {**frame, "beyond": {}}, selection)
    assert [d.detail for d in plain] == [
        "expected ['complete_assignment', 'UNKNOWN'], found ['complete_assignment', 'PASS']"
    ]
    # A Python FAIL is never beyond; a rule in `beyond` must pass over a scope that gaps hold.
    failed = {"case": {"id": "c"}, "rules": {"A": ["complete_assignment", "FAIL"]}}
    assert not compare_case(failed, frame, selection)[0].detail.startswith(BEYOND)
    assert dual_run.unexplained({**frame, "scope": "complete", "status": "PASS"}) is not None
    unknown = {**frame, "rules": {"A": ["complete_assignment", "UNKNOWN"]}, "explained": {"A": "x"}}
    assert dual_run.unexplained(unknown) is not None


def _mounting(path: str) -> dict[str, Any]:
    return {"self_test": {"contract": {"missing": [path]}}}


def _parsed() -> dict[str, Any]:
    return {"self_test": {"contract": {"rules": {}}}}


def test_the_shell_reads_each_asked_inside_contract_in_rounds(tmp_path: Path) -> None:
    """AD-379: the shell sends each asked file with its resolved identity, round by round, until
    the frame names no path."""
    (tmp_path / "a.json").write_bytes(b"A")
    (tmp_path / "b.json").write_bytes(b"B")
    sent: list[list[dict[str, str]]] = []

    def send(request: Mapping[str, Any]) -> dict[str, Any]:
        sent.append(list(request["insides"]))
        return [_mounting("a.json"), _mounting("b.json"), _parsed()][len(sent) - 1]

    frame = dual_run_tree.tree_frame(send, {"insides": []}, tmp_path)
    assert frame == _parsed()
    assert [len(item) for item in sent] == [0, 1, 2]
    assert sent[2][1] == {"reference": "b.json", "identity": "b.json", "hex": b"B".hex()}


def test_a_link_keeps_its_resolved_identity_and_a_path_outside_is_not_read(
    tmp_path: Path,
) -> None:
    """AD-366 duties: the identity is the resolved path, so the core sees a link; a path that
    resolves outside the repository is never read, and the frame keeps naming it."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "real.json").write_bytes(b"R")
    (repository / "link.json").symlink_to(repository / "real.json")
    (tmp_path / "outside.json").write_bytes(b"O")
    (repository / "out.json").symlink_to(tmp_path / "outside.json")
    assert dual_run_tree.read_inside(repository, "link.json", 10) == ("real.json", b"R")
    assert dual_run_tree.read_inside(repository, "out.json", 10) is None
    assert dual_run_tree.read_inside(repository, "../outside.json", 10) is None
    assert dual_run_tree.read_inside(repository, "absent.json", 10) is None
    missing = _mounting("out.json")
    assert dual_run_tree.tree_frame(lambda _: missing, {"insides": []}, repository) == missing


def test_the_rounds_the_files_and_the_bytes_of_the_shell_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-379: a hostile tree cannot make the shell read without end; each bound is named."""
    for index in range(4):
        (tmp_path / f"{index}.json").write_bytes(b"x" * 8)
    rounds = iter(range(10))

    def chain(_: Mapping[str, Any]) -> dict[str, Any]:
        return _mounting(f"{next(rounds)}.json")

    monkeypatch.setattr(dual_run_tree, "MAX_ROUNDS", 3)
    frame = dual_run_tree.tree_frame(chain, {"insides": []}, tmp_path)
    assert frame == {"error": "the tree needs more than 3 rounds"}
    monkeypatch.setattr(dual_run_tree, "MAX_ROUNDS", 10)
    monkeypatch.setattr(dual_run_tree, "MAX_FILES", 2)
    rounds = iter(range(10))
    frame = dual_run_tree.tree_frame(chain, {"insides": []}, tmp_path)
    assert frame == {"error": "the tree needs more than 2 inside contracts"}
    monkeypatch.setattr(dual_run_tree, "MAX_FILES", 10)
    monkeypatch.setattr(dual_run_tree, "MAX_BYTES", 12)
    rounds = iter(range(10))
    frame = dual_run_tree.tree_frame(chain, {"insides": []}, tmp_path)
    assert frame == {"error": "the inside contracts hold more than 12 bytes"}


def test_a_frame_with_an_error_or_without_missing_paths_ends_the_loop(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"A")
    error = {"error": "the engine exits with 2", "self_test": {"contract": {"missing": ["a"]}}}
    calls: list[Mapping[str, Any]] = []

    def send(request: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(request)
        return error

    assert dual_run_tree.tree_frame(send, {"insides": []}, tmp_path) == error
    assert len(calls) == 1
    assert dual_run_tree.missing_paths({"self_test": {"contract": {"missing": []}}}) is None


def _chain_core(depth: int) -> Any:
    """A fake core for a chain of `depth` mounts: it asks for the next file until it has all."""

    def send(request: Mapping[str, Any]) -> dict[str, Any]:
        count = len(request["insides"])
        return _parsed() if count == depth else _mounting(f"{count}.json")

    return send


def test_exactly_the_file_bound_finishes_and_one_file_more_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-379: the shell bound is inclusive: `MAX_FILES` files finish (injected bound 3)."""
    for index in range(4):
        (tmp_path / f"{index}.json").write_bytes(b"x")
    monkeypatch.setattr(dual_run_tree, "MAX_FILES", 3)
    assert dual_run_tree.tree_frame(_chain_core(3), {"insides": []}, tmp_path) == _parsed()
    frame = dual_run_tree.tree_frame(_chain_core(4), {"insides": []}, tmp_path)
    assert frame == {"error": "the tree needs more than 3 inside contracts"}


def test_a_chain_at_the_depth_bound_finishes_through_the_shell(tmp_path: Path) -> None:
    """AD-379: a chain of 900 mounts needs 900 reading rounds and a last one: the real bound of
    901 rounds lets it finish, and a chain of 901 mounts stops at the round bound."""
    for index in range(901):
        (tmp_path / f"{index}.json").write_bytes(b"{}")
    assert dual_run_tree.MAX_ROUNDS == 901
    assert dual_run_tree.tree_frame(_chain_core(900), {"insides": []}, tmp_path) == _parsed()
    frame = dual_run_tree.tree_frame(_chain_core(901), {"insides": []}, tmp_path)
    assert frame == {"error": "the tree needs more than 901 rounds"}
