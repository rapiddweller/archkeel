# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit module selection must never silently decide an entire component pair."""

import json
from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.check.declarations import project_rule_declaration
from archkeel.check.evaluation.rule_support import _forbidden_dependency_verdicts
from archkeel.check.evaluation.rules import rule_evaluation_facts, rule_subject_failures
from archkeel.check.validation.closed_world import _decided_pairs
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.codec import contract_bytes, contract_digest, parse_contract
from archkeel.ir.facts_codec import classified
from archkeel.ir.model import EvidenceClass, ForbiddenDependencyRule
from archkeel.ir.profiles import PYTHON
from archkeel.ir.widening import contract_widening_changes

ROOT = Path(__file__).parents[1]


def _contract(**selectors):
    return {
        "schema_version": "3.4.0",
        "components": [
            {
                "id": name,
                "label": name,
                "role": "component",
                "packages": [f"sample.{name}", f"sample.{name}_extra"],
                "responsibilities": [f"Own {name}."],
                "forbidden_responsibilities": [],
                "provenance": ["target.md"],
            }
            for name in ("caller", "errors")
        ],
        "rules": [
            {
                "id": "NO-AGGREGATE",
                "kind": "forbidden_dependency",
                "source": "sample.caller",
                "target": "sample.errors",
                "include_type_checking": True,
                "rationale": "Keep callers on narrow error contracts.",
                "provenance": ["target.md"],
                "decided_by": "architect",
                **selectors,
            }
        ],
    }


def _ownership(contract):
    return tuple(
        (item.label, item.packages, item.exact_modules or ()) for item in contract.components
    )


def _import(source, target, *, symbol=None, typing=False, symbols_known=True):
    return classified(
        item_id=f"IMPORT-{source}-{target}-{symbol}-{typing}",
        evidence_class=EvidenceClass.FACT,
        area="imports",
        kind="import",
        title=f"{source} -> {target}",
        data={
            "source_module": source,
            "target_module": target,
            "under_type_checking": typing,
            "symbol": symbol,
            "symbols_known": symbols_known,
        },
    )


def _module(name):
    return classified(
        item_id=f"MODULE-{name}",
        evidence_class=EvidenceClass.FACT,
        area="modules",
        kind="module",
        title=name,
        data={"qualified_name": name},
    )


@pytest.mark.parametrize("source_match,target_match", product(("exact", "prefix"), repeat=2))
def test_selector_matrix(source_match, target_match):
    contract = parse_contract(_contract(source_match=source_match, target_match=target_match))
    imports = [
        _import(source, target)
        for source, target in product(
            ("sample.caller", "sample.caller.child", "sample.callers"),
            ("sample.errors", "sample.errors.base", "sample.errors_extra.child"),
        )
    ]
    matches = {
        (item["data"]["source_module"], item["data"]["target_module"])
        for _, item, verdict in _forbidden_dependency_verdicts(
            imports, contract.rules, _ownership(contract)
        )
        if verdict is AssessmentStatus.FAIL
    }
    if source_match == target_match == "prefix":
        # Existing package-pair semantics cover every package owned by each component.
        expected_targets = ("sample.errors", "sample.errors.base", "sample.errors_extra.child")
    else:
        expected_targets = ("sample.errors",) + (
            ("sample.errors.base",) if target_match == "prefix" else ()
        )
    expected_sources = ("sample.caller",) + (
        ("sample.caller.child",) if source_match == "prefix" else ()
    )
    assert matches == set(product(expected_sources, expected_targets))


def test_exact_selection_preserves_symbol_typing_and_exact_source_allowances():
    contract = parse_contract(
        _contract(
            source_match="exact",
            target_match="exact",
            target_symbol="Hidden",
            include_type_checking=False,
            allowed_sources=["sample.caller.child"],
        )
    )
    imports = [
        _import("sample.caller", "sample.errors", symbol="Hidden"),
        _import("sample.caller", "sample.errors", symbol="Other"),
        _import("sample.caller", "sample.errors", symbols_known=False),
        _import("sample.caller", "sample.errors", symbol="Hidden", typing=True),
        _import("sample.caller.child", "sample.errors", symbol="Hidden"),
    ]
    assert [
        verdict
        for _, _, verdict in _forbidden_dependency_verdicts(
            imports, contract.rules, _ownership(contract)
        )
    ] == [AssessmentStatus.FAIL, AssessmentStatus.PASS, AssessmentStatus.UNKNOWN]
    rule = replace(contract.rules[0], allowed_sources=("sample.caller",))
    assert not list(_forbidden_dependency_verdicts(imports, (rule,), _ownership(contract)))


