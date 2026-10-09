# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript inner facts stay within source syntax and local binding evidence."""

import json
from pathlib import Path

import pytest
from test_source_graph import _graph_from_source_facts

from archkeel.analyzer.typescript.collect import collect
from archkeel.analyzer.typescript.parse import parse
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings


def _collected(tmp_path: Path, source: str):
    return _collected_files(tmp_path, {"src/main.ts": source})


def _collected_files(tmp_path: Path, files: dict[str, str]):
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"module": "CommonJS", "moduleResolution": "Node"},
                "include": ["src"],
            }
        ),
        encoding="utf-8",
    )
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    return facts


def test_parser_records_declarations_members_signatures_and_source_sites() -> None:
    syntax = parse(
        "src/core.ts",
        b"""export interface Port { run(value: number): string; }
export class Client extends Base implements Port {
  private token: string = '';
  static limit = 10;
  static reset(): void {}
  run(value: number): string { return helper(value); }
}
export enum State { READY = 'ready' }
export type Text = string;
export const VERSION = 1;
export function build(): Client { const client = new Client(); return client; }
""",
    )
    assert [(item.kind, item.name, item.parent) for item in syntax.definitions] == [
        ("interface", "Port", None),
        ("method", "run", "Port"),
        ("class", "Client", None),
        ("method", "reset", "Client"),
        ("method", "run", "Client"),
        ("enum", "State", None),
        ("type_alias", "Text", None),
        ("constant", "VERSION", None),
        ("function", "build", None),
    ]
    client = next(item for item in syntax.definitions if item.name == "Client")
    assert [(base.name, base.relationship) for base in client.bases] == [
        ("Base", "inherits"),
        ("Port", "realizes"),
    ]
    assert [(field.name, field.static, field.literal) for field in client.members] == [
        ("token", False, "''"),
        ("limit", True, "10"),
    ]
    state = next(item for item in syntax.definitions if item.name == "State")
    assert [(field.name, field.literal) for field in state.members] == [("READY", "'ready'")]
    assert [
        (site.kind, site.expression, site.scope, site.assigned_name)
        for site in syntax.sites
        if site.kind != "reference"
    ] == [
        ("call", "helper", "Client.run", None),
        ("new", "Client", "build", "client"),
    ]
    assert syntax.definitions[-1].parameters == ()
    assert syntax.definitions[-1].returns == "Client"


def test_typescript_visibility_uses_module_exports_without_inheriting_member_visibility(
    tmp_path: Path,
) -> None:
    facts = _collected(
        tmp_path,
        "function hidden() {}\n"
        "function visible() {}\n"
        "interface LocalPort { field: string; }\n"
        "type LocalType = string;\n"
        "export { visible as publicVisible, type LocalType as PublicType };\n"
        "export class InlineExport { field: string; }\n",
    )
    symbols = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    ]
    by_name = {record.data.get("name"): record for record in symbols}

    assert by_name["hidden"].data.get("visibility_detail").get("kind") == "private"
    assert by_name["visible"].data.get("visibility_detail").get("kind") == "public"
    assert by_name["LocalPort"].data.get("visibility_detail").get("kind") == "private"
    assert by_name["LocalType"].data.get("visibility_detail").get("kind") == "public"
    assert by_name["InlineExport"].data.get("visibility_detail").get("kind") == "public"
    local_port = by_name["LocalPort"].data.get("attribute_declarations")
    assert local_port[0].get("visibility").get("kind") == "public"


@pytest.mark.parametrize(
    "source",
    [
        "function globalScriptDeclaration() {}\n",
        "function hidden() {}\nexport = hidden;\n",
    ],
)
def test_unclassified_script_or_export_syntax_does_not_claim_module_private_visibility(
    tmp_path: Path, source: str
) -> None:
    facts = _collected(tmp_path, source)
    symbol = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.data.get("name") in {"globalScriptDeclaration", "hidden"}
    )
    assert symbol.data.get("visibility_detail").get("kind") == "unknown"
    assert symbol.data.get("visibility_detail").get("basis") == "unknown"


