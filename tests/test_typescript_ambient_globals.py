# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`types` adds globals, and a project `declare` publishes its name (AD-274, #682)."""

import json

import pytest

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings

ENVIRONMENT = {"target": "ES2022", "lib": ["ES2023", "DOM", "DOM.Iterable"]}
USE = "export const used = NAME;\n"


def _facts(tmp_path, files, compiler=None):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    options = {**ENVIRONMENT, **(compiler or {})}
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": options, "include": ["src"]})
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings(),
        )
    )
    # The collector hands its facts to this check; a record that cites another file crashes a run.
    validate_source_facts(facts)
    return facts


def _gaps(facts, name):
    return [
        gap for gap in facts.coverage.gaps if f"Script global {name} " in gap.data.get("reason", "")
    ]


def _reads(facts, name):
    rows = next(item.records for item in facts.sections if item.name == "imports")
    return [row for row in rows if row.data.get("specifier") == name]


def _published(tmp_path, declaration, *, path="src/globals.d.ts", name="NAME", compiler=None):
    facts = _facts(tmp_path, {path: declaration, "src/use.ts": USE.replace("NAME", name)}, compiler)
    assert _reads(facts, name)
    return not _gaps(facts, name)


@pytest.mark.parametrize(
    "compiler",
    [
        {},
        {"types": []},
        {"types": ["vite/client"]},
        {"types": ["vite/client", "node", "vitest/globals"]},
        {"typeRoots": ["./ambient"]},
        {"types": ["node"], "typeRoots": ["./ambient"]},
    ],
)
def test_types_keep_the_catalog_and_leave_unlisted_names_unproved(tmp_path, compiler):
    source = "export const m = Math.max(1, 2); export const d = document; export const p = process;"
    facts = _facts(tmp_path, {"src/use.ts": source}, compiler)
    assert not _gaps(facts, "Math") and not _gaps(facts, "document")
    assert _gaps(facts, "process")


@pytest.mark.parametrize(
    "compiler",
    [
        {"libReplacement": True},
        {"noLib": True, "lib": None},
        {"lib": ["es2022", "unobserved.library"]},
    ],
)
def test_options_that_change_the_meaning_of_a_lib_still_switch_the_catalog_off(tmp_path, compiler):
    facts = _facts(tmp_path, {"src/use.ts": "export const m = Math.max(1, 2);"}, compiler)
    assert _gaps(facts, "Math")


@pytest.mark.parametrize(
    "declaration",
    [
        "declare var NAME: string;",
        "declare let NAME: string;",
        "declare const NAME: string;",
        "declare function NAME(): string;",
        "declare class NAME {}",
        "declare abstract class NAME {}",
        "declare namespace NAME { const inner: string }",
        "declare namespace NAME.Inner { }",
        "declare module NAME { }",
        "declare enum NAME { a }",
        "declare const enum NAME { a }",
        "declare const OTHER: string, NAME: string;",
        "declare const NAME: string;\ndeclare const NAME: string;",
        "declare function NAME(a: 1): void;\ndeclare function NAME(a: 2): void;",
        "export {};\ndeclare global { const NAME: string }",
        "export {};\ndeclare global { var NAME: string }",
        "export {};\ndeclare global { function NAME(): void }",
        "export {};\ndeclare global { class NAME {} }",
        "export {};\ndeclare global { namespace NAME { } }",
        "export {};\ndeclare global { enum NAME { a } }",
        "import type {} from './other';\ndeclare global { const NAME: string }",
    ],
)
def test_each_kind_of_global_declaration_publishes_its_name(tmp_path, declaration):
    assert _published(tmp_path, declaration)


@pytest.mark.parametrize(
    "declaration",
    [
        "export {};\ndeclare const NAME: string;",
        "export declare const NAME: string;",
        "import type {} from './other';\ndeclare const NAME: string;",
        "export {};\ndeclare function NAME(): void;",
        "declare namespace Holder { const NAME: string }",
        "declare module 'package' { const NAME: string }",
        "declare interface NAME {}",
        "type NAME = string;",
        "declare const OTHER: string;",
    ],
)
def test_a_module_local_or_nested_or_type_only_declaration_publishes_nothing(tmp_path, declaration):
    assert not _published(tmp_path, declaration)