def test_exact_source_requires_its_own_subject_and_receipt():
    contract = parse_contract(_contract(source_match="exact", target_match="exact"))
    child = _module("sample.caller.child")
    root = _module("sample.caller")
    kwargs = dict(
        profile=PYTHON,
        scope="root",
        source_modules=None,
        blank_modules=frozenset(),
        receipt_scope_complete=True,
    )
    assert rule_evaluation_facts(contract, modules=[child], **kwargs) == []
    [receipt] = rule_evaluation_facts(contract, modules=[root, child], **kwargs)
    assert receipt["subjects"] == ["sample.caller"]
    [failure] = rule_subject_failures(
        contract.rules, {"sample.caller.child", "sample.errors.base"}, type_shapes={}
    )
    assert failure["data"]["missing"] == ["source", "target"]


def test_exact_selection_is_not_a_whole_pair_decision():
    for source_match, target_match in (
        ("exact", "exact"),
        ("exact", "prefix"),
        ("prefix", "exact"),
    ):
        contract = parse_contract(_contract(source_match=source_match, target_match=target_match))
        assert _decided_pairs(contract, ForbiddenDependencyRule) == []
        declaration = project_rule_declaration(contract.rules[0])
        assert declaration["data"].get("source_match", "prefix") == source_match
        assert declaration["data"].get("target_match", "prefix") == target_match


def test_selectors_roundtrip_without_changing_legacy_bytes():
    raw = _contract(source_match="exact", target_match="exact")
    contract = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    schema = json.loads((ROOT / "schema/architecture-contract-3.4.schema.json").read_bytes())
    assert Draft202012Validator(schema).is_valid(json.loads(contract_bytes(contract)))
    legacy = _contract()
    legacy["schema_version"] = "3.3.0"
    prior = parse_contract(legacy)
    encoded = json.loads(contract_bytes(prior))
    assert "source_match" not in encoded["rules"][0]
    assert "target_match" not in encoded["rules"][0]
    explicit = parse_contract(_contract(source_match="prefix", target_match="prefix"))
    assert contract_digest(replace(explicit, schema_version="3.3.0")) == contract_digest(prior)


@pytest.mark.parametrize("field", ("source_match", "target_match"))
@pytest.mark.parametrize("value", (None, True, "substring", "", 1))
def test_selector_grammar_is_strict(field, value):
    with pytest.raises(ValueError):
        parse_contract(_contract(**{field: value}))


@pytest.mark.parametrize("version", ("2.1.0", "2.2.0", "2.3.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0"))
def test_older_versions_reject_explicit_selectors(version):
    raw = _contract(source_match="prefix")
    raw["schema_version"] = version
    with pytest.raises(ValueError, match="3.4.0"):
        parse_contract(raw)


@pytest.mark.parametrize("field", ("source_match", "target_match"))
def test_switching_to_exact_is_widening_and_back_to_prefix_is_narrowing(field):
    before = parse_contract(_contract())
    after = parse_contract(_contract(**{field: "exact"}))
    assert field in {change.field for change in contract_widening_changes(before, after)}
    assert contract_widening_changes(after, before) == ()