def test_identifier_const_keeps_value_space_separate_from_same_name_type_alias(
    tmp_path: Path,
) -> None:
    facts = _collected(
        tmp_path,
        "const DriverEntityManager = 1;\n"
        "export type EntityManager = number;\n"
        "export const EntityManager: EntityManager = DriverEntityManager;\n",
    )
    symbols = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.data.get("qualified_name", "").endswith(".EntityManager")
    ]
    assert {record.kind for record in symbols} == {"type_alias", "constant"}
    assert len({record.id for record in symbols}) == 2
    constant = next(record for record in symbols if record.kind == "constant")
    assert constant.data.get("annotation") == "EntityManager"
    assert constant.data.get("visibility_detail").get("kind") == "public"

    observed = _graph_from_source_facts(facts, ("src",))
    target = ArchitectureGraph(
        "declared",
        entities=(
            Entity(
                "expected-type",
                "type_alias",
                "app.src.main_x2e_ts.EntityManager",
                "typescript",
                presence="planned",
                provenance=("docs/target.md",),
            ),
            Entity(
                "expected-value",
                "constant",
                "app.src.main_x2e_ts.EntityManager",
                "typescript",
                presence="planned",
                provenance=("docs/target.md",),
            ),
        ),
    )
    comparison = compare_graphs(observed, target)
    assert {item.subject_id: item.status for item in comparison.assessments} == {
        "expected-type": "UNKNOWN",
        "expected-value": "UNKNOWN",
    }
    assert all(item.change == "ambiguous" for item in comparison.assessments)
    assert not any(item.status == "FAIL" for item in comparison.assessments)


def test_identifier_const_alias_does_not_prove_call_or_constructor_dispatch(tmp_path: Path) -> None:
    facts = _collected(
        tmp_path,
        "export function makeUser(): object { return {}; }\n"
        "export type Alias = string;\n"
        "export const Alias = makeUser;\n"
        "export const Called = makeUser();\n"
        "export const Arrow = () => makeUser();\n"
        "function callAlias() { Alias(); new Alias(); }\n"
        "function use(Alias: () => void) { Alias(); makeUser(); }\n",
    )
    symbols = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    ]
    assert any(
        record.kind == "constant" and record.data.get("name") == "Alias" for record in symbols
    )
    alias_constant = next(
        record
        for record in symbols
        if record.kind == "constant" and record.data.get("name") == "Alias"
    )
    assert alias_constant.data.get("annotation") is None
    assert alias_constant.data.get("initializer") is None
    assert not {"Called", "Arrow"} & {record.data.get("name") for record in symbols}

    calls = [
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
    ]
    alias_call = next(
        record
        for record in calls
        if record.data.get("expression") == "Alias"
        and record.data.get("source_scope", "").endswith(".callAlias")
        and record.data.get("construction") is None
    )
    assert alias_call.data.get("status") == "unresolved"
    alias_new = next(
        record
        for record in calls
        if record.data.get("expression") == "Alias"
        and record.data.get("source_scope", "").endswith(".callAlias")
        and record.data.get("construction") is not None
    )
    assert alias_new.data.get("construction").get("status") == "unresolved"
    shadowed_call = next(
        record
        for record in calls
        if record.data.get("expression") == "Alias"
        and record.data.get("source_scope", "").endswith(".use")
    )
    assert shadowed_call.data.get("status") == "unresolved"
    direct_call = next(record for record in calls if record.data.get("expression") == "makeUser")
    assert direct_call.data.get("status") == "resolved"


def test_parser_preserves_only_lexical_async_modifiers() -> None:
    syntax = parse(
        "main.ts",
        b"class Service { async run(): Promise<void> {} namedAsync(): Promise<void> {} "
        b"async(): void {} }\n"
        b"export async function load(): Promise<void> {}\n"
        b"export function promiseOnly(): Promise<void> {}\n",
    )
    by_name = {item.name: item.is_async for item in syntax.definitions}
    assert by_name == {
        "Service": False,
        "run": True,
        "namedAsync": False,
        "async": False,
        "load": True,
        "promiseOnly": False,
    }


