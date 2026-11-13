# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript inner facts stay within source syntax and local binding evidence."""

import json
from pathlib import Path

import pytest
from native_typescript import collect
from test_source_graph import _graph_from_source_facts

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
        "expected-type": "PASS",
        "expected-value": "PASS",
    }
    assert {item.target_id: item.observed_ids for item in comparison.correspondences} == {
        "expected-type": (next(record.id for record in symbols if record.kind == "type_alias"),),
        "expected-value": (constant.id,),
    }
    assert all(item.change == "matched" for item in comparison.assessments)


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
