# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Named TypeScript parameter properties are direct declarations, not inferred storage."""

import json
from pathlib import Path

import pytest
from collector_pin import trusted
from test_typescript_inner import _collected
from test_typescript_partial_uml import _project, _TypeScriptCollector

from archkeel.check.report import run_report, run_saved_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report


def test_parameter_properties_use_existing_bound_source_attribute_facts(tmp_path: Path):
    source = (
        "export class Store { constructor(\n"
        "  protected readonly repo: string, ordinary: number\n) {} }\n"
    )
    facts = _collected(tmp_path, source)
    records = next(s.records for s in facts.sections if s.name == "symbols")
    owner = next(r for r in records if r.kind == "class")
    declarations = owner.data.get("attribute_declarations")
    assert len(declarations) == 1
    field = declarations[0]
    assert field.get("name") == "repo" and field.get("annotation") == "string"
    assert field.get("visibility").get("kind") == "protected"
    assert field.get("static") is False
    evidence = next(e for e in facts.evidence if e.id in field.get("evidence_ids"))
    assert (evidence.file, evidence.line, evidence.column) == ("src/main.ts", 2, 22)
    inventories = owner.data.get("member_inventories")
    assert all(i.get("status") == "complete" for i in inventories)
    assert next(i for i in inventories if i.get("kind") == "attribute").get("definition_ids") == (
        field.get("definition_id"),
    )


def _target(root: Path, expected: str, spelling="constructor", methods=False):
    root, config = _project(root, matching=True)
    (root / "src/main.ts").write_text(
        f"export class Store {{ {spelling}(readonly repo: string, ordinary: number) {{}} }}\n"
    )
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_bytes())
    declaration = {
        "presence": "planned",
        "language": "typescript",
        "provenance": ["docs/target.md"],
        "responsibilities": ["Declare the independent Store API."],
    }
    entities = [
        {
            **declaration,
            "id": "main",
            "kind": "module",
            "qualified_name": "demo.src.main_x2e_ts",
            "parent_id": "app",
            "file_path": "src/main.ts",
        },
        {
            **declaration,
            "id": "store",
            "kind": "class",
            "qualified_name": "demo.src.main_x2e_ts.Store",
            "parent_id": "main",
        },
    ]
    if expected:
        entities.append(
            {
                **declaration,
                "id": "field",
                "kind": "attribute",
                "qualified_name": f"demo.src.main_x2e_ts.Store.{expected}",
                "parent_id": "store",
                "annotation": "string",
            }
        )
    if methods:
        entities.append(
            {
                **declaration,
                "id": "ctor",
                "kind": "method",
                "qualified_name": "demo.src.main_x2e_ts.Store.constructor",
                "parent_id": "store",
                "signature": {
                    "parameters": [
                        {
                            "name": "repo",
                            "annotation": "string",
                            "kind": "positional",
                            "default_known": True,
                        },
                        {
                            "name": "ordinary",
                            "annotation": "number",
                            "kind": "positional",
                            "default_known": True,
                        },
                    ],
                    "returns": None,
                },
            }
        )
    uml = contract["declarations"]["uml"]
    uml["schema_version"] = "1.1.0"
    uml["entities"] = entities
    uml["scopes"] = [
        {
            "scope_id": "store",
            "entity_kinds": ["attribute", "method"] if methods else ["attribute"],
            "mode": "closed",
            "rationale": "Only declared direct fields.",
            "provenance": ["docs/target.md"],
        }
    ]
    contract_path.write_text(json.dumps(contract))
    return root, config


@pytest.mark.parametrize("expected,status", [("repo", "PASS"), ("missing", "FAIL"), ("", "FAIL")])
def test_readonly_only_property_matches_native_and_saved_reports(tmp_path, expected, status):
    root, config = _target(tmp_path / "project", expected)
    result, encoded = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    comparison = architecture_report(model).comparison
    assert comparison.status == status
    assert result.declared_rules == status
    if expected == "missing":
        assert any(a.subject_id == "field" and a.status == "FAIL" for a in comparison.assessments)
    if not expected:
        assert any(
            a.aspect == "completeness" and a.status == "FAIL" for a in comparison.assessments
        )
    saved = root / "saved.json"
    saved.write_bytes(encoded)
    replay = run_saved_report(saved)
    assert replay.declared_rules == result.declared_rules
    assert replay.rule_assessments == result.rule_assessments


