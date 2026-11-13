# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decorators do not hide the direct lexical members written in TypeScript source."""

import json
from pathlib import Path

import pytest
from test_source_graph import _graph_from_source_facts
from test_typescript_inner import _collected, _collected_files
from test_typescript_partial_uml import _live, _project

from archkeel.check.report import run_saved_report
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, TargetScope
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report

SOURCE = """@Controller('api')
export class Endpoint {
  @Field() public token: string;
  @First
  // A comment does not detach a decorator.
  @Get('route')
  public static run(value: string): string { return value; }
  plain(): void {}
}
"""
# Inventory controls bind decorator names so unrelated import gaps cannot decide them.
DECORATORS = """
function Get() { return () => {}; }
function Controller(path: string) { return () => {}; }
function Field() { return () => {}; }
function First() {}
"""
QUALIFIED = "app.src.main_x2e_ts.Endpoint"


def _target(
    names: tuple[str, ...], *, qualified: str = QUALIFIED, kind: str = "method"
) -> ArchitectureGraph:
    owner = Entity(
        "endpoint",
        "class",
        qualified,
        "typescript",
        presence="planned",
        provenance=("docs/target.md",),
    )
    children = tuple(
        Entity(
            name,
            kind,
            f"{qualified}.{name}",
            "typescript",
            parent_id=owner.id,
            presence="planned",
            provenance=("docs/target.md",),
        )
        for name in names
    )
    return ArchitectureGraph(
        "declared",
        (owner, *children),
        target_scopes=(
            TargetScope(owner.id, "closed", "All direct members.", ("docs/target.md",), (kind,)),
        ),
    )


def test_decorated_members_keep_source_metadata_ownership_and_complete_inventory(
    tmp_path: Path,
) -> None:
    facts = _collected(tmp_path, SOURCE + DECORATORS)
    assert facts.coverage.full_scope and not facts.coverage.gaps
    symbols = {
        record.data.get("name"): record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    }
    evidence = {item.id: item for item in facts.evidence}
    assert symbols["Endpoint"].data.get("decorators") == ("@Controller('api')",)
    assert symbols["run"].data.get("decorators") == ("@First", "@Get('route')")
    assert symbols["plain"].data.get("decorators") == ()
    assert symbols["Endpoint"].data.get("signature_decorators_proven") is None
    assert symbols["run"].data.get("signature_decorators_proven") is False
    assert symbols["plain"].data.get("signature_decorators_proven") is True
    assert symbols["run"].data.get("lexical_parent_id") == symbols["Endpoint"].id
    assert symbols["run"].data.get("qualified_name") == f"{QUALIFIED}.run"
    refs = symbols["run"].data.get("decorator_evidence_ids")
    assert [(evidence[identity].line, evidence[identity].excerpt) for identity in refs] == [
        (4, "@First"),
        (6, "@Get('route')"),
    ]
    field = symbols["Endpoint"].data.get("attribute_declarations")[0]
    assert field.get("name") == "token" and field.get("decorators") == ("@Field()",)
    assert all(
        item.get("status") == "complete"
        for item in symbols["Endpoint"].data.get("member_inventories")
    )
    field_refs = field.get("decorator_evidence_ids")
    assert [(evidence[identity].line, evidence[identity].excerpt) for identity in field_refs] == [
        (3, "@Field()"),
    ]


def test_plain_top_level_and_nested_functions_publish_signature_identity(tmp_path):
    facts = _collected(
        tmp_path,
        "export function build(value: string): string { "
        "function nested(text: string): string { return text; } return nested(value); }",
    )
    functions = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "function"
    ]
    assert {record.data.get("name") for record in functions} == {"build", "nested"}
    assert all(record.data.get("signature_decorators_proven") is True for record in functions)