def test_a_script_ts_file_without_import_or_export_declares_globals_too(tmp_path):
    assert _published(tmp_path, "declare const NAME: string;", path="src/env.ts")


def test_the_use_is_backed_by_a_fact_that_cites_the_declaration(tmp_path):
    facts = _facts(
        tmp_path,
        {"src/globals.d.ts": "\n\ndeclare const NAME: string;\n", "src/use.ts": USE},
    )
    (row,) = _reads(facts, "NAME")
    cited = {item.id: item for item in facts.evidence}
    assert {(cited[item].file, cited[item].line) for item in row.evidence_ids} == {
        ("src/use.ts", 1)
    }
    bindings = next(item.records for item in facts.sections if item.name == "bindings")
    (fact,) = [item for item in bindings if item.id in row.fact_ids]
    assert fact.data.get("script_global") == "NAME"
    assert {(cited[item].file, cited[item].line) for item in fact.evidence_ids} == {
        ("src/globals.d.ts", 3)
    }
    assert row.data.get("target_module") == "NAME" and not row.data.get("symbols_known")


@pytest.mark.parametrize(
    "extra",
    [
        {"src/broken.ts": "export const = ;"},
        {"src/write.ts": "window.NAME = 1;"},
        {"src/write.ts": "globalThis.NAME = 1;"},
        {"src/write.ts": "NAME = 1;"},
        {"src/shadow.ts": "export const NAME = 1;"},
        {"src/shadow.ts": "export function NAME() {}"},
    ],
)
def test_the_conditions_of_a_standard_global_apply_to_a_declared_one(tmp_path, extra):
    files = {"src/globals.d.ts": "declare const NAME: string;", "src/use.ts": USE, **extra}
    assert _gaps(_facts(tmp_path, files), "NAME")


def test_a_runtime_publisher_of_the_name_is_decided_by_the_publisher_rule(tmp_path):
    files = {
        "src/publisher.js": "var NAME = (function () { return { go() {} }; })();\n",
        "src/use.ts": USE,
    }
    assert not _gaps(_facts(tmp_path, files, {"allowJs": True}), "NAME")
    # The `declare var` of the publisher binds the name in its own file, as it did before AD-274.
    files["src/globals.d.ts"] = "declare var NAME: { go(): void };"
    assert _gaps(_facts(tmp_path, files, {"allowJs": True}), "NAME")


def test_a_directive_for_types_creates_no_gap_and_other_directives_keep_theirs(tmp_path):
    files = {
        "src/a.d.ts": '/// <reference types="vite/client" />\ndeclare const NAME: string;',
        "src/b.d.ts": '/// <reference path="./a.d.ts" />\n',
        "src/c.d.ts": '/// <reference lib="dom" />\n',
        "src/use.ts": USE,
    }
    reasons = [gap.data.get("reason", "") for gap in _facts(tmp_path, files).coverage.gaps]
    assert not any("vite/client" in reason for reason in reasons)
    assert any("./a.d.ts" in reason for reason in reasons)
    assert any("Unobserved triple-slash reference: dom" in reason for reason in reasons)


def test_a_directive_after_the_first_statement_is_a_plain_comment(tmp_path):
    files = {"src/a.ts": 'export const a = 1;\n/// <reference types="vite/client" />\n'}
    assert not _facts(tmp_path, files).coverage.gaps


def test_a_vite_project_reports_only_what_the_catalog_and_declarations_cannot_prove(tmp_path):
    files = {
        "src/vite-env.d.ts": (
            '/// <reference types="vite/client" />\ndeclare const __APP_VERSION__: string;\n'
        ),
        "src/app.ts": (
            "export const v = __APP_VERSION__;\n"
            "export const w = () => { Math.max(1, 2); new Date(); return document.title; };\n"
            "export const e = import.meta.env;\n"
        ),
    }
    facts = _facts(
        tmp_path,
        files,
        {"types": ["vite/client", "node", "vitest/globals"], "moduleResolution": "bundler"},
    )
    assert not any("Script global" in gap.data.get("reason", "") for gap in facts.coverage.gaps)
    assert not any("triple-slash" in gap.data.get("reason", "") for gap in facts.coverage.gaps)
