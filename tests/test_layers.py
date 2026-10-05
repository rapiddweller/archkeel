# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Layer intent is authenticated; order assesses declared permissions, not imports."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_target_graph import _contract, _nested_repository, _repository

from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport
from archkeel.ir.codec import (
    contract_bytes,
    contract_digest,
    decode_canonical_model,
    load_inside_contract_tree,
    parse_contract,
    parse_observation,
)
from archkeel.ir.graph_codec import graph_bytes, parse_graph, parse_report, report_bytes
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.ir.widening import contract_widenings
from tools.architecture_graph_schema import graph_schema, report_schema

CONTRACT_SCHEMA = json.loads(
    (Path(__file__).parents[1] / "schema/architecture-contract.schema.json").read_bytes()
)


@pytest.mark.parametrize(
    "version,digest,graph_digest",
    [
        (
            "2.1.0",
            "5b9fb2a096c040b6e88c65411c1b3502d0a04ce6d20f4a3884b22406ea2b61c9",
            "7feb98a0546c1a9422a0a1ef2d31a58d36bbed70e0c618532294796c6d3072f1",
        ),
        (
            "2.2.0",
            "e4f6749bfd406ea0e932770f82a6b03268cabd1e6073e1d13089ed941db8e0fb",
            "8307972478bdd30353c206942027672706bf3479e5cb8544a8d1cf6f84ec7704",
        ),
    ],
)
def test_absent_layer_keeps_old_canonical_bytes(version, digest, graph_digest):
    raw = _contract()
    raw["schema_version"] = version
    if version == "2.1.0":
        raw.pop("declarations")
    contract = parse_contract(raw)
    assert contract_digest(contract) == digest
    legacy_graph = replace(declared_graph(contract), schema_version="1.0.0")
    assert sha256(graph_bytes(legacy_graph)).hexdigest() == graph_digest
    assert b'"layer"' not in contract_bytes(contract)
    assert b'"layer"' not in graph_bytes(legacy_graph)


@pytest.mark.parametrize("value", ["", "  ", None, 12, []])
def test_invalid_layer_is_rejected(value):
    raw = _contract()
    raw["schema_version"] = "2.3.0"
    raw["components"][0]["layer"] = value
    with pytest.raises(ValueError, match="layer"):
        parse_contract(raw)
    assert not Draft202012Validator(CONTRACT_SCHEMA).is_valid(raw)


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_old_contract_rejects_layer(version):
    raw = _contract()
    raw.pop("declarations")
    raw["schema_version"] = version
    raw["components"][0]["layer"] = "Core"
    with pytest.raises(ValueError, match="layer"):
        parse_contract(raw)
    assert not Draft202012Validator(CONTRACT_SCHEMA).is_valid(raw)


@pytest.mark.parametrize("nested", [False, True])
def test_layer_compiler_matches_authenticated_projection(tmp_path, nested):
    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json") if nested else (config.contract,):
        raw = json.loads((root / path).read_bytes())
        raw["schema_version"] = "2.3.0"
        raw["components"][0]["layer"] = "Core"
        (root / path).write_text(json.dumps(raw))
    data = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(data)),
        sha256(data).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    independent = declared_tree_graph(tree, root_path=config.contract)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        record for record in model.records("declarations") if record.kind == "uml_target"
    )
    assert recorded_target_graph(model, declaration) == independent
    assert all(intent.layer == "Core" for intent in independent.component_intents)
    assert independent.schema_version == "1.2.0"
    encoded = json.loads(graph_bytes(independent))
    assert parse_graph(encoded) == independent
    assert Draft202012Validator(graph_schema()).is_valid(encoded)
    encoded["schema_version"] = "1.0.0"
    with pytest.raises(ValueError, match="layer"):
        parse_graph(encoded)
    assert not Draft202012Validator(graph_schema()).is_valid(encoded)
    report = architecture_report(model)
    assert report.schema_version == "1.2.0"
    assert parse_report(json.loads(report_bytes(report))) == report
    assert Draft202012Validator(report_schema()).is_valid(json.loads(report_bytes(report)))


