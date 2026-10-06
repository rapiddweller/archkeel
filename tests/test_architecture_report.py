# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One report boundary retains independent graphs and verified Core receipts."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_target_graph import _nested_repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    GraphComparison,
)
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.graph_codec import parse_report, report_bytes
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.render.html import render_html
from tools.architecture_graph_schema import report_schema


def test_report_standard_retains_independent_graphs_and_core_comparison(tmp_path):
    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    target = next(item for item in model.records("declarations") if item.kind == "uml_target")
    assert report.observed == observed_graph(model)
    assert report.target == recorded_target_graph(model, target)
    assert report.comparison is not None
    wire = json.loads(report_bytes(report))
    Draft202012Validator(report_schema()).validate(wire)
    assert parse_report(wire) == report
    assert report_schema() == json.loads(
        Path("schema/architecture-report.schema.json").read_bytes()
    )


def test_browser_receives_only_the_standard_report(tmp_path):
    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    page = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    start = page.index(">", page.index('id="flow-data"')) + 1
    wire = json.loads(page[start : page.index("</script>", start)])
    expected = json.loads(report_bytes(architecture_report(model)))
    for side in ("observed", "target"):
        for collection in ("entities", "relationships"):
            for item in expected[side][collection]:
                del item["record_ids"]
    assert wire == expected
    assert parse_report(wire) == parse_report(expected)
    assert not {"components", "modules", "explorers", "uml"}.intersection(wire)


def test_report_rejects_swapped_origins_and_comparison_without_source():
    with pytest.raises(ValueError, match="observed origin"):
        ArchitectureReport(ArchitectureGraph("declared"), None).validate()
    with pytest.raises(ValueError, match="declared origin"):
        ArchitectureReport(ArchitectureGraph("observed"), ArchitectureGraph("observed")).validate()
    with pytest.raises(ValueError, match="reason"):
        ArchitectureReport(None, None).validate()
    with pytest.raises(ValueError, match="both source and Target"):
        ArchitectureReport(
            None, None, GraphComparison("UNKNOWN"), unavailable="Source facts are absent."
        ).validate()


@pytest.mark.parametrize(
    "change",
    [
        "target",
        "source",
        "evidence",
        "field",
        "membership",
        "finding",
        "duplicate_membership",
        "gap",
    ],
)
def test_report_rejects_dangling_core_references_and_unknown_fields(tmp_path, change):
    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert report.comparison is not None and report.comparison.assessments
    wire = json.loads(report_bytes(report))
    if change == "field":
        wire["components"] = []
    elif change == "finding":
        wire["findings"][0]["evidence_ids"] = ["missing-proof"]
    elif change == "duplicate_membership":
        membership = next(item for item in wire["memberships"] if item["module_ids"])
        membership["module_ids"] *= 2
    elif change == "gap":
        wire["decision_gaps"] = [
            {"source_id": "missing", "target_id": "missing", "relationship_ids": []}
        ]
    elif change == "membership":
        wire["memberships"][0]["module_ids"] = ["missing-module"]
    else:
        assessment = wire["comparison"]["assessments"][0]
        assessment[
            {"target": "subject_id", "source": "observed_ids", "evidence": "evidence_ids"}[change]
        ] = "missing-target" if change == "target" else ["missing-reference"]
    with pytest.raises(ValueError):
        parse_report(wire)


def test_report_preserves_core_failures_unknowns_and_navigation_without_copying_source(tmp_path):
    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    expected = {(item.id, "FAIL") for item in model.records("violations") or ()} | {
        (item.id, "UNKNOWN") for item in model.records("unknowns") or ()
    }
    assert {(item.id, item.status) for item in report.findings} == expected
    assert report.memberships
    assert report.observed == observed_graph(model)
    assert all(item.kind != "component" for item in report.observed.entities)
    assert report.target is not None and report.target.origin == "declared"
    report.validate()
    assert not result.diagnostics


def test_module_source_path_is_not_invented_for_referenced_endpoints(tmp_path):
    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    graph = observed_graph(model)
    modules = [
        item for item in graph.entities if item.kind == "module" and item.presence == "defined"
    ]
    assert modules and all(item.file_path for item in modules)
    assert all(item.file_path is None for item in graph.entities if item.presence == "referenced")
    invalid = replace(
        graph,
        entities=tuple(
            replace(item, file_path="../outside.py") if item is modules[0] else item
            for item in graph.entities
        ),
    )
    with pytest.raises(ValueError, match="file path"):
        invalid.validate()


