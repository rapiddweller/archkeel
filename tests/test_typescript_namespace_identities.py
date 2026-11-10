# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript type/value namespaces preserve unique definitions and real collisions."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from collector_pin import trusted
from test_source_graph import _graph_from_source_facts
from test_typescript_inner import _collected
from test_typescript_partial_uml import _project, _TypeScriptCollector

from archkeel.check.report import run_report, run_saved_report
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    DefinitionContext,
    Entity,
    Relationship,
)
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.facts import Evidence
from archkeel.ir.report_graph import architecture_report

PROOF = Evidence("proof", "sample.ts", 1, 1, 0, "export type Shared = number;")


def _graphs(kinds, wanted_kind, *, language="typescript", complete=False):
    module = Entity(
        "module",
        "module",
        "sample",
        language,
        presence="defined",
        evidence_ids=("proof",),
        record_ids=("module",),
    )
    definitions = tuple(
        Entity(
            f"site-{index}",
            kind,
            "sample.Shared",
            language,
            parent_id="module",
            presence="defined",
            evidence_ids=("proof",),
            record_ids=(f"site-{index}",),
        )
        for index, kind in enumerate(kinds)
    )
    observed = ArchitectureGraph(
        "observed",
        (module, *definitions),
        evidence=(PROOF,),
        coverage=(
            Coverage(
                "module",
                (wanted_kind,),
                status="complete" if complete else "partial",
                reason=None if complete else "incomplete inventory",
            ),
        ),
    )
    target = ArchitectureGraph(
        "declared",
        (
            replace(
                module, presence="planned", evidence_ids=(), record_ids=(), provenance=("target",)
            ),
            Entity(
                "wanted",
                wanted_kind,
                "sample.Shared",
                language,
                parent_id="module",
                presence="planned",
                provenance=("target",),
            ),
        ),
    )
    return observed, target


def _wanted(comparison):
    return [item for item in comparison.assessments if item.subject_id == "wanted"]


@pytest.mark.parametrize(
    "kinds,wanted_kind,selected",
    [
        (("type_alias", "constant"), "type_alias", "site-0"),
        (("type_alias", "constant"), "constant", "site-1"),
        (("interface", "function"), "interface", "site-0"),
        (("interface", "function"), "function", "site-1"),
    ],
)
def test_unique_type_and_value_namespaces_keep_their_own_evidence(kinds, wanted_kind, selected):
    observed, target = _graphs(kinds, wanted_kind)
    comparison = compare_graphs(observed, target)
    assessments = _wanted(comparison)
    assert {item.status for item in assessments} == {"PASS"}
    assert all(
        item.observed_ids == (selected,) for item in assessments if item.aspect == "existence"
    )
    assert all(item.evidence_ids == ("proof",) for item in assessments)
    assert next(
        item.observed_ids for item in comparison.correspondences if item.target_id == "wanted"
    ) == (selected,)


@pytest.mark.parametrize(
    "kinds,wanted_kind",
    [
        (("type_alias", "type_alias", "constant"), "type_alias"),
        (("interface", "type_alias", "constant"), "type_alias"),
        (("constant", "constant", "type_alias"), "constant"),
        (("function", "constant", "type_alias"), "constant"),
        (("class", "type_alias"), "type_alias"),
        (("class", "interface"), "class"),
        (("class", "constant"), "constant"),
        (("enum", "type_alias"), "type_alias"),
        (("enum", "constant"), "constant"),
        (("enum", "constant"), "enum"),
        (("symbol", "type_alias"), "type_alias"),
    ],
)
def test_same_namespace_and_both_namespace_collisions_remain_unknown(kinds, wanted_kind):
    observed, target = _graphs(kinds, wanted_kind)
    assessments = _wanted(compare_graphs(observed, target))
    assert len(assessments) == 1
    assert assessments[0].status == "UNKNOWN" and assessments[0].change == "ambiguous"
    assert len(assessments[0].observed_ids) == 2


@pytest.mark.parametrize(
    "kinds,wanted_kind,selected",
    [
        (("interface", "constant", "function"), "type_alias", "site-0"),
        (("function", "interface", "type_alias"), "constant", "site-0"),
        (("function",), "class", "site-0"),
        (("constant",), "enum", "site-0"),
    ],
)
def test_unique_wrong_kind_in_requested_namespace_stays_fail(kinds, wanted_kind, selected):
    observed, target = _graphs(kinds, wanted_kind)
    result = _wanted(compare_graphs(observed, target))
    assert len(result) == 1
    assert (result[0].aspect, result[0].status, result[0].change) == ("kind", "FAIL", "changed")
    assert result[0].observed_ids == (selected,)


@pytest.mark.parametrize("complete,expected", [(False, "UNKNOWN"), (True, "FAIL")])
@pytest.mark.parametrize(
    "actual_kind,wanted_kind", [("constant", "type_alias"), ("type_alias", "constant")]
)
def test_opposite_namespace_alone_requires_inventory_proof_of_absence(
    complete, expected, actual_kind, wanted_kind
):
    observed, target = _graphs((actual_kind,), wanted_kind, complete=complete)
    result = _wanted(compare_graphs(observed, target))
    assert len(result) == 1
    assert result[0].aspect == "existence" and result[0].status == expected
    assert result[0].change == ("missing" if complete else "unavailable")


