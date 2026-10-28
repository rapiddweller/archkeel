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


def _facts(tmp_path, files, compiler=None, package_type=None):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    options = {**ENVIRONMENT, **(compiler or {})}
    if package_type is not None:
        (tmp_path / "package.json").write_text(json.dumps({"type": package_type}))
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
        {"src/shadow.ts": "const NAME = 1;"},
        {"src/shadow.ts": "function NAME() {}"},
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


def test_a_declared_global_read_through_an_alias_keeps_record_ids_unique(tmp_path):
    files = {
        "src/globals.d.ts": "declare const NAME: { go(): void };",
        "src/use.js": "(function () { const port = window.NAME; port.go(); })();\n",
    }
    facts = _facts(tmp_path, files, {"allowJs": True})
    assert not _gaps(facts, "NAME")


DECLARE = "declare const NAME: string;\n"
NODENEXT = {"module": "nodenext", "moduleResolution": "nodenext"}
NODE16 = {"module": "node16", "moduleResolution": "node16"}
# Verified with tsc 5.9.3: (files, compiler options, package type) -> is NAME global? The use file
# `src/use.ts` reads NAME; "global" means tsc finds it, "local" means tsc reports TS2304 or TS2552.
MODULE_OR_SCRIPT = {
    "d.ts script": ({"src/env.d.ts": DECLARE}, {}, None, True),
    "d.ts with export": ({"src/env.d.ts": "export {};\n" + DECLARE}, {}, None, False),
    "d.ts forced": ({"src/env.d.ts": DECLARE}, {"moduleDetection": "force"}, None, True),
    "d.mts script": ({"src/env.d.mts": DECLARE}, {}, None, True),
    "d.cts script": ({"src/env.d.cts": DECLARE}, {}, None, True),
    "ts script": ({"src/env.ts": DECLARE}, {}, None, True),
    "ts script, detection auto": ({"src/env.ts": DECLARE}, {"moduleDetection": "auto"}, None, True),
    "ts script, detection legacy": (
        {"src/env.ts": DECLARE},
        {"moduleDetection": "legacy"},
        None,
        True,
    ),
    "ts script, detection force": (
        {"src/env.ts": DECLARE},
        {"moduleDetection": "force"},
        None,
        False,
    ),
    "mts script": ({"src/env.mts": DECLARE}, {}, None, False),
    "cts script": ({"src/env.cts": DECLARE}, {}, None, False),
    "tsx script, react-jsx": ({"src/env.tsx": DECLARE}, {"jsx": "react-jsx"}, None, True),
    "ts script, module esnext": (
        {"src/env.ts": DECLARE},
        {"module": "esnext", "moduleResolution": "bundler"},
        None,
        True,
    ),
    "ts script, module preserve": (
        {"src/env.ts": DECLARE},
        {"module": "preserve", "moduleResolution": "bundler"},
        None,
        True,
    ),
    "ts script, nodenext, package module": ({"src/env.ts": DECLARE}, NODENEXT, "module", False),
    "ts script, nodenext, package commonjs": (
        {"src/env.ts": DECLARE},
        NODENEXT,
        "commonjs",
        False,
    ),
    "ts script, nodenext, no package type": ({"src/env.ts": DECLARE}, NODENEXT, None, False),
    "ts script, node16, package module": ({"src/env.ts": DECLARE}, NODE16, "module", False),
    "nested namespace in a script": (
        {"src/env.ts": "declare namespace NAME.B.C { const x: 1 }\n"},
        {},
        None,
        True,
    ),
    "declare global in a module": (
        {"src/env.ts": "export {};\ndeclare global { const NAME: string }\n"},
        {},
        None,
        True,
    ),
    "declare global in a forced module": (
        {"src/env.ts": "export {};\ndeclare global { const NAME: string }\n"},
        {"moduleDetection": "force"},
        None,
        True,
    ),
    "declare global in an mts file": (
        {"src/env.mts": "export {};\ndeclare global { const NAME: string }\n"},
        {},
        None,
        True,
    ),
    "exported declaration in declare global": (
        {"src/env.ts": "export {};\ndeclare global { export const NAME: string }\n"},
        {},
        None,
        True,
    ),
}


@pytest.mark.parametrize("case", MODULE_OR_SCRIPT)
def test_a_declaration_is_global_exactly_when_the_compiler_says_so(tmp_path, case):
    files, compiler, package_type, global_name = MODULE_OR_SCRIPT[case]
    facts = _facts(
        tmp_path,
        {**files, "src/use.ts": USE},
        {"allowJs": False, **compiler},
        package_type,
    )
    # The collector reads no global in the Node module modes, so "global" needs a read and no gap.
    assert (bool(_reads(facts, "NAME")) and not _gaps(facts, "NAME")) is global_name


@pytest.mark.parametrize(
    "module_file",
    [
        "export function open() {}",
        "function open() {}\nexport {};",
        "export const open = 1;",
        "const open = 1;\nexport {};",
    ],
)
def test_a_module_local_binding_of_a_catalog_name_is_not_a_second_publication(
    tmp_path, module_file
):
    files = {"src/a.ts": "export const go = () => window.open('/x');", "src/b.ts": module_file}
    facts = _facts(tmp_path, files)
    assert not _gaps(facts, "open")


def test_a_binding_in_a_global_script_still_blocks_a_catalog_name(tmp_path):
    files = {
        "src/a.ts": "export const go = () => window.open('/x');",
        "src/b.ts": "function open() {}",
    }
    assert _gaps(_facts(tmp_path, files), "open")


def test_a_module_local_declaration_under_forced_modules_does_not_block_a_global_one(tmp_path):
    files = {
        "src/env.d.ts": "declare const NAME: string;",
        "src/local.ts": "declare const NAME: number;",
        "src/use.ts": USE,
    }
    facts = _facts(tmp_path, files, {"moduleDetection": "force"})
    assert _reads(facts, "NAME") and not _gaps(facts, "NAME")


def test_a_script_binding_is_local_when_the_options_make_every_file_a_module(tmp_path):
    files = {
        "src/a.ts": "export const go = () => window.open('/x');",
        "src/b.ts": "function open() {}",
    }
    assert not _gaps(_facts(tmp_path, files, {"moduleDetection": "force"}), "open")
