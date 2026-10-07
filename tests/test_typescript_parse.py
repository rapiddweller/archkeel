# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The syntax reader names every module reference and every pattern it cannot read."""

import pytest

from archkeel.analyzer.typescript.parse import Syntax, parse


def _forms(syntax: Syntax) -> list[tuple[str, str | None, bool, bool]]:
    return [
        (item.form, item.specifier, item.type_only, item.module_level) for item in syntax.references
    ]


def _reasons(syntax: Syntax) -> list[str]:
    return sorted(item.reason for item in syntax.concerns)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import a, {b} from './a';", [("import", "./a", False, True)]),
        ("import type {A} from './a';", [("import", "./a", True, True)]),
        ("import {type A, type B} from './a';", [("import", "./a", True, True)]),
        ("import {type A, B} from './a';", [("import", "./a", False, True)]),
        ("import C, {type A} from './a';", [("import", "./a", False, True)]),
        ("import {} from './a';", [("import", "./a", False, True)]),
        ("import type {} from './a';", [("import", "./a", True, True)]),
        ("import './side';", [("import", "./side", False, True)]),
        ("export * from './a';", [("reexport", "./a", False, True)]),
        ("export {a} from './a';", [("reexport", "./a", False, True)]),
        ("export type {a} from './a';", [("reexport", "./a", True, True)]),
        ("export {type a, type b} from './a';", [("reexport", "./a", True, True)]),
        ("export {type a, b} from './a';", [("reexport", "./a", False, True)]),
        ("import x = require('./a');", [("import_equals", "./a", False, True)]),
        ("import type x = require('./a');", [("import_equals", "./a", True, True)]),
        ("import('./a');", [("dynamic_import", "./a", False, False)]),
        ("const x = require('./a');", [("require", "./a", False, False)]),
        ("type T = import('./a').Value;", [("import_type", "./a", True, False)]),
        ("let v: typeof import('./a');", [("import_type", "./a", True, False)]),
        ("let v: A<import('./a').T>;", [("import_type", "./a", True, False)]),
        ("const v = x as import('./a').T;", [("import_type", "./a", True, False)]),
        ("const v = <import('./a').T>x;", [("import_type", "./a", True, False)]),
        ("declare module 'm' { import b from './a'; }", [("import", "./a", False, False)]),
    ],
)
def test_reference_forms_and_flags(
    source: str, expected: list[tuple[str, str, bool, bool]]
) -> None:
    assert _forms(parse("main.ts", source.encode())) == expected


@pytest.mark.parametrize(
    "source",
    [
        "import(name);",
        "import();",
        "import(`./a${name}`);",
        "import('./a\\x62');",
        "require(name);",
        "require();",
    ],
)
def test_a_specifier_that_is_not_a_plain_string_names_no_module(source: str) -> None:
    (reference,) = parse("main.ts", source.encode()).references
    assert reference.specifier is None


def test_a_template_without_substitution_is_a_plain_string() -> None:
    (reference,) = parse("main.ts", b"import(`./a`);").references
    assert reference.specifier == "./a"


def test_positions_follow_the_compiler_in_utf16_units_and_every_line_break() -> None:
    source = 'const s = "\U0001f600";import("./a");\r\n\rimport("./b"); import("./c");'
    spans = [
        (item.span.line, item.span.column) for item in parse("main.ts", source.encode()).references
    ]
    # An astral character is two UTF-16 units; CRLF, CR and U+2028 each end one line.
    assert spans == [(1, 16), (3, 1), (4, 1)]


def test_an_import_type_starts_at_its_typeof_like_the_compiler_counts_it() -> None:
    source = b'type X = A & typeof import("node:os").constants.dlopen;'
    (reference,) = parse("main.ts", source).references
    assert source[reference.span.column - 1 :].startswith(b"typeof")


