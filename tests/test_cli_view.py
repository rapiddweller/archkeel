# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-284: a view spec is checked data; each reference is proven, declared, claim or unknown."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.model import Observation, Section
from archkeel.ir.view_spec import (
    ViewStatus,
    check_view,
    parse_view_spec,
    snapshot_identity,
    view_check_json,
    view_summary,
)

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "fixtures/F-architecture-view/place-order.json"
_HINTS = (
    '"""Name the order type for annotations only."""\n\n'
    "from __future__ import annotations\n\n"
    "from typing import TYPE_CHECKING\n\n"
    "if TYPE_CHECKING:\n"
    "    from shop.model.entities import Order\n\n\n"
    "def label(order: Order) -> str:\n"
    "    return str(order)\n"
)
_LOADER = (
    '"""Load a renderer by a name known only at run time."""\n\n'
    "import importlib\n\n\n"
    "def load(name: str) -> object:\n"
    '    return importlib.import_module(f"shop.{name}")\n'
)


def _snapshot(tmp_path: Path, overlay: dict[str, str | None] | None = None) -> bytes:
    root = _prepare_repo(tmp_path, overlay or {})
    result, packet = run_report(root, config=load_config(root), analyzer=observe)
    assert result.exit_code == 0 and packet is not None
    return packet


def _observation(packet: bytes) -> Observation:
    raw = decode_json(packet)
    assert isinstance(raw, dict)
    return parse_observation(decode_canonical_model(raw))