@pytest.mark.parametrize("nested", [False, True])
def test_forged_layer_is_rejected(tmp_path, nested):
    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    owner = next(
        record
        for record in original.observation.records("declarations")
        if record.kind
        == ("inside_component_responsibility" if nested else "component_responsibility")
    )
    forged = replace(
        owner,
        data=replace(
            owner.data, entries=tuple({**dict(owner.data.entries), "layer": "Fake"}.items())
        ),
    )
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == owner.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics


def _layer_contract(source="Core", target="Edge", required=True):
    raw = _contract()
    raw.pop("declarations")
    raw["schema_version"] = "2.3.0"
    core = raw["components"][0]
    if source is not None:
        core["layer"] = source
    core["requires"] = (
        [{"component": "peer", "rationale": "Use the peer boundary."}] if required else []
    )
    raw["components"].append(
        {
            **core,
            "id": "peer",
            "label": "peer",
            "packages": ["sample.peer"],
            "namespace": "sample.peer",
            "requires": [],
            "layer": target,
        }
    )
    raw["rules"] = [
        {
            "id": "LAYERS",
            "kind": "layer_order",
            "layers": ["Core", "Edge"],
            "rationale": "Core cannot require an outer layer.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    return raw


@pytest.mark.parametrize(
    "source,target,required,expected",
    [
        ("Core", "Edge", True, "FAIL"),
        ("Edge", "Core", True, "PASS"),
        ("Core", "Core", True, "PASS"),
        ("Core", "Edge", False, "PASS"),
        (None, "Edge", False, "UNKNOWN"),
        ("Other", "Edge", False, "UNKNOWN"),
        ("Core", "Other", True, "UNKNOWN"),
    ],
)
def test_layer_order_declared_permissions_without_imports(
    tmp_path, source, target, required, expected
):
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_layer_contract(source, target, required)))
    result, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert result.declared_rules == expected
    row = next(row for row in result.rule_assessments if row.id == "LAYERS")
    assert row.status == expected and row.rationale == "Core cannot require an outer layer."
    assert not model.records("imports")
    if expected == "PASS":
        assert "declared requires" in row.reason.lower()
    if expected == "FAIL":
        violation = next(item for item in model.records("violations") if "LAYERS" in item.rule_ids)
        assert violation.kind == "layer_order"
        assert violation.data.get("source_layer") == "Core"
        assert violation.data.get("target_layer") == "Edge"
        assert violation.evidence_ids
        assert {item.file for item in model.evidence if item.id in violation.evidence_ids} == {
            config.contract
        }


def test_layer_order_inside_has_local_permissions(tmp_path):
    root, config = _nested_repository(tmp_path)
    (root / "leaf.json").write_text(json.dumps(_layer_contract()))
    result, _ = run_report(root, config=config, analyzer=observe)
    row = next(row for row in result.rule_assessments if row.kind == "layer_order")
    assert row.status == "FAIL" and row.scope != "root"


def test_layer_and_order_changes_require_policy_review():
    assert Draft202012Validator(CONTRACT_SCHEMA).is_valid(_layer_contract())
    before = parse_contract(_layer_contract())
    raw = _layer_contract("Edge", "Core")
    after = parse_contract(raw)
    assert any(".layer changed" in item for item in contract_widenings(before, after))
    raw = _layer_contract()
    raw["rules"][0]["layers"].reverse()
    assert contract_widenings(before, parse_contract(raw))


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_old_contract_rejects_layer_order(version):
    raw = _layer_contract()
    raw["schema_version"] = version
    for component in raw["components"]:
        component.pop("layer")
    with pytest.raises(ValueError, match="layer_order"):
        parse_contract(raw)
    assert not Draft202012Validator(CONTRACT_SCHEMA).is_valid(raw)