def test_report_keeps_external_permissions_as_independent_typed_intent(tmp_path):
    from test_architecture_demo import CONFIG, _prepare_repo

    from archkeel.ir.codec import parse_contract
    from archkeel.ir.model import ExternalDependencyScopeRule
    from fixtures.architecture_demo import CATALOG

    sample = next(item for item in CATALOG if item.id == "class-a-external-dependency-scope")
    root = _prepare_repo(tmp_path, dict(sample.files))
    _, encoded = run_report(root, config=CONFIG, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    contract = parse_contract(json.loads((root / CONFIG.contract).read_bytes()))
    expected = tuple(
        rule for rule in contract.rules if isinstance(rule, ExternalDependencyScopeRule)
    )
    assert expected and report.target is not None
    assert report.target.external_scopes == expected
    assert parse_report(json.loads(report_bytes(report))) == report
    assert any(
        "EXTERNAL-JSON-STORE" in item.rule_ids and item.status == "FAIL" for item in report.findings
    )


@pytest.mark.parametrize(
    "field", ["dependency", "allowed_sources", "exact_sources", "rationale", "decided_by"]
)
def test_core_rejects_forged_external_permission_before_report_projection(tmp_path, field):
    from test_architecture_demo import CONFIG, _prepare_repo

    from archkeel.check.uml import assemble_uml
    from archkeel.ir.model import RecordData
    from fixtures.architecture_demo import CATALOG

    sample = next(item for item in CATALOG if item.id == "class-a-external-dependency-scope")
    root = _prepare_repo(tmp_path, dict(sample.files))
    original = observe(
        root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = original.observation
    assert model is not None and not original.diagnostics
    invalid = {
        "dependency": "invented",
        "allowed_sources": ("shop.app",),
        "exact_sources": ("shop.app",),
        "rationale": "Invented permission.",
        "decided_by": "agent",
    }
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    record,
                    data=RecordData(
                        tuple((key, value) for key, value in record.data.entries if key != field)
                        + ((field, invalid[field]),)
                    ),
                )
                if record.id == "EXTERNAL-JSON-STORE"
                else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(model, sections=sections)), root, CONFIG.contract
    )
    assert result.diagnostics
    assert "authenticated contract" in result.diagnostics[0].unknown_claim


def test_report_retains_open_dependency_decisions_without_inventing_core_unknowns(tmp_path):
    from test_architecture_demo import CONFIG, _prepare_repo

    from fixtures.architecture_demo import CATALOG
    from fixtures.demo_catalog_support import contract_without_rule

    sample = next(item for item in CATALOG if item.id == "tour")
    root = _prepare_repo(
        tmp_path,
        {
            **dict(sample.files),
            "architecture-contract.json": contract_without_rule("DEP-APP-ALLOWS-MODEL"),
        },
    )
    _, encoded = run_report(root, config=CONFIG, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    names = {item.component_id: item.label for item in report.target.component_intents}
    gap = next(
        item
        for item in report.decision_gaps
        if names[item.source_id] == "app" and names[item.target_id] == "model"
    )
    assert gap.relationship_ids
    assert {item.id for item in report.findings} == {
        item.id for section in ("violations", "unknowns") for item in model.records(section) or ()
    }
    assert parse_report(json.loads(report_bytes(report))) == report


@pytest.mark.parametrize("level", ["root", "inside"])
def test_external_permissions_authenticate_and_roundtrip_at_each_contract_level(tmp_path, level):
    from archkeel.ir.codec import load_inside_contract_tree, parse_contract
    from archkeel.ir.target_graph import declared_tree_graph

    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    path = config.contract if level == "root" else "inside.json"
    raw = json.loads((root / path).read_bytes())
    raw["rules"].append(
        dict(
            id="EXT",
            kind="external_dependency_scope",
            dependency="json",
            allowed_sources=["sample.core"],
            exact_sources=["sample.core"],
            rationale="Keep JSON use in the declared boundary.",
            provenance=["docs/target.md"],
            decided_by="architect",
        )
    )
    (root / path).write_text(json.dumps(raw))
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    import hashlib

    content = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(content)),
        hashlib.sha256(content).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    expected = declared_tree_graph(tree, root_path=config.contract)
    assert report.target == expected
    assert len(report.target.external_scopes) == 1
    assert parse_report(json.loads(report_bytes(report))) == report


def test_source_failure_keeps_independent_target_and_original_diagnostic(tmp_path):
    from archkeel.check.uml import assemble_uml
    from archkeel.ir.model import Diagnostic

    root, config = _nested_repository(tmp_path, root_version="2.2.0")
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None and not original.diagnostics
    failure = Diagnostic(
        "parse_error", "sample/core.py", "Source is incomplete.", "Repair the source."
    )
    compiled = assemble_uml(replace(original, diagnostics=(failure,)), root, config.contract)
    assert compiled.diagnostics == (failure,)
    report = architecture_report(compiled.observation)
    assert report.target is not None
    assert report.comparison is None
    assert report.target.origin == "declared"
    # Source failure cannot bypass declaration authentication.
    payload = json.loads((root / config.contract).read_bytes())
    payload["components"][0]["responsibilities"] = ["Different intent."]
    (root / config.contract).write_text(json.dumps(payload))
    rejected = assemble_uml(replace(original, diagnostics=(failure,)), root, config.contract)
    assert rejected.diagnostics[0] == failure and len(rejected.diagnostics) == 2
    assert architecture_report(rejected.observation).target is None