@pytest.mark.parametrize(
    "spelling",
    [
        "constructor",
        "'constructor'",
        '"constructor"',
        r'"constr\u0075ctor"',
        r'"constr\u{75}ctor"',
        r'"constr\x75ctor"',
        r"constr\u0075ctor",
        r"constr\u{75}ctor",
        r'"\constructor"',
        r'"constr\u{00000075}ctor"',
        r"constr\u{00000075}ctor",
        r'"constr\u{000000000000000000000000000075}ctor"',
    ],
)
def test_decorated_instance_constructor_spellings_keep_closed_methods_unknown(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {spelling}() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target((spelling,)))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize(
    "member,spelling",
    [
        ("static constructor(): void {}", "constructor"),
        ("public static constructor(value: string): string { return value; }", "constructor"),
        ("static 'constructor'(): void {}", "'constructor'"),
        (r'static "constr\u0075ctor"(): void {}', r'"constr\u0075ctor"'),
        (r'static "constr\u{00000075}ctor"(): void {}', r'"constr\u{00000075}ctor"'),
        ("static get constructor(): string { return ''; }", "constructor"),
        ("static set constructor(value: string) {}", "constructor"),
    ],
)
def test_decorated_static_constructor_named_methods_keep_metadata_and_complete_inventory(
    tmp_path: Path,
    member: str,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {member} }}"
    facts = _collected(tmp_path, source + DECORATORS)
    method_record = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "method"
    )
    assert method_record.data.get("decorators") == ("@Get()",)
    assert method_record.data.get("qualified_name") == f"{QUALIFIED}.{spelling}"
    comparison = compare_graphs(_graph_from_source_facts(facts, ("src",)), _target((spelling,)))
    assert comparison.status == "PASS"


@pytest.mark.parametrize(
    "spelling", [r'"constr\\u0075ctor"', r'"cons\tructor"', r'"constr\u00FCctor"']
)
def test_constructor_escape_recognition_does_not_reinterpret_other_member_names(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {spelling}(): void {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((spelling,))).status == "PASS"


@pytest.mark.parametrize(
    "spelling",
    [
        r'"constr\u{110000}ctor"',
        r'"constr\u{FFFFFFFF}ctor"',
        r'"constr\u{000000110000}ctor"',
        r"constr\u{110000}ctor",
        r'static "constr\u{110000}ctor"',
        r'"constr\u{}ctor"',
    ],
)
def test_invalid_unicode_member_names_cannot_close_a_decorated_inventory(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {spelling}() {{}} }}"
    name = spelling.removeprefix("static ")
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((name,))).status == "UNKNOWN"


@pytest.mark.parametrize(
    "spelling",
    [
        r"constr\u{20}uctor",
        r"constr\u0020uctor",
        r"constr\u{D800}uctor",
        r"\u{30}ctor",
        r"constr\u{30}uctor",
    ],
)
def test_unvalidated_escaped_identifiers_keep_decorated_inventory_unknown(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {spelling}() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((spelling,))).status == "UNKNOWN"


@pytest.mark.parametrize(
    "spelling",
    [
        r'"constr\u{20}uctor"',
        r'"constr\u0020uctor"',
        r'"constr\u{D800}uctor"',
        r'"\u{30}ctor"',
        r'"constr\u{30}uctor"',
    ],
)
def test_quoted_string_names_retain_their_distinct_unicode_character_rules(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() {spelling}() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((spelling,))).status == "PASS"


@pytest.mark.parametrize(
    "spelling",
    [
        r"constr\u{20}uctor",
        r"constr\u0020uctor",
        r"\u{30}ctor",
        r'"constr\u{110000}uctor"',
        r'"constr\u{000000110000}uctor"',
    ],
)
def test_decorated_class_cannot_close_an_invalid_undecorated_method_name(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() run() {{}} {spelling}() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(("run", spelling, "missing")))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize("spelling", [r'"constr\u{20}uctor"', r'"constr\u{D800}uctor"'])
def test_decorated_class_retains_valid_undecorated_quoted_method_names(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ @Get() run() {{}} {spelling}() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target(("run", spelling))).status == "PASS"