@pytest.mark.parametrize("mounted", (False, True))
def test_native_exact_policy_preserves_nested_receipts_and_saved_reports(tmp_path, mounted):
    from test_exact_module_ownership import _observe_tree

    from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
    from archkeel.ir.decisions import rule_assessments
    from archkeel.ir.trace import trace_valid_violations

    contract = _contract(source_match="exact", target_match="exact")
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    files = {
        "sample/__init__.py": "",
        "sample/caller/__init__.py": "import sample.errors\nimport sample.errors.base\n",
        "sample/caller/child.py": "import sample.errors\nimport sample.errors.base\n",
        "sample/errors/__init__.py": "",
        "sample/errors/base.py": "",
    }
    if mounted:
        files["inside.json"] = json.dumps(contract)
        outer = _contract()
        outer["components"] = [
            {
                **outer["components"][0],
                "id": "all",
                "label": "all",
                "packages": ["sample"],
                "inside": "inside.json",
            }
        ]
        outer["rules"] = []
        contract = outer
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    assert observation.coverage.status == "PASS", observation.coverage.failures
    findings = trace_valid_violations(observation)
    assert len(findings) == 1
    assert findings[0].data.get("source_module") == "sample.caller"
    assert findings[0].data.get("target_module") == "sample.errors"
    identity = "all:NO-AGGREGATE" if mounted else "NO-AGGREGATE"
    [row] = [r for r in rule_assessments(observation, undecided_by_rule={}) if r.id == identity]
    assert row.status == "FAIL" and row.evaluation_proven
    saved = parse_observation(
        decode_canonical_model(json.loads(canonical_report_bytes(observation)))
    )
    assert rule_assessments(saved, undecided_by_rule={}) == rule_assessments(
        observation, undecided_by_rule={}
    )


def test_exact_parent_ban_does_not_prohibit_an_entire_child_component_pair():
    from archkeel.check.validation.inside import _forbidden_targets

    contract = parse_contract(_contract(source_match="exact", target_match="exact"))
    assert _forbidden_targets(contract, contract.components[0]) == []
    # The parent ban still rejects its exact import through the shared evaluator.
    assert (
        len(
            list(
                _forbidden_dependency_verdicts(
                    [_import("sample.caller", "sample.errors")],
                    contract.rules,
                    _ownership(contract),
                )
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "source_match,target_match,source,target,expected",
    [
        ("prefix", "prefix", "sample.caller", "sample.errors_extra.child", True),
        ("prefix", "prefix", "sample.caller_extra.child", "sample.errors_extra", True),
        ("exact", "prefix", "sample.caller", "sample.errors_extra", False),
        ("prefix", "exact", "sample.caller_extra", "sample.errors", False),
        ("exact", "prefix", "sample.caller", "sample.errors.child", True),
        ("prefix", "exact", "sample.caller.child", "sample.errors", True),
    ],
)
def test_module_cells_obey_both_module_selectors(
    source_match, target_match, source, target, expected
):
    from archkeel.ir.architecture_graph import ComponentIntent, RuleAssessment
    from archkeel.ir.model import Record, RecordData
    from archkeel.ir.module_explore import _dependency_selections, _rule_applies

    contract = parse_contract(_contract(source_match=source_match, target_match=target_match))
    raw_declaration = project_rule_declaration(contract.rules[0])
    raw_site = _import(source, target)

    def record(raw):
        return Record(
            id=raw["id"],
            evidence_class=EvidenceClass(raw["evidence_class"]),
            area=raw["area"],
            kind=raw["kind"],
            title=raw["title"],
            subjects=tuple(raw["subjects"]),
            evidence_ids=tuple(raw["evidence_ids"]),
            rule_ids=tuple(raw["rule_ids"]),
            fact_ids=tuple(raw["fact_ids"]),
            provenance=tuple(raw["provenance"]),
            data=RecordData(tuple(raw["data"].items())),
        )

    intents = {
        identity: ComponentIntent(
            identity, component.role, packages=component.packages, label=component.label
        )
        for identity, component in zip(("source", "target"), contract.components, strict=True)
    }
    assessment = RuleAssessment(
        id="NO-AGGREGATE",
        kind="forbidden_dependency",
        status="PASS",
        evaluation_proven=True,
        count=0,
        undecided=0,
        decided_by="architect",
        rationale="Keep narrow dependencies.",
        provenance=("target.md",),
        reason="Completed source proof.",
        scope="root",
        components=("source", "target"),
    )
    assert (
        _rule_applies(
            record(raw_declaration),
            assessment,
            source,
            target,
            record(raw_site),
            (),
            {"source"},
            {"target"},
            intents,
            {},
            _dependency_selections({contract.rules[0].id: record(raw_declaration)}, intents, {}),
        )
        is expected
    )