@pytest.mark.parametrize("layers", [[], ["Core", "Core"], [""], [3]])
def test_invalid_order_is_rejected(layers):
    raw = _layer_contract()
    raw["rules"][0]["layers"] = layers
    with pytest.raises(ValueError, match="layers"):
        parse_contract(raw)
    assert not Draft202012Validator(CONTRACT_SCHEMA).is_valid(raw)


def test_declared_layer_violation_has_an_authenticated_policy_trace(tmp_path):
    from archkeel.ir.trace import trace_valid_violations

    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_layer_contract()))
    result = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = result.observation
    violation = next(item for item in model.records("violations") if item.kind == "layer_order")
    assert violation in trace_valid_violations(model)
    assert violation.evidence_ids
    assert {item.file for item in model.evidence if item.id in violation.evidence_ids} == {
        config.contract
    }


@pytest.mark.parametrize("change", ["fact", "rule", "evidence"])
def test_declared_layer_trace_rejects_unbound_inputs(tmp_path, change):
    from archkeel.ir.trace import trace_valid_violations

    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_layer_contract()))
    result = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = result.observation
    violation = next(item for item in model.records("violations") if item.kind == "layer_order")
    records = {item.id: item for section in model.sections for item in section.records}
    if change == "evidence":
        original = records[violation.fact_ids[0]]
        forged = replace(original, evidence_ids=("missing",))
    else:
        original = violation
        forged = (
            replace(original, fact_ids=("missing",))
            if change == "fact"
            else replace(original, rule_ids=("missing",))
        )
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == original.id else item for item in section.records),
        )
        for section in model.sections
    )
    assert not trace_valid_violations(replace(model, sections=sections))


@pytest.mark.parametrize("change", ["missing", "changed"])
def test_layer_policy_with_unbound_contract_source_is_unknown(tmp_path, monkeypatch, change):
    from archkeel.check import observation

    root, config = _repository(tmp_path)
    path = root / config.contract
    path.write_text(json.dumps(_layer_contract()))
    evaluate = observation.evaluate_source

    def replace_contract_after_evaluation(*args, **kwargs):
        scan = evaluate(*args, **kwargs)
        if change == "missing":
            path.unlink()
        else:
            path.write_text("{}")
        return scan

    monkeypatch.setattr(observation, "evaluate_source", replace_contract_after_evaluation)
    result = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert result.observation is not None
    model = result.observation
    assert any(item.kind == "declaration_source_unavailable" for item in model.coverage.failures)
    assert not model.records("violations")
    receipt = next(
        item
        for item in model.records("scope_observations")
        if item.kind == "rule_evaluation" and "LAYERS" in item.rule_ids
    )
    assert receipt.data.get("assessment_complete") is False


def test_repeated_permissions_produce_one_layer_pair_violation(tmp_path):
    root, config = _repository(tmp_path)
    raw = _layer_contract()
    raw["components"][0]["requires"].append(
        {
            "component": "peer",
            "rationale": "Use another peer facade.",
            "through": ["sample.peer.Other"],
        }
    )
    (root / config.contract).write_text(json.dumps(raw))
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.declared_rules == "FAIL"
    row = next(row for row in result.rule_assessments if row.id == "LAYERS")
    assert row.count == 1


@pytest.mark.parametrize("components,expected", [(["peer"], "PASS"), (["core"], "UNKNOWN")])
def test_layer_order_component_selection_is_local(tmp_path, components, expected):
    root, config = _repository(tmp_path)
    raw = _layer_contract(source=None, required=False)
    raw["rules"][0]["components"] = components
    (root / config.contract).write_text(json.dumps(raw))
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.declared_rules == expected


def test_layer_order_rejects_undeclared_component_selection():
    raw = _layer_contract()
    raw["rules"][0]["components"] = ["unknown"]
    with pytest.raises(ValueError, match="components"):
        parse_contract(raw)


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_writer_rejects_layer_on_old_contract(version):
    contract = parse_contract(_layer_contract())
    with pytest.raises(ValueError, match="layer"):
        contract_bytes(replace(contract, schema_version=version))