def test_unique_namespace_definition_does_not_resolve_reference_site_candidates():
    observed, target = _graphs(("type_alias", "constant"), "type_alias")
    observed = replace(
        observed,
        relationships=(
            Relationship(
                "reference",
                "references",
                "module",
                resolution="partial",
                candidate_ids=("site-0", "site-1"),
                expression="Shared",
                evidence_ids=("proof",),
                record_ids=("reference",),
            ),
        ),
    )
    target = replace(
        target,
        relationships=(
            Relationship(
                "wanted-reference", "references", "module", "wanted", provenance=("target",)
            ),
        ),
    )
    comparison = compare_graphs(observed, target)
    result = next(item for item in comparison.assessments if item.subject_id == "wanted-reference")
    assert (result.status, result.change, result.observed_ids) == (
        "UNKNOWN",
        "unavailable",
        ("reference",),
    )


def test_namespace_selection_does_not_prove_conditional_binding():
    observed, target = _graphs(("type_alias", "constant"), "type_alias")
    observed = replace(
        observed,
        entities=tuple(
            replace(entity, definition_contexts=(DefinitionContext("if", "body", ("proof",)),))
            if entity.id == "site-0"
            else entity
            for entity in observed.entities
        ),
    )
    result = _wanted(compare_graphs(observed, target))
    assert len(result) == 1
    assert (result[0].status, result[0].change) == ("UNKNOWN", "unavailable")


@pytest.mark.parametrize("language", ["python", "dart"])
def test_non_typescript_same_name_kinds_retain_existing_ambiguity(language):
    observed, target = _graphs(("type_alias", "constant"), "type_alias", language=language)
    result = _wanted(compare_graphs(observed, target))
    assert (result[0].status, result[0].change) == ("UNKNOWN", "ambiguous")


def test_namespace_selection_never_crosses_language_boundary():
    observed, target = _graphs(("type_alias", "constant"), "type_alias")
    observed = replace(
        observed,
        entities=tuple(
            replace(entity, language="python") if entity.id == "site-0" else entity
            for entity in observed.entities
        ),
    )
    result = _wanted(compare_graphs(observed, target))
    assert (result[0].status, result[0].change) == ("UNKNOWN", "unavailable")


@pytest.mark.parametrize(
    "source,kind",
    [
        ("export interface Shared {}\nexport interface Shared {}\n", "interface"),
        ("export const Shared = 1;\nexport function Shared() {}\n", "constant"),
        ("export class Shared {}\nexport const Shared = 1;\n", "constant"),
    ],
)
def test_native_same_namespace_declarations_remain_ambiguous(tmp_path: Path, source, kind):
    facts = _collected(tmp_path, source)
    observed = _graph_from_source_facts(facts, ("src",))
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "wanted",
                kind,
                "app.src.main_x2e_ts.Shared",
                "typescript",
                presence="planned",
                provenance=("target",),
            ),
        ),
    )
    result = _wanted(compare_graphs(observed, target))
    assert (result[0].status, result[0].change) == ("UNKNOWN", "ambiguous")
    assert len(result[0].observed_ids) == 2


def test_type_value_matching_is_recorded_identically_in_live_and_saved_reports(
    tmp_path: Path, monkeypatch
):
    root, config = _project(tmp_path / "project")
    source = root / "src/main.ts"
    source.write_text(
        source.read_text() + "\nconst DriverEntityManager = 1;\n"
        "export type EntityManager = number;\n"
        "export const EntityManager: EntityManager = DriverEntityManager;\n"
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    for identifier, kind in (("manager-type", "type_alias"), ("manager-value", "constant")):
        contract["declarations"]["uml"]["entities"].append(
            {
                "id": identifier,
                "kind": kind,
                "qualified_name": "demo.src.main_x2e_ts.EntityManager",
                "parent_id": "main",
                "language": "typescript",
                "presence": "planned",
                "responsibilities": ["Expose the distinct EntityManager namespace."],
                "provenance": ["docs/target.md"],
            }
        )
    path.write_text(json.dumps(contract))
    fresh, encoded = run_report(
        root,
        config=config,
        analyzer=trusted(_TypeScriptCollector()),
        only_architecture=True,
        full_architecture=True,
    )
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    selected = {"manager-type", "manager-value"}
    assert {
        item.subject_id: item.status
        for item in report.comparison.assessments
        if item.subject_id in selected and item.aspect == "existence"
    } == {
        "manager-type": "PASS",
        "manager-value": "PASS",
    }
    observed = {entity.id: entity for entity in report.observed.entities}
    correspondences = {
        item.target_id: item.observed_ids for item in report.comparison.correspondences
    }
    assert observed[correspondences["manager-type"][0]].kind == "type_alias"
    assert observed[correspondences["manager-value"][0]].kind == "constant"
    assert correspondences["manager-type"] != correspondences["manager-value"]
    saved_path = tmp_path / "saved.json"
    saved_path.write_bytes(encoded)

    def unexpected_comparison(*args, **kwargs):
        raise AssertionError("Saved reports must use the recorded comparison.")

    monkeypatch.setattr("archkeel.check.uml_evaluation.compare_graphs", unexpected_comparison)
    saved = run_saved_report(saved_path, only_architecture=True, full_architecture=True)
    assert saved.rule_assessments == fresh.rule_assessments
    assert saved.architecture_projection == fresh.architecture_projection
    assert fresh.exit_code == saved.exit_code == 2
    assert model.coverage.status == "FAIL" and model.coverage.failures