@pytest.fixture(scope="module")
def shop(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    return _observation(_snapshot(tmp_path_factory.mktemp("clean")))


@pytest.fixture(scope="module")
def changed(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    """The shop with a dynamic loader, a type-only import and an app -> store requires entry."""
    contract = json.loads((ROOT / "fixtures/F-architecture/architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["id"] == "COMP-APP")
    app["requires"] = [{"component": "store", "rationale": "Use cases persist orders."}]
    header = (ROOT / "fixtures/F-architecture/shop/render/text.py").read_text().split('"""')[0]
    overlay = {
        "shop/render/loader.py": header + _LOADER,
        "shop/render/hints.py": header + _HINTS,
        "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
    }
    return _observation(_snapshot(tmp_path_factory.mktemp("changed"), overlay))


def _spec(observation: Observation, **fields: object) -> dict[str, object]:
    identity = snapshot_identity(observation)
    spec: dict[str, object] = {
        "schema_version": "1.0.0",
        "title": "Place an order",
        "snapshot": {
            "source_digest": identity.source_digest,
            "contract_digest": identity.contract_digest,
        },
        "nodes": ["shop.cli.main", "shop.app.orders", "shop.render.text", "shop.model.entities"],
    }
    spec.update(fields)
    return spec


def _check(observation: Observation, strict: bool = False, **fields: object):
    return check_view(parse_view_spec(_spec(observation, **fields)), observation, strict=strict)


def _edge(source: str, target: str, kind: str | None = "imports", **extra: object) -> dict:
    return {"source": source, "target": target, **({"kind": kind} if kind else {}), **extra}


def test_example_spec_mixes_proven_and_claim_and_is_deterministic(shop: Observation) -> None:
    raw = json.loads(EXAMPLE.read_text())
    identity = snapshot_identity(shop)
    # The Explorer team loads this file: a change to the F source or contract must update it.
    assert raw["snapshot"] == asdict(identity)
    raw["snapshot"] = {
        "source_digest": identity.source_digest,
        "contract_digest": identity.contract_digest,
    }
    spec = parse_view_spec(raw)
    result = check_view(spec, shop, strict=False)
    assert result.exit_code == 0 and result.snapshot_current
    assert {node.id: node.status for node in result.nodes} == {
        "COMP-CLI": ViewStatus.DECLARED,
        "COMP-APP": ViewStatus.DECLARED,
        "shop.cli.main": ViewStatus.PROVEN,
        "shop.app.orders": ViewStatus.PROVEN,
        "shop.store.repository": ViewStatus.PROVEN,
        "shop.store.codec": ViewStatus.PROVEN,
    }
    assert [edge.status for edge in result.edges] == [ViewStatus.PROVEN, ViewStatus.CLAIM]
    proven = result.edges[0]
    assert proven.kind == "imports" and proven.evidence
    assert all(
        site.evidence_id and site.file and site.line and site.record_id.startswith("IMP-")
        for site in proven.evidence
    )
    assert result.edges[1].evidence == ()
    assert [step.status for step in result.steps] == [
        ViewStatus.PROVEN,
        ViewStatus.PROVEN,
        ViewStatus.CLAIM,
        ViewStatus.PROVEN,
    ]
    assert result.steps[1].kind == "calls" and result.steps[1].path == (
        "shop.cli.main",
        "shop.app.orders",
    )
    assert check_view(spec, shop, strict=True).exit_code == 0
    assert view_check_json(result) == view_check_json(check_view(spec, shop, strict=False))
    assert "structure, not runtime order" in view_summary(result)


def test_a_fabricated_node_is_missing(shop: Observation) -> None:
    result = _check(shop, nodes=["shop.cli.main", "shop.app.payments", "COMP-PAYMENTS"])
    assert [(node.id, node.status) for node in result.nodes] == [
        ("shop.cli.main", ViewStatus.PROVEN),
        ("shop.app.payments", ViewStatus.MISSING),
        ("COMP-PAYMENTS", ViewStatus.MISSING),
    ]
    assert result.exit_code == 1


def test_a_fabricated_edge_is_missing(shop: Observation) -> None:
    result = _check(shop, edges=[_edge("shop.render.text", "shop.app.orders")])
    assert result.edges[0].status is ViewStatus.MISSING and result.edges[0].evidence == ()
    assert result.exit_code == 1


def test_a_reversed_edge_is_missing_and_names_the_observed_direction(shop: Observation) -> None:
    result = _check(shop, edges=[_edge("shop.model.entities", "shop.render.text")])
    assert result.edges[0].status is ViewStatus.MISSING
    assert "reverse" in result.edges[0].reason
    forward = _check(shop, edges=[_edge("shop.render.text", "shop.model.entities")])
    assert forward.edges[0].status is ViewStatus.PROVEN and forward.exit_code == 0


def test_a_path_is_structure_not_a_runtime_call(shop: Observation) -> None:
    nodes = ["shop.cli.main", "shop.store.repository"]
    steps = [{"node": "shop.cli.main"}, {"node": "shop.store.repository", "kind": "imports"}]
    result = _check(shop, nodes=nodes, steps=steps)
    step = result.steps[1]
    assert step.status is ViewStatus.PROVEN and step.kind == "imports"
    assert step.path == ("shop.cli.main", "shop.app.orders", "shop.store", "shop.store.repository")
    assert any("structure, not runtime order" in item for item in result.limits)
    # The same pair as one direct call is not an observed edge: a path proves no call.
    call = _check(shop, nodes=nodes, edges=[_edge(*nodes, kind="calls")])
    assert call.edges[0].status is ViewStatus.UNKNOWN
    assert (
        _check(shop, strict=True, nodes=nodes, edges=[_edge(*nodes, kind="calls")]).exit_code == 1
    )


def test_a_stale_snapshot_checks_nothing(shop: Observation) -> None:
    spec = _spec(shop, edges=[_edge("shop.render.text", "shop.model.entities")])
    snapshot = dict(spec["snapshot"])  # type: ignore[call-overload]
    snapshot["source_digest"] = "0" * 64
    spec["snapshot"] = snapshot
    result = check_view(parse_view_spec(spec), shop, strict=False)
    assert result.exit_code == 2 and not result.snapshot_current
    assert (
        result.snapshot == snapshot_identity(shop)
        and result.view_snapshot.source_digest == "0" * 64
    )
    statuses = {item.status for item in (*result.nodes, *result.edges, *result.steps)}
    assert statuses == {ViewStatus.UNKNOWN}


def test_an_unsupported_dynamic_dependency_stays_unknown(changed: Observation) -> None:
    nodes = ["shop.render.loader", "shop.store", "shop.render.text"]
    edges = [_edge("shop.render.loader", "shop.store"), _edge("shop.render.text", "shop.store")]
    result = _check(changed, nodes=nodes, edges=edges)
    assert [edge.status for edge in result.edges] == [ViewStatus.UNKNOWN, ViewStatus.MISSING]
    assert "dynamic" in result.edges[0].reason
    only_loader = _check(changed, nodes=nodes, edges=edges[:1])
    assert only_loader.exit_code == 0
    assert _check(changed, strict=True, nodes=nodes, edges=edges[:1]).exit_code == 1


@pytest.mark.parametrize(
    "styled",
    [
        {"status": "proven"},
        {"evidence": ["EVD-0000000000000000"]},
        {"claim": "proven"},
    ],
)
def test_a_claim_styled_as_proof_is_rejected(shop: Observation, styled: dict) -> None:
    spec = _spec(shop, edges=[_edge("shop.render.text", "shop.app.orders", **styled)])
    with pytest.raises(ValueError):
        parse_view_spec(spec)


def test_a_claim_stays_a_claim_when_the_graph_has_the_edge(shop: Observation) -> None:
    edge = _edge("shop.render.text", "shop.model.entities", claim=True, note="Reads the order.")
    result = _check(shop, edges=[edge])
    assert result.edges[0].status is ViewStatus.CLAIM and result.edges[0].evidence == ()
    assert result.edges[0].note == "Reads the order."


def test_a_zero_contract_graph_has_no_declared_status(shop: Observation) -> None:
    sections = tuple(
        Section(item.name, ()) if item.name == "declarations" else item for item in shop.sections
    )
    bare = replace(shop, sections=sections)
    edges = [_edge("shop.render.text", "shop.model.entities")]
    result = _check(
        bare, nodes=["COMP-APP", "shop.render.text", "shop.model.entities"], edges=edges
    )
    assert [node.status for node in result.nodes] == [
        ViewStatus.MISSING,
        ViewStatus.PROVEN,
        ViewStatus.PROVEN,
    ]
    assert result.edges[0].status is ViewStatus.PROVEN
    assert ViewStatus.DECLARED not in {item.status for item in (*result.nodes, *result.edges)}
    assert "PASS" not in view_summary(result)


def test_a_requires_edge_is_declared_never_proven(changed: Observation, shop: Observation) -> None:
    edges = [_edge("COMP-APP", "COMP-STORE", kind="requires")]
    nodes = ["COMP-APP", "COMP-STORE"]
    declared = _check(changed, nodes=nodes, edges=edges)
    assert declared.edges[0].status is ViewStatus.DECLARED and declared.exit_code == 0
    assert declared.edges[0].evidence[0].record_id == "COMP-APP"
    assert _check(shop, nodes=nodes, edges=edges).edges[0].status is ViewStatus.MISSING


def test_component_edges_lift_observed_module_relationships(shop: Observation) -> None:
    nodes = ["COMP-CLI", "COMP-APP", "COMP-STORE"]
    result = _check(
        shop,
        nodes=nodes,
        edges=[_edge("COMP-CLI", "COMP-APP"), _edge("COMP-STORE", "COMP-CLI")],
        steps=[{"node": "COMP-CLI"}, {"node": "COMP-STORE", "kind": "imports"}],
    )
    assert [edge.status for edge in result.edges] == [ViewStatus.PROVEN, ViewStatus.MISSING]
    assert result.steps[1].status is ViewStatus.PROVEN
    assert result.steps[1].path[0].startswith("shop.cli")


def test_spec_references_must_be_listed_nodes(shop: Observation) -> None:
    with pytest.raises(ValueError, match="nodes"):
        parse_view_spec(_spec(shop, edges=[_edge("shop.cli.main", "shop.store")]))
    with pytest.raises(ValueError, match="first step"):
        parse_view_spec(_spec(shop, steps=[{"node": "shop.cli.main", "kind": "imports"}]))


def test_cli_view_check_prints_json_and_returns_the_exit_code(
    shop: Observation, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    packet = _snapshot(tmp_path / "cli")
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(packet)
    spec = tmp_path / "view.json"
    observation = _observation(packet)
    edges = [_edge("shop.render.text", "shop.model.entities")]
    spec.write_text(json.dumps(_spec(observation, edges=edges)))
    arguments = ["view", "check", str(spec), "--snapshot", str(snapshot), "--json"]
    assert main(arguments) == 0
    expected = check_view(parse_view_spec(json.loads(spec.read_text())), observation, strict=False)
    assert capsys.readouterr().out == view_check_json(expected)
    spec.write_text(
        json.dumps(_spec(observation, edges=[_edge("shop.render.text", "shop.cli.main")]))
    )
    assert main(arguments) == 1
    capsys.readouterr()
    spec.write_text("{}")
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["command"] == "view"


def test_a_type_only_import_is_proven_and_labelled(changed: Observation) -> None:
    nodes = ["shop.render.hints", "shop.model.entities", "shop.render.text"]
    edges = [_edge(*nodes[:2]), _edge(nodes[2], nodes[1])]
    result = _check(changed, nodes=nodes, edges=edges)
    hint, text = result.edges
    assert hint.status is ViewStatus.PROVEN and all(site.type_only for site in hint.evidence)
    assert hint.reason.endswith("type-only import: not executed at runtime")
    assert text.status is ViewStatus.PROVEN and "type-only" not in text.reason


def test_the_result_matches_its_schema(shop: Observation) -> None:
    from jsonschema import Draft202012Validator

    raw = json.loads(EXAMPLE.read_text())
    result = check_view(parse_view_spec(raw), shop, strict=False)
    schema = json.loads((ROOT / "schema/view-check.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(view_check_json(result))))


def _tampered(packet: bytes) -> str:
    """Add a fabricated render.text -> store import whose evidence is not in the snapshot."""
    raw = json.loads(packet)
    fields = raw["encoding"]["section_data_fields"]["imports"]
    record = json.loads(json.dumps(raw["imports"][0]))
    record[0], record[6] = "IMP-00000000deadbeef", ["EVD-00000000deadbeef"]
    for name, value in (("source_module", "shop.render.text"), ("target_module", "shop.store")):
        record[10][fields.index(name)] = value
    raw["imports"].append(record)
    return json.dumps(raw)


def test_a_tampered_snapshot_is_not_checked(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    packet = _snapshot(tmp_path / "tampered")
    snapshot, spec = tmp_path / "architecture.json", tmp_path / "view.json"
    snapshot.write_text(_tampered(packet))
    nodes = ["shop.render.text", "shop.store"]
    edges = [_edge(*nodes)]
    spec.write_text(json.dumps(_spec(_observation(packet), nodes=nodes, edges=edges)))
    assert main(["view", "check", str(spec), "--snapshot", str(snapshot), "--json"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["command"] == "view" and "missing evidence" in out["diagnostics"][0]["unknown_claim"]