def test_parser_type_only_export_clauses_do_not_prove_runtime_exports() -> None:
    syntax = parse(
        "main.ts",
        b"class ClassType {}\ninterface InterfaceType {}\n"
        b"type AliasType = string;\n"
        b"export { type ClassType, type InterfaceType as PublicInterface };\n"
        b"export type { AliasType as PublicAlias };\n",
    )
    definitions = {item.name: item for item in syntax.definitions}
    assert definitions["ClassType"].exported is False
    assert definitions["InterfaceType"].exported is False
    assert definitions["AliasType"].exported is False
    assert {
        definitions[name].visibility for name in ("ClassType", "InterfaceType", "AliasType")
    } == {"public"}


def test_type_only_export_forms_do_not_resolve_value_import_calls(tmp_path: Path) -> None:
    facts = _collected_files(
        tmp_path,
        {
            "src/types.ts": (
                "class ClauseExport {}\n"
                "class StatementExport {}\n"
                "function localFunction() {}\n"
                "export { type ClauseExport };\n"
                "export type { StatementExport };\n"
                "export { localFunction };\n"
            ),
            "src/main.ts": (
                "import { ClauseExport, StatementExport, localFunction } from './types';\n"
                "new ClauseExport();\n"
                "ClauseExport();\n"
                "new StatementExport();\n"
                "StatementExport();\n"
                "localFunction();\n"
            ),
        },
    )
    types = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.data.get("module") == "app.src.types_x2e_ts"
        and record.data.get("name") == "ClauseExport"
    )
    statement = next(
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.data.get("module") == "app.src.types_x2e_ts"
        and record.data.get("name") == "StatementExport"
    )
    assert types.data.get("visibility_detail").get("kind") == "public"
    assert statement.data.get("visibility_detail").get("kind") == "public"

    calls = [
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("source_module") == "app.src.main_x2e_ts"
    ]
    assert len(calls) == 5
    assert all(
        record.data.get("status") == "unresolved"
        for record in calls
        if record.data.get("expression") != "localFunction"
    )
    assert (
        next(
            record for record in calls if record.data.get("expression") == "localFunction"
        ).data.get("status")
        == "resolved"
    )
    assert all(
        record.data.get("construction").get("status") == "unresolved"
        for record in calls
        if record.data.get("construction") is not None
    )


def test_aliased_exports_do_not_prove_same_name_runtime_exports(tmp_path: Path) -> None:
    facts = _collected_files(
        tmp_path,
        {
            "src/renamed.ts": (
                """function original() {}
export {
  original as renamed,
  original as default,
  original as "string-name"
};
"""
            ),
            "src/main.ts": (
                "import { original, renamed } from './renamed';\noriginal();\nrenamed();\n"
            ),
        },
    )
    symbols = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.data.get("module") == "app.src.renamed_x2e_ts"
        and record.data.get("name") == "original"
    ]
    assert len(symbols) == 1
    assert symbols[0].data.get("visibility_detail").get("kind") == "public"
    assert symbols[0].data.get("exported") is not True

    calls = [
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
        if record.data.get("source_module") == "app.src.main_x2e_ts"
    ]
    assert {record.data.get("expression") for record in calls} == {"original", "renamed"}
    assert all(record.data.get("status") == "unresolved" for record in calls)


def test_overloads_and_computed_construction_remain_separate_syntax_sites() -> None:
    syntax = parse(
        "main.ts",
        b"function make(value: string): Port;\nfunction make(value: number): Port;\n"
        b"function make(value: unknown): Port { return new (pick())(); }\n",
    )
    assert [(item.name, item.span.line) for item in syntax.definitions] == [
        ("make", 1),
        ("make", 2),
        ("make", 3),
    ]
    assert [(site.kind, site.expression) for site in syntax.sites if site.kind != "reference"] == [
        ("new", "(pick())"),
        ("call", "pick"),
    ]


