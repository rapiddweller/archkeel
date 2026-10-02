# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure existing evidence without turning incomplete decisions into passes."""

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component
from test_boundary_types_nested_dtos import _write_app
from test_dart_directives import dart_package
from test_inside_publication import _child, _inside, _rule

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


def test_replay_keeps_import_proof_before_the_scanner_strips_it(tmp_path: Path) -> None:
    _repo(tmp_path, "str")
    package = tmp_path / "sample/app"
    (package / "__init__.py").write_text("from .facade import convert\n__all__ = ['convert']\n")
    (package / "facade.py").write_text("from .impl import convert\n__all__ = ['convert']\n")
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"][0]["public"] = ["sample.app:convert"]
    raw["components"][0]["inside"] = "inside.json"
    contract.write_text(json.dumps(raw))
    (tmp_path / "inside.json").write_text(
        json.dumps(
            _inside(
                [
                    _child("facade", "sample.app.facade", public=["sample.app.facade:convert"]),
                    _child("impl", "sample.app.impl"),
                ],
                [{**raw["rules"][0], "id": "INNER-TYPES", "source": "sample.app.facade"}],
            )
        )
    )
    _repin(tmp_path)

    metrics, observation = measure(tmp_path, repeats=1)

    assert len(metrics["rules"]) == 2
    assert all(row["replay_matches"] is True for row in metrics["rules"])
    assert all(row["runtime_seconds"] > 0 for row in metrics["rules"])
    assert metrics["canonical_capture_matches"] is True
    assert not [row for row in observation["unknowns"] if row["rule_ids"]]
    assert all("module_level_import" not in row["data"] for row in observation["imports"])


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
    assert rule["import_ledger"]["unit"] == "import"
    assert rule["import_ledger"]["decided_passes"] == 0


def _import_repo(root: Path) -> None:
    _repo(root, "str")
    contract = root / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"] += [
        _component("client", public=[]),
        _component("target", public=["sample.target:published"]),
    ]
    raw["rules"] += [
        _rule(
            "NO-SECRET",
            "forbidden_dependency",
            source="sample.client",
            target="sample.target",
            target_symbol="secret",
            include_type_checking=False,
        ),
        _rule("INTERFACES", "interface_boundary", include_type_checking=False),
    ]
    contract.write_text(json.dumps(raw))
    (root / "sample/target.py").write_text(
        "def published() -> str: return 'yes'\n"
        "def private() -> str: return 'private'\n"
        "def secret() -> str: return 'secret'\n"
    )
    (root / "sample/client.py").write_text(
        "from sample.target import published, private, secret\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from sample.target import secret as typing_secret\n"
    )
    _repin(root)


def _scope_repo(root: Path) -> None:
    _repo(root, "str")
    contract = root / "contract.json"
    raw = json.loads(contract.read_text())
    raw["rules"] = [
        _rule("ASSIGN", "complete_assignment", source="sample"),
        _rule("LAYOUT", "root_layout", root="sample", allowed_children=["sample.app"]),
        _rule("CONSTRUCT", "forbidden_construct", source="sample", constructs=["assert"]),
        _rule("CYCLES", "no_component_cycles"),
        _rule("REQUIRES", "complete_requires"),
        _rule("PERMISSION", "allowed_dependency", source="sample.app", target="sample.app"),
    ]
    raw["components"][0]["inside"] = "inside.json"
    contract.write_text(json.dumps(raw))
    (root / "inside.json").write_text(
        json.dumps(
            _inside(
                [_child("impl", "sample.app.impl")],
                [_rule("ASSIGN", "complete_assignment", source="sample.app")],
            )
        )
    )
    _repin(root)


def test_scope_conjunctions_bind_actual_producer_receipts_and_scopes(tmp_path: Path) -> None:
    _scope_repo(tmp_path)

    metrics, observation = measure(tmp_path, repeats=1)

    receipts = {
        row["id"]: row
        for row in observation["scope_observations"]
        if row["kind"] == "rule_evaluation"
    }
    modules = {row["id"] for row in observation["modules"]}
    for row in metrics["rules"]:
        assert row["decided_pass_positions"] is None
        if row["id"] == "PERMISSION":
            assert row["assessment_status"] == "DECLARATION"
            assert row["decision_unit"] is None
            assert row["scope_ledger"] is None
            continue
        assert row["decision_unit"] == "observed_scope"
        ledger = row["scope_ledger"]
        assert ledger["producer_bound"] is ledger["scope_complete"] is True
        assert ledger["population"] == ledger["decided_passes"] == 1
        assert ledger["decided_violations"] == ledger["unknown_decisions"] == 0
        assert ledger["verdict"] == "PASS"
        receipt = receipts[ledger["receipt_id"]]
        assert receipt["rule_ids"] == [row["id"]]
        assert receipt["data"]["scope"] == ledger["scope"]
        assert ledger["fact_ids"] == receipt["fact_ids"]
        assert set(ledger["fact_ids"]) <= modules
        assert ledger["evidence_ids"] == receipt["evidence_ids"]
    child = next(row for row in metrics["rules"] if row["id"] == "app:ASSIGN")
    assert child["scope_ledger"]["scope"] == "app"
    assert metrics["canonical_capture_matches"] is True