@pytest.mark.parametrize(
    "constructor,status",
    [
        ("'constructor'(private repo: string)", "FAIL"),
        ('"constructor"(protected repo: string)', "FAIL"),
        ("constructor(readonly repo: string)", "FAIL"),
        ("'constructor'(readonly repo: string)", "FAIL"),
        (r'"constr\u{00000075}ctor"(private repo: string)', "UNKNOWN"),
    ],
)
def test_mixed_decorator_closed_target_detects_supported_constructor_properties(
    tmp_path: Path,
    constructor: str,
    status: str,
) -> None:
    source = f"class Endpoint {{ {constructor} {{}} @Get() run() {{}} }}"
    facts = _collected(tmp_path, source + DECORATORS)
    graph = _graph_from_source_facts(facts, ("src",))
    comparison = compare_graphs(graph, _target((), kind="attribute"))
    assert comparison.status == status


@pytest.mark.parametrize("spelling", ["constructor", "'constructor'", r'"constr\u{00000075}ctor"'])
def test_mixed_decorator_static_constructor_named_method_has_no_instance_properties(
    tmp_path: Path,
    spelling: str,
) -> None:
    source = f"class Endpoint {{ static {spelling}(repo: string) {{}} @Get() run() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((), kind="attribute")).status == "PASS"


@pytest.mark.parametrize(
    "constructor",
    [
        "async constructor() {}",
        "*constructor() {}",
        "get constructor() { return ''; }",
        "set constructor(value: string) {}",
    ],
)
def test_mixed_decorator_cannot_certify_unsupported_instance_constructor_shapes(
    tmp_path: Path,
    constructor: str,
) -> None:
    source = f"class Endpoint {{ {constructor} @Get() run() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((), kind="attribute")).status == "UNKNOWN"


@pytest.mark.parametrize(
    "constructor",
    [
        "constructor(private repo: string)",
        "'constructor'(private repo: string)",
        "constructor(readonly repo: string)",
        '"constructor"(readonly repo: string)',
    ],
)
def test_constructor_signatures_keep_uncollected_property_inventory_partial(
    tmp_path: Path,
    constructor: str,
) -> None:
    source = f"class Endpoint {{ {constructor}; @Get() run() {{}} }}"
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    assert compare_graphs(graph, _target((), kind="attribute")).status == "UNKNOWN"


def test_constructor_overload_bindings_remain_ambiguous_in_a_decorated_class(
    tmp_path: Path,
) -> None:
    source = (
        "class Endpoint { constructor(repo: string); constructor(repo: string) {} @Get() run() {} }"
    )
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(("constructor", "run")))
    assert comparison.status == "UNKNOWN"
    assert any(
        item.status == "UNKNOWN" and item.change == "ambiguous" for item in comparison.assessments
    )


