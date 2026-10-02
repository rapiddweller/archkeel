# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure existing evidence without turning incomplete decisions into passes."""

import json
import subprocess
from pathlib import Path

import pytest
from test_boundary_types_nested_dtos import _write_app
from test_inside_publication import _child, _inside

from archkeel.analyzer.embedded.report import analyze_snapshot
from tools import rule_yield
from tools.rule_yield import _captured_analysis, _rule_measures, measure


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
    _repin(root)


def test_a_known_violation_and_unknown_are_not_mutually_exclusive(tmp_path: Path) -> None:
    _repo(tmp_path, "tuple[object, Missing]")

    metrics, observation = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["violation_records"] == 1
    assert rule["unknown_by_cause"] == {"unresolved_name": 1}
    assert rule["declared_positions"] == 2
    assert rule["decided_positions"] == 1
    assert rule["decided_pass_positions"] == 1
    assert rule["violation_positions"] == 1
    assert rule["unknown_positions"] == 1
    assert rule["violation_unknown_overlap"] == 1
    assert rule["population_reconciled"] is True
    assert rule["replay_matches"] is True
    assert rule["runtime_seconds"] > 0
    assert metrics["analyzer"] == observation["analyzer"]
    assert metrics["canonical_capture_matches"] is True
    assert metrics["source"] == observation["source"]
    assert metrics["contract"] == observation["contract"]
    assert len(observation["violations"]) == 1
    assert len([r for r in observation["unknowns"] if r["kind"] == "boundary_type_position"]) == 1
    assert not subprocess.check_output(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], text=True
    )


def test_a_captured_safe_population_has_a_real_denominator(tmp_path: Path) -> None:
    _repo(tmp_path, "str")

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["violation_records"] == 0
    assert rule["unknown_by_cause"] == {}
    assert rule["declared_positions"] == 2
    assert rule["decided_positions"] == 2
    assert rule["decided_pass_positions"] == 2
    assert rule["population_reconciled"] is True
    assert rule["complete_scope"] is True
    assert not rule["evidence_gaps"]


def test_an_incoherent_current_aggregate_is_rejected_by_the_core_projection(tmp_path: Path) -> None:
    _repo(tmp_path, "Missing")
    _, observation = measure(tmp_path, repeats=1)
    observation["unknowns"] = [
        row for row in observation["unknowns"] if row["kind"] != "boundary_type_position"
    ]

    with pytest.raises(ValueError):
        _rule_measures(observation, {})


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
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    assert metrics["rules"] == []
    assert metrics["boundary_rules_measured"] == 0
    assert "No boundary_types rule" in " ".join(metrics["evidence_gaps"])


def test_measurement_refuses_an_unpinned_worktree(tmp_path: Path) -> None:
    _repo(tmp_path, "object")
    (tmp_path / "sample/app/impl.py").write_text("changed\n")

    with pytest.raises(ValueError, match="clean Git snapshot"):
        measure(tmp_path, repeats=1)


def _repin(root: Path) -> None:
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
            "Pin changed input",
        ],
        check=True,
    )


def test_capture_is_byte_equal_to_the_plain_canonical_scan(tmp_path: Path) -> None:
    _repo(tmp_path, "tuple[object, Missing]")
    head = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    arguments = {
        "git_head": head,
        "dirty": False,
        "contract_root": tmp_path,
        "contract_path": tmp_path / "contract.json",
        "roots": ("sample",),
        "namespace": "sample",
        "language": "python",
    }
    plain, _ = analyze_snapshot(tmp_path, **arguments)
    captured, _ = _captured_analysis(tmp_path, arguments)

    assert (
        json.dumps(captured, sort_keys=True).encode() == json.dumps(plain, sort_keys=True).encode()
    )


def test_structurally_equal_but_changed_wire_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, "str")
    capture = rule_yield._captured_analysis

    def changed_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        assert model["coverage"]["ast_coverage_percent"] == 100.0
        model["coverage"]["ast_coverage_percent"] = 100
        return model, calls

    monkeypatch.setattr(rule_yield, "_captured_analysis", changed_capture)

    with pytest.raises(ValueError, match="profiling changed the canonical observation"):
        measure(tmp_path, repeats=1)


@pytest.mark.parametrize("annotation", ["object", "dict[str, object]"])
def test_allowanced_broad_and_opaque_positions_are_not_passes(
    tmp_path: Path, annotation: str
) -> None:
    _repo(tmp_path, annotation)
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    outer = {
        "qualified_name": "sample.app.impl.convert",
        "position": "value",
        "annotation": annotation,
    }
    raw["rules"][0]["allowed_positions"] = [outer]
    if annotation.startswith("dict"):
        raw["rules"][0]["allowed_positions"].append({**outer, "container_depth": 1})
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["declared_positions"] == 2
    assert rule["decided_positions"] == 2
    assert rule["decided_pass_positions"] == 1
    assert rule["allowanced_positions"] == 1
    assert rule["opaque_allowanced_positions"] == 1
    assert rule["violation_positions"] == 0


