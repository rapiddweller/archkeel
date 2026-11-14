# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The UML target row of a contract through the release core and the default CLI (AD-470).

Release 4.0.1 compares `declarations.uml` with the source facts. The core compares the module,
import and TypeScript symbol parts (AD-494, AD-498). Each plant is a defect that 4.0.1 reports:
a refusal, a FAIL or an UNKNOWN. The core gives no PASS for any of them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, case_root, run
from test_cli_core_inside_trees import tree

from archkeel.cli import core_only

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ROW = "UML-TARGET-a2e40c5592b1b06a"
UNDECIDED = "the UML target: {count} assessments cannot be decided: "
MOUNTED = (
    "the UML target: an inside contract has its own UML target, which the core does not compare"
)
Plant = Callable[[dict[str, Any]], None]


@pytest.fixture(autouse=True)
def release(release_core: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)


def _copy(tmp_path: Path, name: str, plant: Plant | None = None) -> Path:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    if plant is not None:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        plant(contract)
        path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    # The core reads the Git head of the root, so the copy is a clean repository.
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    for command in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run([*git, *command], cwd=root, check=True, capture_output=True)
    return root


def _rows(envelope: dict[str, Any]) -> dict[str, list[str]]:
    return envelope["frame"].get("rules", {})


def _uml(contract: dict[str, Any]) -> dict[str, Any]:
    return contract["declarations"]["uml"]


def _entity(contract: dict[str, Any], identity: str) -> dict[str, Any]:
    return next(item for item in _uml(contract)["entities"] if item["id"] == identity)