def test_import_binding_and_local_shadow_names_are_separate_from_module_edges() -> None:
    syntax = parse(
        "main.ts",
        b"import Default, { helper as run } from './helper';\n"
        b"import * as model from './model';\n"
        b"function work(helper: () => void) { run(); helper(); model.Unit; }\n",
    )
    assert [(item.imported, item.local, item.namespace) for item in syntax.import_bindings] == [
        ("default", "Default", False),
        ("helper", "run", False),
        ("*", "model", True),
    ]
    calls = [site for site in syntax.sites if site.kind == "call"]
    assert [(site.name, site.shadowed_names) for site in calls] == [
        ("run", ("helper",)),
        ("helper", ("helper",)),
    ]
    assert any(
        site.kind == "reference" and site.name == "Unit" and site.receiver == "model"
        for site in syntax.sites
    )


def test_type_only_specifiers_are_retained_per_import_binding() -> None:
    syntax = parse(
        "main.ts",
        b'import type { TypeOnly } from "./model";\n'
        b'import { type MixedType, runtimeValue } from "./model";\n',
    )
    assert [(item.local, item.type_only) for item in syntax.import_bindings] == [
        ("TypeOnly", True),
        ("MixedType", True),
        ("runtimeValue", False),
    ]


def test_computed_members_and_parameter_properties_keep_member_inventory_partial() -> None:
    syntax = parse(
        "main.ts",
        b"class C { [key](): void {} constructor(private token: string) {} }",
    )
    classifier = next(item for item in syntax.definitions if item.name == "C")
    assert classifier.members_complete is False


def test_nested_class_bases_are_not_attributed_to_the_outer_class() -> None:
    syntax = parse(
        "main.ts",
        b"class Outer { method() { class Inner extends Base {} } }",
    )
    outer = next(item for item in syntax.definitions if item.name == "Outer")
    inner = next(item for item in syntax.definitions if item.name == "Inner")
    assert outer.bases == ()
    assert [(item.name, item.relationship) for item in inner.bases] == [("Base", "inherits")]


def test_anonymous_callbacks_and_object_methods_are_not_named_scopes() -> None:
    syntax = parse(
        "main.ts",
        b"function work() { const callback = (helper: () => void) => helper(); "
        b"const object = { run(helper: () => void) { helper(); } }; }",
    )
    assert not any(item.name == "run" and item.kind == "method" for item in syntax.definitions)
    calls = [item for item in syntax.sites if item.kind == "call" and item.name == "helper"]
    assert len(calls) == 2
    assert all(item.scope_ambiguous for item in calls)
    assert all("helper" in item.shadowed_names for item in calls)


def test_parser_error_regions_do_not_create_inner_declarations_or_sites() -> None:
    syntax = parse(
        "main.ts",
        b"export class Good {}\nexport class = ;\nfunction bad() { return new Missing(); }\n",
    )
    assert syntax.first_error is not None
    assert [(item.kind, item.name) for item in syntax.definitions] == [
        ("class", "Good"),
        ("function", "bad"),
    ]
    assert [(site.kind, site.expression) for site in syntax.sites if site.kind != "reference"] == [
        ("new", "Missing")
    ]


def test_interface_heritage_private_names_bare_enum_members_and_partial_signatures() -> None:
    syntax = parse(
        "main.ts",
        b"interface Child extends First, Second { run(value?: string): void; }\n"
        b"enum State { READY, STOPPED }\nclass Token { #token: string; }\n",
    )
    child = next(item for item in syntax.definitions if item.name == "Child")
    method = next(item for item in syntax.definitions if item.name == "run")
    state = next(item for item in syntax.definitions if item.name == "State")
    token = next(item for item in syntax.definitions if item.name == "Token")
    assert [(base.name, base.relationship) for base in child.bases] == [
        ("First", "inherits"),
        ("Second", "inherits"),
    ]
    assert method.signature_complete is False
    assert [member.name for member in state.members] == ["READY", "STOPPED"]
    assert [(member.name, member.visibility) for member in token.members] == [("#token", "private")]