def test_resolution_mode_attribute_is_reported_on_the_reference() -> None:
    plain, marked = parse(
        "main.mts",
        b'import type {A} from "a";\nimport type {B} from "b" with {"resolution-mode": "require"};',
    ).references
    assert (plain.mode_override, marked.mode_override) == (False, True)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("main.ts", "const x = <number>y;"),
        ("main.cts", "const x = <number>y;"),
        ("main.d.ts", "declare const x: number;"),
        ("main.tsx", "const x = <div>{y}</div>;"),
        ("main.js", "const x = <div>{y}</div>;"),
        ("main.mjs", "export const x = 1;"),
        ("main.jsx", "const x = <a />;"),
    ],
)
def test_each_extension_uses_a_grammar_that_reads_it(path: str, source: str) -> None:
    assert parse(path, source.encode()).first_error is None


def test_syntax_errors_are_located_and_never_yield_references() -> None:
    syntax = parse("main.ts", b"import './a';\nexport const = ;\nimport './b';\n")
    assert syntax.first_error is not None
    assert syntax.first_error.line == 2
    # A reference inside a repaired region is not a fact; intact statements still are.
    assert [item.specifier for item in syntax.references] == ["./a", "./b"]


def test_a_reference_the_parser_had_to_repair_is_dropped() -> None:
    syntax = parse("main.ts", b"export type * from './a';\n")
    assert syntax.first_error is not None
    assert syntax.references == ()


@pytest.mark.parametrize(
    ("source", "reasons"),
    [
        ("function f() { return require('./a'); }", []),
        (
            "typeof require; require.main; require.resolve('x');",
            ["Indirect require use is not resolved"] * 3,
        ),
        ("const load = require; load('./a');", ["Indirect require use is not resolved"]),
        ("function require() {} require('./a');", ["Indirect require use is not resolved"]),
        ("module.require('./a');", ["Unproven require member use"]),
        ("module['require']('./a');", ["Computed require member use"]),
        ("module[name]('./a');", ["Computed require member use"]),
        ("const {require: load} = module;", ["Indirect require binding is not resolved"]),
        ("const {['require']: load} = module;", ["Indirect require binding is not resolved"]),
        ("const {'require': load} = module;", ["Indirect require binding is not resolved"]),
        ("const {[key]: load} = module;", ["Indirect require binding is not resolved"]),
        ("const {[key]: load} = other;", []),
        ("import {createRequire} from 'node:module';", ["Node module loader is not observed"]),
        ("const x = {'createRequire': 1};", ["Node module loader is not observed"]),
        ("import type {X} from 'module';", ["Node module loader is not observed"]),
        ("/// <reference types='node' />\nexport {};", ["Unobserved triple-slash reference: node"]),
        ("export {};\n/// <reference types='node' />", []),
        ("// import('x')\n/* @import {X} from 'x' */", []),
        ("/** @typedef {import('./a').A} A */", ["JSDoc import is not observed"]),
        ("/** @import {A} from './a' */", ["JSDoc import is not observed"]),
        ("/**/ const a = 1;", []),
    ],
)
def test_patterns_the_reader_cannot_follow_are_concerns(source: str, reasons: list[str]) -> None:
    assert _reasons(parse("main.ts", source.encode())) == sorted(reasons)


@pytest.mark.parametrize(
    ("source", "shadows"),
    [
        ("require('./a');", False),
        ("typeof require === 'function'; require.main === module;", False),
        ("function require() {}", True),
        ("const require = 1;", True),
        ("function f(require) {}", True),
        ("const {require} = x;", True),
        ("foo(require);", True),
        ("import require from 'x';", True),
    ],
)
def test_only_a_binding_or_an_alias_of_require_can_shadow_it(source: str, shadows: bool) -> None:
    assert parse("main.ts", source.encode()).shadows_require is shadows


def test_every_module_specifier_of_the_loader_is_one_concern_per_file() -> None:
    syntax = parse("main.ts", b"import('node:module'); require('module'); export * from 'module';")
    assert [item.specifier for item in syntax.references] == ["node:module", "module", "module"]
    assert _reasons(syntax) == ["Node module loader is not observed"]