@pytest.mark.parametrize(
    "names,status",
    [
        (("run", "plain"), "PASS"),
        (("run",), "FAIL"),
        (("run", "plain", "missing"), "FAIL"),
    ],
)
def test_decorated_closed_methods_detect_known_presence_extra_and_absence(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    graph = _graph_from_source_facts(_collected(tmp_path, SOURCE + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(names))
    assert comparison.status == status
    assert not any(item.status == "UNKNOWN" for item in comparison.assessments)


def test_duplicate_decorated_owners_keep_closed_inventory_unknown(tmp_path: Path) -> None:
    graph = _graph_from_source_facts(
        _collected(tmp_path, "class Endpoint { @Get() run() {} } class Endpoint {}" + DECORATORS),
        ("src",),
    )
    comparison = compare_graphs(graph, _target(("run",)))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize(
    "member",
    [
        "@Get() [key]() {}",
        "@Get() run() {} static { initialize(); }",
        "@Get()",
    ],
)
def test_unsupported_decorated_inventory_cannot_prove_member_absence(
    tmp_path: Path,
    member: str,
) -> None:
    graph = _graph_from_source_facts(
        _collected(tmp_path, f"class Endpoint {{ {member} }}" + DECORATORS),
        ("src",),
    )
    names = ("run", "missing", "constructor") if "constructor" in member else ("run", "missing")
    comparison = compare_graphs(graph, _target(names))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize(
    "names,status", [(("token",), "PASS"), ((), "FAIL"), (("token", "missing"), "FAIL")]
)
def test_decorated_closed_attributes_detect_extra_and_missing_fields(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    graph = _graph_from_source_facts(_collected(tmp_path, SOURCE + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(names, kind="attribute"))
    assert comparison.status == status
    assert not any(item.status == "UNKNOWN" for item in comparison.assessments)


def test_unchanged_nest_app_controller_has_a_complete_direct_method_inventory(
    tmp_path: Path,
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures/L-nest-realworld/src/app.controller.ts"
    package = fixture.parents[1] / "resolver-inputs/@nestjs/common"
    facts = _collected_files(
        tmp_path,
        {
            "src/main.ts": fixture.read_text(),
            **{
                f"node_modules/@nestjs/common/{name}": (package / name).read_text()
                for name in ("package.json", "index.js", "index.d.ts")
            },
        },
    )
    symbols = {
        record.data.get("name"): record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    }
    assert symbols["AppController"].data.get("decorators") == ("@Controller('api')",)
    assert symbols["root"].data.get("decorators") == ("@Get()",)
    methods = [
        item
        for item in symbols["AppController"].data.get("member_inventories")
        if item.get("kind") == "method"
    ]
    assert len(methods) == 1 and methods[0].get("status") == "complete"
    assert methods[0].get("definition_ids") == (symbols["root"].id,)
    graph = _graph_from_source_facts(facts, ("src",))
    comparison = compare_graphs(
        graph,
        _target(("root",), qualified="app.src.main_x2e_ts.AppController"),
    )
    assert comparison.status == "PASS"


@pytest.mark.parametrize(
    "names,status",
    [
        (("run", "plain"), "PASS"),
        (("run",), "FAIL"),
        (("run", "plain", "missing"), "FAIL"),
    ],
)
def test_decorated_inventory_live_and_saved_reports_agree(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    root, config = _project(tmp_path / "decorated", matching=True)
    (root / "src/main.ts").write_text(SOURCE + DECORATORS)
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_text())
    qualified = "demo.src.main_x2e_ts.Endpoint"
    entities = [
        {
            "id": "endpoint",
            "kind": "class",
            "qualified_name": qualified,
            "language": "typescript",
            "presence": "planned",
            "provenance": ["docs/target.md"],
            "responsibilities": ["Own the direct endpoint methods."],
        },
        *(
            {
                "id": name,
                "kind": "method",
                "qualified_name": f"{qualified}.{name}",
                "parent_id": "endpoint",
                "language": "typescript",
                "presence": "planned",
                "provenance": ["docs/target.md"],
                "responsibilities": ["Handle a request."],
            }
            for name in names
        ),
    ]
    contract["declarations"]["uml"] = {
        "schema_version": "1.0.0",
        "entities": entities,
        "scopes": [
            {
                "scope_id": "endpoint",
                "mode": "closed",
                "entity_kinds": ["method"],
                "rationale": "All direct methods.",
                "provenance": ["docs/target.md"],
            }
        ],
    }
    contract_path.write_text(json.dumps(contract))
    result, encoded = _live(root, config)
    assert encoded is not None
    comparison = architecture_report(
        parse_observation(decode_canonical_model(json.loads(encoded)))
    ).comparison
    assert comparison is not None and comparison.status == status
    path = root / "architecture.json"
    path.write_bytes(encoded)
    saved = run_saved_report(path)
    assert saved.rule_assessments == result.rule_assessments
    assert saved.architecture_projection == result.architecture_projection
    assert saved.declared_rules == result.declared_rules == status
    assert saved.exit_code == result.exit_code


@pytest.mark.parametrize("names", [("run",), ("run", "missing")])
def test_missing_decorator_binding_cannot_certify_closed_inventory(tmp_path, names):
    facts = _collected(tmp_path, "class Endpoint { @Get() run() {} }")
    assert len(facts.coverage.gaps) == 1
    gap = facts.coverage.gaps[0]
    assert gap.kind == "source_resolution_gap"
    assert gap.data.get("resolution_dimension") == "imports"
    assert gap.data.get("module") == "app.src.main_x2e_ts"
    comparison = compare_graphs(_graph_from_source_facts(facts, ("src",)), _target(names))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)