def test_a_nested_allowance_can_share_a_position_with_a_remaining_violation(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    (tmp_path / "sample/app/impl.py").write_text(
        "class Request:\n    left: dict[str, str]\n    right: object\n"
        "def convert(value: Request) -> str: return str(value)\n"
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"].append("sample.app.impl:Request")
    raw["rules"][0]["allowed_positions"] = [
        {
            "qualified_name": "sample.app.impl.convert",
            "position": "value",
            "annotation": "dict[str, str]",
            "field_path": "left",
        }
    ]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    [position] = [row for row in rule["positions"] if row["position"] == "value"]
    assert position["violation_ids"] and position["allowance_ids"]
    assert position["pass"] is False
    assert rule["population_reconciled"] is True
    assert rule["violation_positions"] == rule["allowanced_positions"] == 1


def test_repeated_functions_keep_distinct_symbol_occurrences(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    source = tmp_path / "sample/app/impl.py"
    source.write_text(source.read_text() * 2)
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert len(rule["positions"]) == 4
    assert len({row["symbol_id"] for row in rule["positions"]}) == 2
    assert len({row["id"] for row in rule["positions"]}) == 4


def test_inherited_positions_keep_the_origin_method_suffix(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    (tmp_path / "sample/app/impl.py").write_text(
        "from typing import Generic, TypeVar\nT = TypeVar('T')\nclass Payload: pass\n"
        "class Base(Generic[T]):\n    def get(self) -> T: ...\n"
        "class Child(Base[Payload]): pass\n"
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"] = ["sample.app.impl:Child", "sample.app.impl:Payload"]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    [method] = [row for row in rule["positions"] if row["qualified_name"].endswith(".get")]
    assert method["identity_suffix"]
    assert method["position"] == "return" and method["annotation"] == "T"
    assert method["pass"] is True
    assert rule["population_reconciled"] is True


def test_an_unresolved_route_is_not_complete_decision_coverage(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    (tmp_path / "sample/app/__init__.py").write_text("from .missing import convert\n")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"] = ["sample.app:convert"]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["complete_scope"] is False
    assert "unresolved_reexport_route" in rule["unknown_by_cause"]
    assert rule["assessment_status"] == "UNKNOWN"


def test_nonboundary_assessment_pass_is_not_a_positional_pass_count(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["rules"].append(
        {
            "id": "NO-IMPORT",
            "kind": "forbidden_dependency",
            "source": "sample.app",
            "target": "sample.app",
            "include_type_checking": True,
            "rationale": "Keep the fixture import free.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    )
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    rule = next(row for row in metrics["rules"] if row["id"] == "NO-IMPORT")
    assert rule["assessment_status"] == "PASS"
    assert rule["decided_pass_positions"] is None


def test_additional_ambiguous_facade_positions_join_the_population(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    package = tmp_path / "sample/app"
    (package / "__init__.py").write_text("from .impl import convert\n")
    (package / "other.py").write_text("def convert(value: str) -> str: return value\n")
    (package / "facade.py").write_text(
        "from .impl import convert\nfrom .other import convert\n__all__ = ['convert']\n"
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"] = ["sample.app:convert", "sample.app.facade:convert"]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["declared_positions"] == 6
    assert len(rule["positions"]) == 6
    assert rule["decided_pass_positions"] == 2
    assert rule["unknown_positions"] == 4
    assert rule["population_reconciled"] is True
    assert len({row["id"] for row in rule["positions"]}) == 6


def test_unscoped_api_unknown_stays_separate_from_a_safe_rule(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    source = tmp_path / "sample/app/impl.py"
    source.write_text(
        source.read_text() + "from pydantic import JsonValue\nJsonObject = dict[str, JsonValue]\n"
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["declarations"] = {"public_api": ["sample.app.impl:JsonObject"]}
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["population_reconciled"] is True
    assert rule["complete_scope"] is False
    assert rule["decided_pass_positions"] == 2
    assert rule["unknown_by_cause"] == {}
    assert rule["assessment_status"] == "PASS"
    [unknown] = metrics["unscoped_api_unknowns"]
    assert unknown["data"]["module"] == "sample.app.impl"
    assert unknown["subjects"] == ["sample.app.impl:JsonObject"]
    assert unknown["rule_ids"] == []
    assert rule["scope_gap_ids"] == []
    assert metrics["global_api_scope_complete"] is False


@pytest.mark.parametrize("annotation", ["str", "tuple[object, Missing]"])
def test_lost_producer_capture_cannot_invent_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, annotation: str
) -> None:
    _repo(tmp_path, annotation)
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        return model, [
            call
            for call in calls
            if not (
                call[0] is rule_yield._boundary_type_violation_records
                and call[1]["position"] == "value"
            )
        ]

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["population_reconciled"] is False
    assert rule["decided_pass_positions"] is None
    assert rule["declared_positions"] == (2 if "Missing" in annotation else None)
    assert rule["complete_scope"] is False


@pytest.mark.parametrize("copies", [0, 2])
def test_incomplete_population_receipts_keep_readable_positions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, copies: int
) -> None:
    _repo(tmp_path, "str")
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        return model, [
            repeated
            for call in calls
            for repeated in [call]
            * (copies if call[0] is rule_yield._boundary_rule_positions else 1)
        ]

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["population_reconciled"] is False
    assert rule["decided_pass_positions"] is None
    assert len(rule["positions"]) == 2
    for position in rule["positions"]:
        assert position["pass"] is True
        assert position["violation_ids"] == []
        assert position["allowance_ids"] == []


@pytest.mark.parametrize("loss", ["capture", "publication"])
def test_lost_allowance_capture_or_publication_cannot_certify_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, loss: str
) -> None:
    _repo(tmp_path, "object")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["rules"][0]["allowed_positions"] = [
        {"qualified_name": "sample.app.impl.convert", "position": "value", "annotation": "object"}
    ]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        adjusted = []
        for function, inputs, result in calls:
            if function is rule_yield._boundary_type_allowance_fact:
                if loss == "capture":
                    continue
                if result is not None:
                    result = {**result, "id": "not-published"}
            adjusted.append((function, inputs, result))
        return model, adjusted

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["allowance_records"] == 1
    assert rule["population_reconciled"] is False
    assert rule["allowanced_positions"] is None
    assert rule["decided_pass_positions"] is None


def test_incomplete_scan_cannot_claim_complete_global_api_scope(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    (tmp_path / "sample/app/broken.py").write_text("def broken(\n")
    _repin(tmp_path)

    metrics, observation = measure(tmp_path, repeats=1)

    assert observation["coverage"]["status"] == "FAIL"
    assert metrics["scan_exit_code"] == 2
    assert metrics["unscoped_api_unknowns"] == []
    assert metrics["global_api_scope_complete"] is False
    [rule] = metrics["rules"]
    assert rule["complete_scope"] is False
    assert rule["assessment_status"] == "UNKNOWN"
    assert rule["population_reconciled"] is True
    assert rule["decided_pass_positions"] == 2


def test_contract_path_steps_cross_the_real_json_wire_boundary(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["declarations"] = {
        "paths": [
            {
                "id": "PATH-ONE",
                "label": "Convert",
                "kind": "read",
                "steps": ["sample.app"],
                "provenance": ["docs/architecture/sample.md"],
            }
        ]
    }
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, observation = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["population_reconciled"] is True
    assert rule["decided_pass_positions"] == 2
    [path] = [row for row in observation["declarations"] if row["id"] == "PATH-ONE"]
    assert path["data"]["steps"] == ("sample.app",)


def test_root_and_inside_rules_preserve_scope_and_occurrence_identity(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["inside"] = "inside.json"
    child_rule = {**raw["rules"][0], "source": "sample.app.impl"}
    (tmp_path / "inside.json").write_text(
        json.dumps(
            _inside(
                [_child("api", "sample.app.impl", public=["sample.app.impl:convert"])],
                [child_rule],
            )
        )
    )
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    assert len(metrics["rules"]) == 2
    positions = [position for rule in metrics["rules"] for position in rule["positions"]]
    assert len(positions) == len({position["id"] for position in positions}) == 4
    assert len({position["scope"] for position in positions}) == 2
    assert all(rule["population_reconciled"] for rule in metrics["rules"])
    assert all(rule["decided_pass_positions"] == 2 for rule in metrics["rules"])


def test_lost_ambiguous_producer_capture_is_not_a_proved_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, "str")
    package = tmp_path / "sample/app"
    (package / "other.py").write_text("def convert(value: str) -> str: return value\n")
    (package / "facade.py").write_text(
        "from .impl import convert\nfrom .other import convert\n__all__ = ['convert']\n"
    )
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"] = ["sample.app.facade:convert"]
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        return model, [
            call for call in calls if call[0] is not rule_yield._boundary_type_violation_records
        ]

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    [rule] = metrics["rules"]
    assert rule["population_reconciled"] is False
    assert rule["decided_pass_positions"] is None
