# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Named TypeScript parameter properties are direct declarations, not inferred storage."""

import json
from pathlib import Path

import pytest
from test_typescript_inner import _collected
from test_typescript_partial_uml import _project, _TypeScriptCollector

from archkeel.analyzer.typescript.parse import parse
from archkeel.analyzer.typescript.syntax import DefinitionKind, Visibility
from archkeel.check.observe import Observer
from archkeel.check.report import run_report, run_saved_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report


@pytest.mark.parametrize(
    "modifier,visibility",
    [
        ("public", Visibility.PUBLIC),
        ("private", Visibility.PRIVATE),
        ("protected", Visibility.PROTECTED),
        ("readonly", None),
        ("private readonly", Visibility.PRIVATE),
    ],
)
def test_named_parameter_properties_preserve_parameter_and_member(modifier, visibility):
    source = f"export class Store {{ constructor({modifier} repo: string, ordinary: number) {{}} }}"
    syntax = parse("src/main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    constructor = next(d for d in syntax.definitions if d.name == "constructor")
    assert [(m.name, m.annotation, m.visibility, m.static) for m in owner.members] == [
        ("repo", "string", visibility, False)
    ]
    assert owner.members_complete
    assert [(p.name, p.annotation) for p in constructor.parameters] == [
        ("repo", "string"),
        ("ordinary", "number"),
    ]
    assert constructor.signature_complete
    assert owner.members[0].span.column == source.index("repo") + 1


def test_default_literal_belongs_to_parameter_not_constant_property():
    syntax = parse("main.ts", b"class Store { constructor(readonly count: number = 7) {} }")
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    constructor = next(d for d in syntax.definitions if d.name == "constructor")
    assert [m.name for m in owner.members] == ["count"]
    assert owner.members[0].literal is None
    assert constructor.parameters[0].default == "7"
    assert constructor.signature_complete is False


@pytest.mark.parametrize(
    "body",
    [
        "constructor(private {repo}: object) {}",
        "constructor(private ...repo: string[]) {}",
        "constructor(private repo: string, private repo: string) {}",
        "repo: string; constructor(private repo: string) {}",
        "constructor(private repo: string); constructor(repo: string) {}",
        "constructor(repo: string); constructor(private repo: string) {}",
        "constructor(private repo: ) {}",
    ],
)
def test_ambiguous_or_malformed_parameter_properties_keep_inventory_partial(body):
    syntax = parse("main.ts", f"class Store {{ {body} }}".encode())
    owners = [d for d in syntax.definitions if d.kind is DefinitionKind.CLASS]
    if syntax.first_error is not None:
        assert all(owner.members_complete is False for owner in owners)
        return
    owner = owners[0]
    assert owner.members_complete is False
    assert len({m.name for m in owner.members}) == len(owner.members)


@pytest.mark.parametrize("extra", ["[key](): void {}", "static { initialize(); }"])
def test_other_unsupported_members_do_not_become_complete(extra):
    syntax = parse(
        "main.ts", f"class Store {{ constructor(private repo: string) {{}} {extra} }}".encode()
    )
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert [m.name for m in owner.members] == ["repo"]
    assert owner.members_complete is False


def test_static_constructor_name_is_not_an_instance_constructor():
    syntax = parse(
        "main.ts",
        b"class Store { constructor(private repo: string) {} "
        b"static constructor(ordinary: number) {} }",
    )
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert [m.name for m in owner.members] == ["repo"]
    assert owner.members_complete


@pytest.mark.parametrize("method", ["static constructor", "read"])
def test_parameter_property_modifiers_on_ordinary_methods_stay_unsupported(method):
    syntax = parse("main.ts", f"class Store {{ {method}(readonly repo: string) {{}} }}".encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert not owner.members
    assert owner.members_complete is False


@pytest.mark.parametrize("spelling", ["'constructor'", '"constructor"'])
def test_quoted_instance_constructor_collects_named_properties(spelling):
    syntax = parse("main.ts", f"class Store {{ {spelling}(private repo: string) {{}} }}".encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    method = next(d for d in syntax.definitions if d.kind is DefinitionKind.METHOD)
    assert [m.name for m in owner.members] == ["repo"]
    assert owner.members_complete
    assert method.name == "constructor"
    assert method.parameters[0].name == "repo"


@pytest.mark.parametrize(
    "body",
    [
        r'"repo": string; constructor(private repo: string) {}',
        r'"r\u0065po": string; constructor(private repo: string) {}',
        r"r\u0065po: string; constructor(private repo: string) {}",
        r"constructor(private repo: string, private r\u0065po: string) {}",
        r"constructor(private r\u{65}po: string, private repo: string) {}",
        r'"constr\u0075ctor"(readonly repo: string) {}',
        r"constr\u0075ctor(readonly repo: string) {}",
    ],
)
def test_escaped_or_colliding_static_names_never_claim_complete_inventory(body):
    syntax = parse("main.ts", f"class Store {{ {body} }}".encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert owner.members_complete is False
    assert not any(m.name == "repo" for m in owner.members)


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
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
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
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
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
    syntax = parse("src/main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    constructor = next(d for d in syntax.definitions if d.name == "constructor")
    method = next(d for d in syntax.definitions if d.name == "run")
    assert owner.members_complete and constructor.signature_complete
    assert [value for value, _ in owner.decorator_sources] == ["@ClassTag()"]
    assert [value for value, _ in method.decorator_sources] == ["@MethodTag()"]
    assert constructor.decorator_sources == ()
    fields = {member.name: member for member in owner.members}
    assert [value for value, _ in fields["declared"].decorator_sources] == ["@FieldTag()"]
    assert fields["repo"].decorator_sources == ()
    assert fields["repo"].span.line == 4 and fields["repo"].literal is None
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
@pytest.mark.parametrize("signature_first", [True, False])
def test_decorated_methods_do_not_hide_constructor_overload_ambiguity(spelling, signature_first):
    signature, implementation = f"{spelling}(repo: string);", f"{spelling}(repo: string) {{}}"
    constructors = (signature, implementation) if signature_first else (implementation, signature)
    source = f"class Store {{ {' '.join(constructors)} @Get() run(): void {{}} }}"
    syntax = parse("main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert syntax.first_error is None
    assert owner.members_complete is False


@pytest.mark.parametrize(
    "member",
    [
        r'@Get() static "constr\u0075ctor"(): void {}',
        r'@Get() "constr\u{20}uctor"(): void {}',
    ],
)
def test_property_support_preserves_supported_decorated_quoted_method_names(member):
    source = f"class Store {{ constructor(readonly repo: string) {{}} {member} }}"
    syntax = parse("main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert syntax.first_error is None
    assert [m.name for m in owner.members] == ["repo"]
    assert owner.members_complete
    method = syntax.definitions[-1]
    assert [value for value, _ in method.decorator_sources] == ["@Get()"]


@pytest.mark.parametrize(
    "constructor",
    [
        "@Get() 'constructor'(readonly repo: string) {}",
        r'"constr\u0075ctor"(readonly repo: string) {}',
        "@Get() static constructor(readonly repo: string) {}",
        "@Get() read(readonly repo: string) {}",
    ],
)
def test_decorator_composition_cannot_authorize_unsupported_property_owners(constructor):
    syntax = parse("main.ts", f"class Store {{ {constructor} }}".encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert syntax.first_error is None
    assert owner.members_complete is False and not owner.members
    if constructor.startswith("@Get() '"):
        assert syntax.definitions[-1].name == "'constructor'"


@pytest.mark.parametrize("name", [r'"bad\u{110000}name"', r"bad\u0020name"])
def test_named_properties_do_not_bypass_decorator_unicode_guards(name):
    source = f"class Store {{ constructor(readonly repo: string) {{}} @Get() {name}() {{}} }}"
    syntax = parse("main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert [m.name for m in owner.members] == ["repo"]
    assert owner.members_complete is False


def test_decorated_field_alias_still_blocks_parameter_property_closure():
    source = 'class Store { @Field() "repo": string; constructor(private repo: string) {} }'
    syntax = parse("main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert owner.members_complete is False
    assert [member.name for member in owner.members] == ['"repo"']
    assert [value for value, _ in owner.members[0].decorator_sources] == ["@Field()"]


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
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
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
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
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
    syntax = parse("src/main.ts", source.encode())
    owner = next(d for d in syntax.definitions if d.kind is DefinitionKind.CLASS)
    assert syntax.first_error is None
    assert [member.name for member in owner.members] == ["repo"]
    assert owner.members[0].visibility is Visibility.PRIVATE
    assert owner.members_complete is (status == "PASS")
    root, config = _target(tmp_path / "project", "repo")
    (root / "src/main.ts").write_text(source)
    result, encoded = run_report(root, config=config, analyzer=Observer(_TypeScriptCollector()))
    assert result.declared_rules == status
    path = root / "saved.json"
    path.write_bytes(encoded)
    assert run_saved_report(path).rule_assessments == result.rule_assessments
