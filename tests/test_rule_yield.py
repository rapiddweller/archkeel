# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure existing evidence without turning incomplete decisions into passes."""

import json
import subprocess
from pathlib import Path

import pytest
from test_boundary_types_nested_dtos import _write_app

from tools.rule_yield import _rule_measures, measure


def _repo(root: Path, annotation: str) -> None:
    _write_app(
        root,
        implementation=f"def convert(value: {annotation}) -> str: return str(value)\n",
        declared=("sample.app.impl:convert",),
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Yield test",
            "-c",
            "user.email=yield@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Pin the measurement fixture",
        ],
        check=True,
    )


def test_a_known_violation_and_unknown_are_not_mutually_exclusive(tmp_path: Path) -> None:
    _repo(tmp_path, "tuple[object, Missing]")

    metrics, observation = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["violation_records"] == 1
    assert rule["unknown_by_cause"] == {"unresolved_name": 1}
    assert rule["declared_positions"] == 2
    assert rule["decided_positions"] == 1
    assert rule["decided_pass_positions"] is None
    assert rule["replay_matches"] is True
    assert rule["runtime_seconds"] > 0
    assert metrics["analyzer"] == observation["analyzer"]
    assert metrics["source"] == observation["source"]
    assert metrics["contract"] == observation["contract"]
    assert len(observation["violations"]) == 1
    assert len([r for r in observation["unknowns"] if r["kind"] == "boundary_type_position"]) == 1
    assert not subprocess.check_output(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], text=True
    )


def test_absent_denominator_does_not_become_zero_or_a_pass_count(tmp_path: Path) -> None:
    _repo(tmp_path, "str")

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["violation_records"] == 0
    assert rule["unknown_by_cause"] == {}
    assert rule["declared_positions"] is None
    assert rule["decided_positions"] is None
    assert rule["decided_pass_positions"] is None
    assert rule["evidence_gaps"]


def test_an_aggregate_unknown_is_preserved_without_position_records(tmp_path: Path) -> None:
    _repo(tmp_path, "Missing")
    _, observation = measure(tmp_path, repeats=1)
    observation["unknowns"] = [
        row for row in observation["unknowns"] if row["kind"] != "boundary_type_position"
    ]

    [rule] = _rule_measures(observation, {})

    assert rule["unknown_by_cause"] == {"unresolved_name": 1}
    assert rule["decided_pass_positions"] is None


def test_changed_replay_findings_cannot_publish_a_rule_runtime(tmp_path: Path) -> None:
    _repo(tmp_path, "object")
    _, observation = measure(tmp_path, repeats=1)
    identifier = next(
        row["id"] for row in observation["declarations"] if row["kind"] == "boundary_types"
    )

    [rule] = _rule_measures(observation, {identifier: {"seconds": 1.0, "matches": False}})

    assert rule["violation_records"] == 1
    assert rule["replay_matches"] is False
    assert rule["runtime_seconds"] is None
    assert "changes observed findings" in " ".join(rule["evidence_gaps"])


def test_absent_boundary_policy_is_reported_as_not_measured(tmp_path: Path) -> None:
    _repo(tmp_path, "object")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["rules"] = []
    contract.write_text(json.dumps(raw))
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Yield test",
            "-c",
            "user.email=yield@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Remove policy",
        ],
        check=True,
    )

    metrics, _ = measure(tmp_path, repeats=1)

    assert metrics["rules"] == []
    assert metrics["boundary_rules_measured"] == 0
    assert "No boundary_types rule" in " ".join(metrics["evidence_gaps"])


def test_measurement_refuses_an_unpinned_worktree(tmp_path: Path) -> None:
    _repo(tmp_path, "object")
    (tmp_path / "sample/app/impl.py").write_text("changed\n")

    with pytest.raises(ValueError, match="clean Git snapshot"):
        measure(tmp_path, repeats=1)
