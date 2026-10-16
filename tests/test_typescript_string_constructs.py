# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual TypeScript/JavaScript sources supply conservative construct evidence."""

from __future__ import annotations

import json

import pytest
from test_typescript_collect import _facts

from archkeel.analyzer.typescript import parse as parser
from archkeel.check.observation import assemble_observation
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
from archkeel.ir.facts import ConstructSupport, ForbiddenConstructKind, SourceSectionName
from archkeel.ir.trace import trace_valid_violations

RULE = "WRITTEN-STRING-CONTROL"
CONTRACT = {
    "schema_version": "2.1.0",
    "components": [],
    "rules": [
        {
            "id": RULE,
            "kind": "forbidden_construct",
            "source": "app",
            "constructs": ["string_literal_compare"],
            "rationale": "Protocol decisions require owned typed values.",
            "decided_by": "architect",
            "provenance": ["architecture.md"],
        }
    ],
}
OPTIONS = {"module": "CommonJS", "moduleResolution": "Node", "allowJs": True}


def _model(tmp_path, source, extension="ts", options=None):
    facts = _facts(tmp_path, {f"src/main.{extension}": source}, options=options or OPTIONS)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(CONTRACT))
    (tmp_path / "architecture.md").write_text("Protocol values have explicit typed owners.\n")
    fixed_intent = path.read_bytes()
    observed, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=path,
        roots=("src",),
        namespace="app",
    )
    assert path.read_bytes() == fixed_intent
    return facts, observed


def _constructs(facts):
    return tuple(
        row
        for section in facts.sections
        if section.name is SourceSectionName.CONSTRUCTS
        for row in section.records
    )


def _assessment(model):
    return next(
        row
        for row in rule_assessments(
            model,
            undecided_by_rule=unknown_positions_by_rule(model),
            complete=model.coverage.status == "PASS",
        )
        if row.id == RULE
    )


@pytest.mark.parametrize("extension", ["ts", "js"])
@pytest.mark.parametrize(
    "body",
    [
        'return value == "active";',
        'return value === "active";',
        'return value != "active";',
        'return value !== "active";',
        'return "active" === value;',
        'return value === ("active");',
        'return value === `active`;',
        r'return value === "act\u0069ve";',
        'switch (value) { case "active": return true; default: return false; }',
        'switch (value) { case `active`: return true; default: return false; }',
    ],
)
def test_written_literal_comparisons_have_actual_native_trace_valid_failures(
    tmp_path, extension, body
):
    facts, model = _model(tmp_path, "export function decide(value) { " + body + " }", extension)
    records = _constructs(facts)
    assert len(records) == 1
    assert records[0].data.get("construct") == ForbiddenConstructKind.STRING_LITERAL_COMPARE
    assert records[0].data.get("owner").endswith(".decide")
    evidence = {row.id: row for row in facts.evidence}
    assert all(evidence[key].file == f"src/main.{extension}" for key in records[0].evidence_ids)
    assert any("act" in evidence[key].excerpt for key in records[0].evidence_ids)
    violations = trace_valid_violations(model)
    assert len(violations) == 1 and violations[0].rule_ids == (RULE,)
    assert violations[0].fact_ids == (records[0].id,)
    assert _assessment(model).status == "FAIL"


def test_capability_and_empty_source_never_claim_complete_construct_absence(tmp_path):
    facts, model = _model(tmp_path, "export function same(left, right) { return left === right; }")
    capabilities = {item.name: item.status for item in facts.capabilities.constructs}
    assert capabilities.get(ForbiddenConstructKind.STRING_LITERAL_COMPARE) is ConstructSupport.PARTIAL
    assert not _constructs(facts)
    assert not trace_valid_violations(model)
    assert _assessment(model).status == "UNKNOWN"


