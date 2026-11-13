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
from test_target_graph import _contract

from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport
from archkeel.ir.codec import (
    contract_bytes,
    contract_digest,
    parse_contract,
)
from archkeel.ir.graph_codec import graph_bytes, report_bytes
from archkeel.ir.target_graph import declared_graph
from archkeel.ir.widening import contract_widenings

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
    assert (
        entities["archkeel.ir.architecture_graph.ArchitectureReport.schema_version"].annotation
        == "ReportSchemaVersion"
    )
    assert entities["archkeel.ir.architecture_graph.ReportSchemaVersion"].kind == "enum"