@pytest.mark.parametrize(
    "loss", ["receipt", "completion", "scope", "facts", "duplicate", "publication"]
)
def test_unbound_scope_proof_keeps_predicate_counts_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, loss: str
) -> None:
    _scope_repo(tmp_path)
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        adjusted = []
        for function, inputs, result in calls:
            if function is rule_yield.rule_violations and loss == "completion":
                continue
            if function is rule_yield._rule_evaluation_receipt and inputs["rule"].id == "ASSIGN":
                if loss == "receipt":
                    continue
                if loss == "scope":
                    inputs = {**inputs, "scope": "another-scope"}
                if loss == "facts":
                    inputs = {**inputs, "evaluated": []}
                if loss == "duplicate":
                    adjusted.append((function, inputs, result))
                if loss == "publication":
                    result = {**result, "id": "not-published"}
            adjusted.append((function, inputs, result))
        return model, adjusted

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "ASSIGN")
    assert row["assessment_status"] == "PASS"
    assert row["scope_ledger"]["producer_bound"] is False
    assert row["scope_ledger"]["scope_complete"] is False
    assert row["scope_ledger"]["population"] is None
    assert row["scope_ledger"]["decided_passes"] is None
    assert row["scope_ledger"]["unknown_decisions"] is None


def test_partial_scope_never_turns_a_safe_conjunction_into_a_pass(tmp_path: Path) -> None:
    _scope_repo(tmp_path)
    (tmp_path / "sample/broken.py").write_text("def broken(\n")
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "CONSTRUCT")
    ledger = row["scope_ledger"]
    assert row["assessment_status"] == "UNKNOWN"
    assert ledger["producer_bound"] is True
    assert ledger["scope_complete"] is False
    assert ledger["population"] == ledger["unknown_decisions"] == 1
    assert ledger["decided_passes"] == ledger["decided_violations"] == 0


def test_false_scope_conjunction_keeps_partial_coverage_visible(tmp_path: Path) -> None:
    _scope_repo(tmp_path)
    source = tmp_path / "sample/app/impl.py"
    source.write_text(source.read_text() + "assert True\nassert False\n")
    (tmp_path / "sample/broken.py").write_text("def broken(\n")
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "CONSTRUCT")
    ledger = row["scope_ledger"]
    assert row["violation_records"] == 2
    assert row["assessment_status"] == ledger["verdict"] == "FAIL"
    assert ledger["decided_violations"] == ledger["population"] == 1
    assert ledger["decided_passes"] == ledger["unknown_decisions"] == 0
    assert ledger["scope_complete"] is False
    assert metrics["coverage"]["failures"]


def test_partial_graph_receipt_is_an_unknown_scope_decision(tmp_path: Path) -> None:
    _scope_repo(tmp_path)
    contract = tmp_path / "contract.json"
    raw = json.loads(contract.read_text())
    raw["components"].append(_component("outside", packages=["elsewhere"]))
    contract.write_text(json.dumps(raw))
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "CYCLES")
    assert metrics["coverage"]["status"] == "PASS"
    assert row["assessment_status"] == "UNKNOWN"
    assert row["scope_ledger"]["producer_bound"] is True
    assert row["scope_ledger"]["scope_complete"] is False
    assert row["scope_ledger"]["unknown_decisions"] == 1
    assert row["scope_ledger"]["decided_passes"] == 0


def test_a_false_scope_conjunction_retains_its_actual_unknown_causes(tmp_path: Path) -> None:
    _scope_repo(tmp_path)
    inside = tmp_path / "inside.json"
    raw = json.loads(inside.read_text())
    raw["components"].append(_child("outside", "sample.outside"))
    inside.write_text(json.dumps(raw))
    (tmp_path / "sample/app/unowned.py").write_text("VALUE = 1\n")
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "app:ASSIGN")
    assert row["assessment_status"] == row["scope_ledger"]["verdict"] == "FAIL"
    assert row["scope_ledger"]["decided_violations"] == 1
    assert row["violation_records"] == 1
    assert row["unknown_by_cause"] == {"inside_source_domain_incomplete": 1}