@pytest.mark.parametrize(
    "body",
    [
        "return left === right;",
        "return value === Mode.Active;",
        "return value === `active-${left}`;",
        'const label = "active"; return value === label;',
        'let label = "active"; label = left; return value === label;',
        'const label = "active"; return () => value === label;',
        'return value === format("active");',
        'return ["active", "pending"].includes(value);',
        'return value.includes("active");',
        'return value.startsWith("active");',
        'return value.endsWith("active");',
        'return "active" in value;',
    ],
)
def test_unobserved_value_flow_and_method_forms_are_not_fabricated_or_clean(tmp_path, body):
    facts, model = _model(tmp_path, "export function decide(value, left, right) { " + body + " }")
    assert not _constructs(facts)
    assert not trace_valid_violations(model)
    assert _assessment(model).status == "UNKNOWN"


def test_nominal_enum_and_data_comparisons_are_not_written_literal_dispatch(tmp_path):
    facts, model = _model(
        tmp_path,
        'enum Mode { Active = "active" }\n'
        "export function decide(value: Mode, left: string, right: string) { "
        "return value === Mode.Active && left === right; }",
    )
    assert not _constructs(facts)
    assert not trace_valid_violations(model)
    assert _assessment(model).status == "UNKNOWN"


def test_nested_equality_occurrences_have_distinct_source_bound_identities(tmp_path):
    facts, model = _model(
        tmp_path, 'export function decide(value) { return value === "active" === "pending"; }'
    )
    records = _constructs(facts)
    assert len(records) == len({row.id for row in records}) == 2
    assert {row.fact_ids[0] for row in trace_valid_violations(model)} == {
        row.id for row in records
    }


def test_unknown_parent_grammar_preserves_observation_of_known_children(tmp_path):
    assert "ternary_expression" not in parser._NODE_KINDS
    facts, model = _model(
        tmp_path,
        'export function decide(value, enabled) { return enabled ? value === "active" : false; }',
    )
    assert len(_constructs(facts)) == 1
    assert _assessment(model).status == "FAIL"


def test_unknown_comparison_grammar_cannot_become_proven_absence(tmp_path, monkeypatch):
    monkeypatch.delitem(parser._NODE_KINDS, "binary_expression", raising=False)
    facts, model = _model(tmp_path, 'export function decide(value) { return value === "active"; }')
    assert not _constructs(facts)
    assert not trace_valid_violations(model)
    assert _assessment(model).status == "UNKNOWN"


def test_unknown_template_child_is_not_promoted_to_a_plain_literal(tmp_path, monkeypatch):
    monkeypatch.delitem(parser._NODE_KINDS, "template_substitution", raising=False)
    facts, model = _model(
        tmp_path, 'export function decide(value, left) { return value === `active-${left}`; }'
    )
    assert not _constructs(facts)
    assert not trace_valid_violations(model)
    assert _assessment(model).status == "UNKNOWN"


def test_parse_error_cannot_become_a_clean_construct_rule(tmp_path):
    facts, model = _model(tmp_path, 'export function decide(value { return value === "active";')
    assert not facts.coverage.full_scope
    assert _assessment(model).status != "PASS"


@pytest.mark.parametrize(
    "options,selected",
    [
        ({"module": "CommonJS", "moduleResolution": "Node", "checkJs": True}, True),
        (
            {
                "module": "CommonJS",
                "moduleResolution": "Node",
                "checkJs": True,
                "allowJs": False,
            },
            False,
        ),
    ],
)
def test_native_js_entry_respects_real_allow_js_and_check_js_selection(
    tmp_path, options, selected
):
    facts, model = _model(
        tmp_path,
        'export function decide(value) { return value === "active"; }',
        "js",
        options,
    )
    assert ("src/main.js" in facts.coverage.selected_files) is selected
    if selected:
        assert len(_constructs(facts)) == 1
        assert _assessment(model).status == "FAIL"
    else:
        assert not _constructs(facts)
        assert _assessment(model).status != "PASS"