def test_namespace_and_class_expression_members_are_not_assigned_false_owners() -> None:
    syntax = parse(
        "main.ts",
        b"namespace N { export class C { method() { helper(); } } }\n"
        b"function outer() { const value = class { run() { helper(); } }; }\n",
    )
    assert not any(item.name in {"N", "C", "method", "run"} for item in syntax.definitions)
    assert all(site.scope_ambiguous for site in syntax.sites if site.name == "helper")


def test_overloads_merged_interfaces_and_shadowed_construction_validate(tmp_path) -> None:
    facts = _collected(
        tmp_path,
        "interface Port { first(): void }\n"
        "interface Port { second(): void }\n"
        "function overloaded(value: string): string;\n"
        "function overloaded(value: unknown) { helper(); }\n"
        "overloaded(1);\n"
        "function helper() {}\n"
        "class Unit {}\n"
        "const Base = makeBase();\nclass Inherits extends Base {}\n"
        "function shadowed(Unit: unknown) { const item = new Unit(); }\n"
        "if (flag) { class Hidden {} }\n"
        "new Hidden();\n",
    )
    symbols = next(section.records for section in facts.sections if section.name == "symbols")
    assert not any(item.data.get("name") == "Hidden" for item in symbols)
    ports = [
        item for item in symbols if item.data.get("qualified_name") == "app.src.main_x2e_ts.Port"
    ]
    assert len(ports) == 2
    assert all(
        all(
            inventory.get("status") == "partial"
            for inventory in item.data.get("member_inventories", ())
        )
        for item in ports
    )
    evidence = {item.id: item for item in facts.evidence}
    overload_body = next(
        item
        for item in symbols
        if item.data.get("qualified_name") == "app.src.main_x2e_ts.overloaded"
        and evidence[item.evidence_ids[0]].line == 4
    )
    calls = next(section.records for section in facts.sections if section.name == "calls")
    overloaded_call = next(item for item in calls if item.data.get("expression") == "overloaded")
    assert overloaded_call.data.get("status") == "partially_resolved"
    helper = next(item for item in calls if item.data.get("expression") == "helper")
    assert helper.data.get("source_definition_id") == overload_body.id
    constructions = [
        item.data.get("construction") for item in calls if item.data.get("expression") == "Unit"
    ]
    assert constructions and all(item.get("status") == "unresolved" for item in constructions)
    hidden = next(item for item in calls if item.data.get("expression") == "Hidden")
    assert hidden.data.get("targets") == ()
    inherits = next(
        item
        for item in symbols
        if item.data.get("qualified_name") == "app.src.main_x2e_ts.Inherits"
    )
    assert inherits.data.get("base_declarations")[0].get("status") == "unresolved"


def test_type_only_import_does_not_resolve_value_construction(tmp_path) -> None:
    (tmp_path / "src/model.ts").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/model.ts").write_text("export class C {}\n", encoding="utf-8")
    facts = _collected(
        tmp_path,
        'import { type C, runtimeValue } from "./model";\nnew C(); runtimeValue();\n',
    )
    calls = next(section.records for section in facts.sections if section.name == "calls")
    construction = next(item for item in calls if item.data.get("expression") == "C")
    assert construction.data.get("targets") == ()
    assert construction.data.get("construction").get("status") == "unresolved"


def test_this_field_references_resolve_to_unique_own_member(tmp_path) -> None:
    facts = _collected(
        tmp_path,
        "class Client { private _token = ''; run() { this._token = ''; return this._token; } }\n",
    )
    references = next(section.records for section in facts.sections if section.name == "references")
    token_sites = [item for item in references if item.data.get("expression") == "this._token"]
    assert len(token_sites) == 2
    assert all(item.data.get("status") == "resolved" for item in token_sites)
    assert all(
        item.data.get("targets") == ("app.src.main_x2e_ts.Client._token",) for item in token_sites
    )