# AD-494 and AD-498: the core compares the module, import and symbol assessments of a
# TypeScript target. It leaves exactly the assessments undecided that release 4.0.1 leaves
# undecided (9 and 3), so the row stays UNKNOWN by its count.
@pytest.mark.parametrize(
    ("name", "passes", "undecided"),
    [("H-typescript", 9, 9), ("H-uml-typescript", 0, 3)],
)
def test_the_uml_target_is_an_unknown_row_with_its_reason_and_not_a_gap(
    tmp_path: Path, name: str, passes: int, undecided: int
) -> None:
    code, envelope = run("validate", "--root", str(_copy(tmp_path, name)))
    rows = _rows(envelope)
    assert rows[ROW] == ["uml_target", "UNKNOWN"]
    assert [row for row in rows.values() if row[1] == "PASS"] == [
        row for row in rows.values() if row[0] != "uml_target" and row[1] == "PASS"
    ]
    assert sum(row[1] == "PASS" for row in rows.values()) == passes
    assert all(row[1] != "UNKNOWN" for rule, row in rows.items() if rule != ROW)
    reason = envelope["frame"]["explained"][ROW]
    assert reason.startswith(UNDECIDED.format(count=undecided)), reason
    assert envelope["frame"]["unknown_kinds"][ROW] == "no_receipt"
    assert envelope["gaps"] == []
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def test_the_report_file_holds_the_same_unknown_uml_row(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    root = _copy(tmp_path, "H-uml-typescript")
    arguments = ("report", "--root", str(root), "--output", str(output))
    code, envelope = run(*arguments, "--format", "json")
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["rules"] == {ROW: ["uml_target", "UNKNOWN"]}
    assert written["status"] == "UNKNOWN"
    assert written["unsupported"] == {"rules": {}, "sections": {}, "report": None}
    assert (code, envelope["status"]) == (2, "UNKNOWN")
    page = tmp_path / "report.html"
    code, _ = run("report", "--root", str(root), "--output", str(page))
    assert ROW in page.read_text(encoding="utf-8")
    assert code == 2


def _wrong_kind(contract: dict[str, Any]) -> None:
    _entity(contract, "base")["kind"] = "interface"


def _wrong_signature(contract: dict[str, Any]) -> None:
    _entity(contract, "helper")["signature"]["returns"] = "number"


def _closed_scope_extra(contract: dict[str, Any]) -> None:
    target = _uml(contract)
    target["entities"] = [e for e in target["entities"] if e["id"] not in {"item", "build"}]
    target["relationships"] = [
        r
        for r in target["relationships"]
        if {r["source_id"], r["target_id"]}.isdisjoint({"item", "build"})
    ]


def _missing_module(contract: dict[str, Any]) -> None:
    entity = dict(_entity(contract, "app-module"))
    entity.update(id="ghost", qualified_name="demo.src.ghost_x2e_ts", file_path="src/ghost.ts")
    _uml(contract)["entities"].append(entity)


def _missing_call(contract: dict[str, Any]) -> None:
    edge = {"id": "work-build", "kind": "calls", "source_id": "work", "target_id": "build"}
    _uml(contract)["relationships"].append({**edge, "provenance": ["docs/target.md"]})


def _missing_provenance(contract: dict[str, Any]) -> None:
    _entity(contract, "port")["provenance"] = ["docs/missing.md"]


# Release 4.0.1 gives FAIL (exit 2) for the first three plants and UNKNOWN (exit 0) for the next
# two. It refuses the contract for the last plant: the cited file is missing. The core gives the
# same rows: FAIL (exit 1) for a symbol conflict and for an extra element of a closed scope
# (AD-498), UNKNOWN for a missing module or call.
@pytest.mark.parametrize(
    "plant",
    [
        _wrong_kind,
        _wrong_signature,
        _closed_scope_extra,
        _missing_module,
        _missing_call,
        _missing_provenance,
    ],
    ids=lambda plant: plant.__name__.strip("_"),
)
def test_a_wrong_uml_target_never_passes(tmp_path: Path, plant: Plant) -> None:
    code, envelope = run("validate", "--root", str(_copy(tmp_path, "H-uml-typescript", plant)))
    if plant is _missing_provenance:
        # AD-466: a cited file that the core cannot read refuses the whole contract.
        assert (code, envelope["status"]) == (2, "UNKNOWN")
        refusal = envelope["frame"]["unsupported"]["rules"]
        assert refusal.startswith("contract hygiene reference.provenance"), refusal
        return
    failing = plant in {_wrong_kind, _wrong_signature, _closed_scope_extra}
    assert (code, envelope["status"]) == ((1, "FAIL") if failing else (2, "UNKNOWN"))
    assert _rows(envelope)[ROW] == ["uml_target", "FAIL" if failing else "UNKNOWN"]
    if failing:
        assert envelope["frame"]["details"][ROW]
    else:
        assert "assessments cannot be decided" in envelope["frame"]["explained"][ROW]


def test_an_empty_uml_target_names_that_it_declares_nothing(tmp_path: Path) -> None:
    def empty(contract: dict[str, Any]) -> None:
        _uml(contract).update(entities=[], relationships=[], scopes=[])

    code, envelope = run("validate", "--root", str(_copy(tmp_path, "H-uml-typescript", empty)))
    assert _rows(envelope) == {ROW: ["uml_target", "UNKNOWN"]}
    reason = "the UML target: it declares no entity, relationship or scope"
    assert envelope["frame"]["explained"][ROW] == reason
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def _unknown_kind(contract: dict[str, Any]) -> None:
    _uml(contract)["entities"][0]["kind"] = "widget"


def _bad_schema_version(contract: dict[str, Any]) -> None:
    _uml(contract)["schema_version"] = "9.9.9"


def _dangling_relationship(contract: dict[str, Any]) -> None:
    edge = {"id": "bad", "kind": "calls", "source_id": "run", "target_id": "nope"}
    _uml(contract)["relationships"].append({**edge, "provenance": ["docs/target.md"]})


def _duplicate_entity(contract: dict[str, Any]) -> None:
    _uml(contract)["entities"].append(dict(_entity(contract, "port")))


def _unknown_parent(contract: dict[str, Any]) -> None:
    _entity(contract, "helper")["parent_id"] = "ghost-parent"


# Release 4.0.1 refuses each of these contracts with `contract.invalid` (exit 2).
@pytest.mark.parametrize(
    ("plant", "message"),
    [
        (_unknown_kind, "entity.kind has an invalid vocabulary value"),
        (_bad_schema_version, "uml.schema_version has an invalid vocabulary value"),
        (_dangling_relationship, "unknown relationship target"),
        (_duplicate_entity, "duplicate contract ID"),
        (_unknown_parent, "unknown lexical parent"),
    ],
    ids=lambda value: value.__name__.strip("_") if callable(value) else "",
)
def test_an_unparseable_uml_target_refuses_the_contract(
    tmp_path: Path, plant: Plant, message: str
) -> None:
    code, envelope = run("validate", "--root", str(_copy(tmp_path, "H-uml-typescript", plant)))
    assert _rows(envelope) == {}
    assert [gap["kind"] for gap in envelope["gaps"]][:1] == ["contract_refused"]
    assert message in envelope["gaps"][0]["reason"]
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def test_a_uml_target_that_changes_after_the_core_read_it_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy(tmp_path, "H-uml-typescript")
    exchange = core_only.exchange

    def stale(*arguments: Any) -> Any:
        answer = exchange(*arguments)
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        _wrong_kind(contract)
        path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
        return answer

    monkeypatch.setattr(core_only, "exchange", stale)
    code, envelope = run("validate", "--root", str(root))
    assert "frame" not in envelope
    assert "contract digest differs" in envelope["refusal"]["message"]
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def test_the_python_uml_fixture_has_an_unknown_row_and_never_passes(tmp_path: Path) -> None:
    """Release 4.0.1 passes this target with symbol facts; the core has none for Python (PR2)."""
    code, envelope = run("validate", "--root", str(_copy(tmp_path, "H-uml")))
    assert _rows(envelope) == {ROW: ["uml_target", "UNKNOWN"]}
    assert "assessments cannot be decided" in envelope["frame"]["explained"][ROW]
    assert envelope["gaps"] == []
    assert (code, envelope["status"], envelope["frame"]["status"]) == (2, "UNKNOWN", "UNKNOWN")


def _symbol(identity: str) -> dict[str, Any]:
    return {
        "id": identity,
        "kind": "symbol",
        "qualified_name": "String",
        "language": "typescript",
        "presence": "referenced",
        "provenance": ["README.md"],
    }


def _target(path: Path, identities: list[str]) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    entities = [_symbol(identity) for identity in identities]
    uml = {"schema_version": "1.1.0", "entities": entities, "relationships": [], "scopes": []}
    document["declarations"] = {**document.get("declarations", {}), "uml": uml}
    path.write_text(json.dumps(document), encoding="utf-8")


def test_a_mounted_contract_with_its_own_target_has_one_row_that_sums_the_tree() -> None:
    """A tree has one UML row at the id of its root path. A target in a mount keeps the row
    UNKNOWN by name (AD-494), and it holds back the PASS of the tree."""
    with case_root(HONEST) as root:
        tree(root)
        code, envelope = run("validate", "--root", str(root))
        assert (code, envelope["status"]) == (0, "PASS"), envelope
        _target(root / "inside.json", ["inner-string"])
        code, envelope = run("validate", "--root", str(root))
        rows = _rows(envelope)
        assert rows[ROW] == ["uml_target", "UNKNOWN"]
        assert [rule for rule, row in rows.items() if row[1] != "PASS"] == [ROW]
        assert envelope["frame"]["explained"][ROW] == MOUNTED
        assert (code, envelope["status"]) == (2, "UNKNOWN")
        _target(root / "architecture-contract.json", ["root-string", "root-string-2"])
        _target(root / "deep.json", ["deep-string"])
        code, envelope = run("validate", "--root", str(root))
        assert [rule for rule in _rows(envelope) if rule.startswith("UML-TARGET-")] == [ROW]
        assert envelope["frame"]["explained"][ROW] == MOUNTED
        assert (code, envelope["status"]) == (2, "UNKNOWN")
