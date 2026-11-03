# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-284: a view spec is checked data; each reference is proven, declared, claim or unknown."""

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.model import Observation, Section, Verdict
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
_SUBMODULE = (
    '"""Import a submodule through its package."""\n\n'
    "from shop.store import repository\n\n\n"
    "def load() -> object:\n"
    "    return repository.OrderRepository\n"
)
_LOADER = (
    '"""Load a renderer by a name known only at run time."""\n\n'
    "import importlib\n\n\n"
    "def load(name: str) -> object:\n"
    '    return importlib.import_module(f"shop.{name}")\n'
)


def _snapshot(
    tmp_path: Path, overlay: dict[str, str | None] | None = None, *, complete: bool = True
) -> bytes:
    root = _prepare_repo(tmp_path, overlay or {})
    result, packet = run_report(root, config=load_config(root), analyzer=observe)
    assert result.exit_code == (0 if complete else 2) and packet is not None
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
    """The shop with a dynamic loader, a type-only import, a submodule import and a requires."""
    contract = json.loads((ROOT / "fixtures/F-architecture/architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["id"] == "COMP-APP")
    app["requires"] = [{"component": "store", "rationale": "Use cases persist orders."}]
    header = (ROOT / "fixtures/F-architecture/shop/render/text.py").read_text().split('"""')[0]
    overlay = {
        "shop/render/loader.py": header + _LOADER,
        "shop/render/hints.py": header + _HINTS,
        "shop/app/p_ext.py": header + _SUBMODULE,
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


def test_a_step_is_proven_only_by_one_direct_edge(shop: Observation) -> None:
    nodes = ["shop.cli.main", "shop.app.orders", "shop.store.repository"]
    steps = [{"node": nodes[0]}, {"node": nodes[2], "kind": "imports"}]
    far = _check(shop, nodes=nodes, steps=steps).steps[1]
    # cli.main reaches repository only through app.orders and shop.store: a path is no step.
    assert far.status is ViewStatus.MISSING and "no direct imports edge" in far.reason
    assert far.evidence == () and far.path == ()
    steps = [{"node": nodes[0]}, {"node": nodes[1], "kind": "imports"}]
    near = _check(shop, nodes=nodes, steps=steps).steps[1]
    assert near.status is ViewStatus.PROVEN and near.path == ("shop.cli.main", "shop.app.orders")
    result = _check(shop, nodes=nodes, steps=steps)
    assert any("structure, not runtime order" in item for item in result.limits)
    # The same pair as one direct call is not an observed edge.
    call = _check(shop, nodes=nodes, edges=[_edge(nodes[0], nodes[2], kind="calls")])
    assert call.edges[0].status is ViewStatus.UNKNOWN


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


def test_a_contract_stripped_of_declarations_has_no_declared_status(shop: Observation) -> None:
    """Not the explore snapshot: its layout contract needs a typed marker first (AD-284)."""
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
    # The clean shop declares no requires at all: an absent requires is not decided.
    assert _check(shop, nodes=nodes, edges=edges).edges[0].status is ViewStatus.UNKNOWN
    reverse = [_edge("COMP-STORE", "COMP-APP", kind="requires")]
    assert _check(changed, nodes=nodes, edges=reverse).edges[0].status is ViewStatus.MISSING
    module_end = [_edge("shop.app.orders", "COMP-STORE", kind="requires")]
    unsupported = _check(changed, nodes=["shop.app.orders", "COMP-STORE"], edges=module_end)
    assert unsupported.edges[0].status is ViewStatus.UNKNOWN


def test_component_edges_lift_observed_module_relationships(shop: Observation) -> None:
    nodes = ["COMP-CLI", "COMP-APP", "COMP-STORE"]
    result = _check(
        shop,
        nodes=nodes,
        edges=[_edge("COMP-CLI", "COMP-APP"), _edge("COMP-STORE", "COMP-CLI")],
        steps=[{"node": "COMP-CLI"}, {"node": "COMP-APP", "kind": "imports"}],
    )
    assert [edge.status for edge in result.edges] == [ViewStatus.PROVEN, ViewStatus.MISSING]
    assert result.steps[1].status is ViewStatus.PROVEN
    assert result.steps[1].path == ("shop.cli.main", "shop.app.orders")


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


def test_a_module_the_snapshot_could_not_parse_is_unknown_not_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A coverage failure skips the module: its absence is not proven."""
    packet = _snapshot(
        tmp_path / "broken", {"shop/app/broken.py": "def broken(:\n"}, complete=False
    )
    snapshot, spec = tmp_path / "architecture.json", tmp_path / "view.json"
    snapshot.write_bytes(packet)
    nodes = ["shop.app.broken", "shop.app.payments", "shop.render.text", "shop.model.entities"]
    nodes.append("shop.app.orders")
    edges = [
        _edge(nodes[0], nodes[3]),  # an end node is unknown
        _edge(nodes[2], nodes[1]),
        _edge(nodes[2], nodes[4]),  # absent, but the coverage cannot exclude it
        _edge(nodes[2], nodes[3]),  # present: an observed edge stays proven
    ]
    spec.write_text(json.dumps(_spec(_observation(packet), nodes=nodes, edges=edges)))
    arguments = ["view", "check", str(spec), "--snapshot", str(snapshot), "--json"]
    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    statuses = [node["status"] for node in result["nodes"]]
    assert statuses == ["unknown", "unknown", "proven", "proven", "proven"]
    assert "incomplete source coverage" in result["nodes"][0]["reason"]
    assert [edge["status"] for edge in result["edges"]] == ["unknown"] * 3 + ["proven"]
    assert main([*arguments, "--strict"]) == 1


def test_an_unsupported_or_unscanned_id_is_unknown_not_missing(shop: Observation) -> None:
    nodes = [
        "shop.store.repository.OrderRepository",  # a symbol: the snapshot has it
        "shop/app/orders.py",  # a path, not a module name
        "tests.test_shop",  # outside the scanned roots
        "shop.app.payments",  # in the scanned roots, and absent
    ]
    result = _check(shop, nodes=nodes)
    assert [node.status for node in result.nodes] == [ViewStatus.UNKNOWN] * 3 + [ViewStatus.MISSING]
    assert "symbol" in result.nodes[0].reason
    package = _check(shop, nodes=["shop.render"]).nodes[0]
    assert package.status is ViewStatus.UNKNOWN and package.reason.startswith("a package")
    assert all("shop/**/*.py" in node.reason for node in result.nodes[1:])


def test_an_import_of_a_submodule_does_not_prove_the_package_absent(changed: Observation) -> None:
    nodes = ["shop.app.p_ext", "shop.store", "shop.store.repository"]
    edges = [_edge(nodes[0], nodes[1]), _edge(nodes[0], nodes[2])]
    result = _check(changed, nodes=nodes, edges=edges)
    assert [edge.status for edge in result.edges] == [ViewStatus.UNKNOWN, ViewStatus.PROVEN]
    assert "submodule" in result.edges[0].reason


def test_a_snapshot_error_names_the_snapshot_and_no_report_panel(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "view.json"
    spec.write_text(EXAMPLE.read_text())
    missing = tmp_path / "absent.json"
    assert main(["view", "check", str(spec), "--snapshot", str(missing), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == str(missing)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    spec.write_text("{}")
    assert main(["view", "check", str(spec), "--snapshot", str(missing)]) == 2
    shown = capsys.readouterr()
    assert "Scan complete" not in shown.out + shown.err and "view spec" in shown.out + shown.err
    assert str(spec) in shown.out


def test_an_invented_step_is_missing_unless_the_snapshot_has_a_gap(
    shop: Observation, changed: Observation
) -> None:
    nodes = ["shop.store.codec", "shop.render.text"]
    steps = [{"node": nodes[0]}, {"node": nodes[1], "kind": "imports"}]
    invented = _check(shop, nodes=nodes, steps=steps)
    assert invented.steps[1].status is ViewStatus.MISSING and invented.exit_code == 1
    incomplete = replace(shop, coverage=replace(shop.coverage, status=Verdict.FAIL))
    assert _check(incomplete, nodes=nodes, steps=steps).steps[1].status is ViewStatus.UNKNOWN
    loader = ["shop.render.loader", "shop.render.text"]
    dynamic = [{"node": loader[0]}, {"node": loader[1], "kind": "imports"}]
    gap = _check(changed, nodes=loader, steps=dynamic).steps[1]
    assert gap.status is ViewStatus.UNKNOWN and "dynamic" in gap.reason


# ---------- AD-289: a tour stop is author text beside facts measured from the snapshot ----------
TOUR = ROOT / "fixtures/F-architecture-view/first-contact-tour.json"


def _tour(observation: Observation, stops: list[dict], nodes: list[str]):
    raw = _spec(observation, schema_version="1.1.0", nodes=nodes, stops=stops)
    return check_view(parse_view_spec(raw), observation, strict=False)


def _oracle(observation: Observation, inside: set[str]) -> tuple[set, set]:
    """Count from the raw import records, not through the code under test."""
    modules = {record.title for record in observation.records("modules") or ()}
    pairs = {
        (str(record.data.get("source_module")), str(record.data.get("target_module")))
        for record in observation.records("imports") or ()
    }
    pairs = {(source, target) for source, target in pairs if target in modules}
    out = {pair for pair in pairs if pair[0] in inside and pair[1] not in inside}
    into = {pair for pair in pairs if pair[1] in inside and pair[0] not in inside}
    return out, into


def test_a_stop_on_a_module_carries_measured_facts_with_ids(shop: Observation) -> None:
    stop = {"node": "shop.app.orders", "title": "Place an order", "note": "Read this first."}
    (result,) = _tour(shop, [stop], ["shop.app.orders"]).stops
    assert (result.node, result.status, result.title, result.note) == (
        "shop.app.orders",
        ViewStatus.PROVEN,
        "Place an order",
        "Read this first.",
    )
    facts = result.facts
    assert facts is not None and facts.modules == 1
    out, into = _oracle(shop, {"shop.app.orders"})
    assert {(site.source, site.target) for site in facts.imports_out.evidence} == out
    assert {(site.source, site.target) for site in facts.imports_in.evidence} == into
    assert (facts.imports_out.pairs, facts.imports_in.pairs) == (len(out), len(into))
    assert all(
        site.record_id.startswith("IMP-") and site.evidence_id and site.line
        for site in (*facts.imports_out.evidence, *facts.imports_in.evidence)
    )
    # The snapshot records an unknown with this module as a subject.
    assert "boundary_type_position" in {finding.kind for finding in facts.unknowns}
    assert all(finding.record_id.startswith("UNKNOWN-") for finding in facts.unknowns)
    assert facts.violations == ()


def test_a_stop_on_a_component_counts_its_modules_and_its_boundary(shop: Observation) -> None:
    (result,) = _tour(shop, [{"node": "COMP-APP"}], ["COMP-APP"]).stops
    assert result.status is ViewStatus.DECLARED and result.facts is not None
    modules = {
        record.title
        for record in shop.records("modules") or ()
        if record.title.startswith("shop.app.")
    }
    assert result.facts.modules == len(modules)
    out, into = _oracle(shop, modules)
    assert {(site.source, site.target) for site in result.facts.imports_out.evidence} == out
    assert {(site.source, site.target) for site in result.facts.imports_in.evidence} == into
    assert result.facts.imports_out.pairs == len(out) > 0


def test_a_stop_on_an_unknown_or_missing_node_has_no_facts(shop: Observation) -> None:
    nodes = ["shop.render", "shop.app.payments"]
    result = _tour(shop, [{"node": node} for node in nodes], nodes)
    assert [(stop.status, stop.facts) for stop in result.stops] == [
        (ViewStatus.UNKNOWN, None),
        (ViewStatus.MISSING, None),
    ]
    assert result.stops[0].reason == result.nodes[0].reason
    assert result.exit_code == 1


def test_a_stop_counts_are_a_lower_bound_under_an_import_gap(changed: Observation) -> None:
    nodes = ["shop.render.loader", "shop.model.entities"]
    loader, entities = _tour(changed, [{"node": node} for node in nodes], nodes).stops
    assert loader.facts is not None and entities.facts is not None
    assert "dynamic" in (loader.facts.imports_out.gap or "")
    assert "dynamic_import_limit" in {finding.kind for finding in loader.facts.unknowns}
    # The loader can import any module, so each other module's imports in are a lower bound.
    assert loader.facts.imports_in.gap is None
    assert "shop.render.loader has a dynamic import" in (entities.facts.imports_in.gap or "")
    assert entities.facts.imports_out.gap is None


def test_a_stop_lists_the_violations_that_touch_its_module(tmp_path: Path) -> None:
    from fixtures.demo_catalog_dependencies import _FORBIDDEN_DEPENDENCY_PAIR

    root = _prepare_repo(tmp_path, dict(_FORBIDDEN_DEPENDENCY_PAIR.files))
    _, packet = run_report(root, config=load_config(root), analyzer=observe)
    assert packet is not None
    observation = _observation(packet)
    nodes = ["shop.render.text", "shop.cli.main"]
    text, cli = _tour(observation, [{"node": node} for node in nodes], nodes).stops
    assert text.facts is not None and cli.facts is not None
    assert [(item.kind, item.record_id[:4]) for item in text.facts.violations] == [
        ("forbidden_dependency", "VIO-")
    ]
    assert cli.facts.violations == ()


def test_a_stale_snapshot_gives_a_stop_no_facts(shop: Observation) -> None:
    spec = _spec(shop, schema_version="1.1.0", stops=[{"node": "shop.cli.main"}])
    spec["snapshot"] = {"source_digest": "0" * 64, "contract_digest": "0" * 64}
    (stop,) = check_view(parse_view_spec(spec), shop, strict=False).stops
    assert stop.status is ViewStatus.UNKNOWN and stop.facts is None


@pytest.mark.parametrize(
    "styled",
    [{"kind": "imports"}, {"claim": True}, {"status": "proven"}, {"facts": {"modules": 1}}],
)
def test_a_stop_that_states_a_relation_or_proof_is_rejected(
    shop: Observation, styled: dict
) -> None:
    spec = _spec(shop, schema_version="1.1.0", stops=[{"node": "shop.cli.main", **styled}])
    with pytest.raises(ValueError):
        parse_view_spec(spec)


def test_a_stop_names_a_listed_node_and_needs_version_1_1_0(shop: Observation) -> None:
    with pytest.raises(ValueError, match="nodes"):
        parse_view_spec(_spec(shop, schema_version="1.1.0", stops=[{"node": "shop.store"}]))
    with pytest.raises(ValueError, match="1.1.0"):
        parse_view_spec(_spec(shop, stops=[{"node": "shop.cli.main"}]))


def test_a_spec_without_stops_keeps_its_result(shop: Observation) -> None:
    raw = json.loads(EXAMPLE.read_text())
    old = check_view(parse_view_spec(raw), shop, strict=False)
    new = check_view(parse_view_spec({**raw, "schema_version": "1.1.0"}), shop, strict=False)
    assert old.stops == () and replace(new, schema_version=old.schema_version) == old
    assert json.loads(view_check_json(old))["stops"] == []


def test_the_tour_example_checks_clean_and_matches_its_schema(shop: Observation) -> None:
    from jsonschema import Draft202012Validator

    raw = json.loads(TOUR.read_text())
    assert raw["snapshot"] == asdict(snapshot_identity(shop))
    result = check_view(parse_view_spec(raw), shop, strict=False)
    assert result.exit_code == 0 and len(result.stops) >= 4
    assert all(stop.facts is not None for stop in result.stops)
    schema = json.loads((ROOT / "schema/view-check.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(view_check_json(result))))