@pytest.mark.parametrize("spelling", ["'constructor'", '"constructor"'])
def test_quoted_constructor_matches_closed_field_and_method_target(tmp_path, spelling):
    root, config = _target(tmp_path / "project", "repo", spelling, methods=True)
    result, encoded = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert result.declared_rules == "PASS"
    path = root / "saved.json"
    path.write_bytes(encoded)
    assert run_saved_report(path).rule_assessments == result.rule_assessments


def test_parameter_decorators_do_not_become_property_decorators(tmp_path):
    source = """@ClassTag()
export class Store {
  @FieldTag() declared: string;
  constructor(@Inject('repo') private readonly repo: string, ordinary: number) {}
  @MethodTag() run(): void {}
}
"""
    facts = _collected(tmp_path, source)
    symbols = next(s.records for s in facts.sections if s.name == "symbols")
    record = next(r for r in symbols if r.kind == "class")
    declarations = {item.get("name"): item for item in record.data.get("attribute_declarations")}
    assert declarations["declared"].get("decorators") == ("@FieldTag()",)
    assert declarations["repo"].get("decorators") == ()
    assert declarations["repo"].get("decorator_evidence_ids") == ()
    evidence = {item.id: item for item in facts.evidence}
    assert [
        evidence[identity].excerpt
        for identity in declarations["declared"].get("decorator_evidence_ids")
    ] == ["@FieldTag()"]


@pytest.mark.parametrize("spelling", ["constructor", "'constructor'"])
@pytest.mark.parametrize("expected,status", [("repo", "PASS"), ("missing", "FAIL")])
def test_parameter_decorator_matches_independent_closed_target_and_saved_report(
    tmp_path, spelling, expected, status
):
    root, config = _target(tmp_path / "project", expected, spelling, methods=True)
    (root / "src/main.ts").write_text(
        f"@ClassTag() export class Store {{ {spelling}("
        "@Inject('repo') readonly repo: string, ordinary: number) {} }\n"
    )
    result, encoded = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert result.declared_rules == status
    path = root / "saved.json"
    path.write_bytes(encoded)
    assert run_saved_report(path).rule_assessments == result.rule_assessments


def test_decorated_extra_method_is_known_failure_beside_parameter_property(tmp_path):
    root, config = _target(tmp_path / "project", "repo", methods=True)
    (root / "src/main.ts").write_text(
        "export class Store { constructor(readonly repo: string, ordinary: number) {} "
        "@Get() extra(): void {} }\n"
    )
    result, encoded = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert result.declared_rules == "FAIL"
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert any(
        a.aspect == "completeness" and a.status == "FAIL"
        for a in architecture_report(model).comparison.assessments
    )
    path = root / "saved.json"
    path.write_bytes(encoded)
    assert run_saved_report(path).rule_assessments == result.rule_assessments


@pytest.mark.parametrize(
    "name,status",
    [
        (r"constr\u{20}uctor", "UNKNOWN"),
        (r"constr\u0020uctor", "UNKNOWN"),
        (r"r\u0065ad", "UNKNOWN"),
        (r'"constr\u{110000}ctor"', "UNKNOWN"),
        (r'"constr\u{FFFFFFFF}ctor"', "UNKNOWN"),
        (r'"constr\u{20}uctor"', "PASS"),
        (r'"constr\u{D800}uctor"', "PASS"),
    ],
)
def test_undecorated_method_unicode_guard_preserves_private_attribute_target(
    tmp_path, name, status
):
    source = (
        "export class Store { constructor(private repo: string, ordinary: number) {} "
        f"{name}(): void {{}} }}\n"
    )
    root, config = _target(tmp_path / "project", "repo")
    (root / "src/main.ts").write_text(source)
    result, encoded = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert result.declared_rules == status
    path = root / "saved.json"
    path.write_bytes(encoded)
    assert run_saved_report(path).rule_assessments == result.rule_assessments