def test_layer_diagnostic_describes_the_declared_permission(tmp_path):
    from archkeel.check.validation import observation_diagnostics

    root, config = _repository(tmp_path)
    raw = _layer_contract()
    (root / config.contract).write_text(json.dumps(raw))
    result = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    diagnostics = observation_diagnostics(parse_contract(raw), result.observation, ())
    diagnostic = next(item for item in diagnostics if item.code == "rule.violated")
    assert diagnostic.unknown_claim.startswith("The declared requires permission")
    assert "permission" in diagnostic.remedy


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_layer_absence_preserves_current_graph_and_report_versions(tmp_path, version):
    root, config = _repository(tmp_path)
    raw = _contract()
    raw["declarations"]["uml"]["schema_version"] = version
    (root / config.contract).write_text(json.dumps(raw))
    _, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert report.schema_version == "1.0.0"
    assert report.target.schema_version == version
    data = json.loads(report_bytes(report))
    assert parse_report(data) == report
    assert Draft202012Validator(report_schema()).is_valid(data)
    assert b'"layer"' not in graph_bytes(report.target)
    data["target"]["component_intents"][0]["layer"] = "Core"
    with pytest.raises(ValueError, match="layer"):
        parse_report(data)
    assert not Draft202012Validator(report_schema()).is_valid(data)


@pytest.mark.parametrize("nested", [False, True])
def test_layers_preserve_current_enum_target_and_source_proof(tmp_path, nested):
    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    path = root / ("leaf.json" if nested else config.contract)
    raw = json.loads(path.read_bytes())
    raw["schema_version"] = "2.3.0"
    raw["components"][0]["layer"] = "Core"
    target = raw["declarations"]["uml"]
    target["schema_version"] = "1.1.0"
    context = {"language": "python", "presence": "planned", "provenance": ["docs/target.md"]}
    target["entities"].extend(
        [
            {
                **context,
                "id": "state",
                "kind": "enum",
                "qualified_name": "sample.core.State",
                "parent_id": "core",
                "responsibilities": ["Name the request state."],
            },
            {
                **context,
                "id": "ready",
                "kind": "enum_literal",
                "qualified_name": "sample.core.State.READY",
                "parent_id": "state",
                "responsibilities": ["Name the ready state."],
            },
        ]
    )
    path.write_text(json.dumps(raw))
    source = root / "sample/core.py"
    source.write_text(
        source.read_text() + "\nfrom enum import Enum\nclass State(Enum):\n READY = 'ready'\n"
    )
    _, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert report.schema_version == report.target.schema_version == "1.2.0"
    assert report.observed.schema_version == "1.1.0"
    assert any(entity.kind == "enum_literal" for entity in report.observed.entities)
    assert any(entity.kind == "enum_literal" for entity in report.target.entities)
    graph = declared_graph(parse_contract(raw))
    assert any(entity.kind == "enum_literal" for entity in graph.entities)
    assert parse_report(json.loads(report_bytes(report))) == report
    assert Draft202012Validator(report_schema()).is_valid(json.loads(report_bytes(report)))


def test_old_report_rejects_layer_graph_even_without_component_metadata():
    report = ArchitectureReport(ArchitectureGraph("observed", schema_version="1.2.0"), None)
    with pytest.raises(ValueError, match="layer.*report"):
        report_bytes(report)


def test_own_target_retains_layer_and_report_version_intent():
    contract = parse_contract(
        json.loads((Path(__file__).parents[1] / "docs/architecture/contracts/ir.json").read_bytes())
    )
    entities = {item.qualified_name: item for item in contract.declarations.uml.entities}
    layer = entities["archkeel.ir.architecture_graph.ComponentIntent.layer"]
    assert layer.kind == "attribute" and layer.annotation == "str | None"
    assert entities[
        "archkeel.ir.architecture_graph.ArchitectureReport.schema_version"
    ].annotation == ("Literal['1.2.0', '1.0.0']")