def test_import_passes_are_the_actual_yielded_verdicts(tmp_path: Path) -> None:
    _import_repo(tmp_path)

    metrics, observation = measure(tmp_path, repeats=1)

    rows = {row["id"]: row for row in metrics["rules"]}
    forbidden = rows["NO-SECRET"]["import_ledger"]
    interface = rows["INTERFACES"]["import_ledger"]
    assert forbidden["unit"] == interface["unit"] == "import"
    assert forbidden["population"] == 3
    assert forbidden["decided_passes"] == 2
    assert forbidden["violations"] == 1
    assert forbidden["unknowns"] == 0
    assert interface["population"] == 2
    assert interface["decided_passes"] == interface["violations"] == 1
    assert interface["unknowns"] == 0
    assert forbidden["capture_complete"] is interface["capture_complete"] is True
    assert forbidden["scope_complete"] is interface["scope_complete"] is True
    assert forbidden["scope"] == interface["scope"] == "root"
    assert len(observation["violations"]) == 2
    import_ids = {row["id"] for row in observation["imports"]}
    for ledger in (forbidden, interface):
        assert {row["import_id"] for row in ledger["evaluations"]} <= import_ids
        assert all(row["source_module"] == "sample.client" for row in ledger["evaluations"])
    assert metrics["canonical_capture_matches"] is True


@pytest.mark.parametrize("loss", ["yield", "completion", "scope"])
def test_incomplete_import_capture_cannot_certify_pass_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, loss: str
) -> None:
    _import_repo(tmp_path)
    capture = rule_yield._captured_analysis

    def incomplete_capture(root: Path, arguments: dict) -> tuple[dict, list]:
        model, calls = capture(root, arguments)
        return model, [
            (call[0], {**call[1], "scope": "another-scope"}, call[2])
            if loss == "scope" and call[0] is rule_yield._forbidden_dependency_verdicts
            else call
            for call in calls
            if not (
                call[0] is rule_yield._forbidden_dependency_verdicts
                and (
                    (loss == "completion" and call[2] is None)
                    or (loss == "yield" and call[2] is not None)
                )
            )
        ]

    monkeypatch.setattr(rule_yield, "_captured_analysis", incomplete_capture)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "NO-SECRET")
    assert row["import_ledger"]["capture_complete"] is False
    assert row["import_ledger"]["population"] is None
    assert row["import_ledger"]["decided_passes"] is None


def test_incomplete_scan_retains_import_verdicts_without_scope_closure(tmp_path: Path) -> None:
    _import_repo(tmp_path)
    (tmp_path / "sample/broken.py").write_text("def broken(\n")
    _repin(tmp_path)

    metrics, _ = measure(tmp_path, repeats=1)

    row = next(row for row in metrics["rules"] if row["id"] == "NO-SECRET")
    assert row["import_ledger"]["capture_complete"] is True
    assert row["import_ledger"]["decided_passes"] == 2
    assert row["import_ledger"]["scope_complete"] is False


def test_an_existing_unknown_import_verdict_never_becomes_a_pass(tmp_path: Path) -> None:
    dart_package(
        tmp_path,
        {"lib/client.dart": "import 'target.dart';\n", "lib/target.dart": "class Secret {}\n"},
        components=[
            _component("client", packages=["app.client"]),
            _component("target", packages=["app.target"]),
        ],
        rules=[
            _rule(
                "NO-SECRET",
                "forbidden_dependency",
                source="app.client",
                target="app.target",
                target_symbol="Secret",
                include_type_checking=True,
            )
        ],
        libraries={},
    )
    head = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    model, calls = _captured_analysis(
        tmp_path,
        {
            "git_head": head,
            "dirty": False,
            "contract_path": tmp_path / "contract.json",
            "roots": ("lib",),
            "namespace": "app",
            "language": "dart",
        },
    )

    ledger = rule_yield._import_ledgers(model, calls)["NO-SECRET"]

    assert ledger["capture_complete"] is True
    assert ledger["population"] == ledger["unknowns"] == 1
    assert ledger["decided_passes"] == ledger["violations"] == 0
    assert ledger["evaluations"][0]["verdict"] == "undecided"


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
