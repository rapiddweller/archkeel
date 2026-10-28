# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Only a JSDoc type or an `@import` tag in a JavaScript file is a JSDoc import (#744).

Each expected value agrees with tsc 5.9.3: the import either pulls the module into the program
or not. A case where the reader keeps the gap although tsc does not read it is marked.
"""

import json
import time

import pytest

from archkeel.analyzer.typescript.collect import collect
from archkeel.analyzer.typescript.parse import parse
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings

GAP = "JSDoc import is not observed"
TYPE = "import('./a').A"


def _gap(source: str, path: str = "main.js") -> bool:
    return GAP in [item.reason for item in parse(path, source.encode()).concerns]


@pytest.mark.parametrize(
    ("comment", "gap"),
    [
        # Prose is no type.
        ("/** A reload helper. */", False),
        ("/**\n * After a deploy the dynamic import() fails.\n */", False),
        ("/** call import(x) later */", False),
        ("/** it says \"import('./a')\" */", False),
        (f"/** Use {{@link {TYPE}}} here. */", False),
        # Only `/**` opens a JSDoc block.
        (f"// @type {{{TYPE}}}", False),
        (f"/* @type {{{TYPE}}} */", False),
        ("/**/", False),
        ("/***/", False),
        (f"/** x */\n// @type {{{TYPE}}}", False),
        (f"/** x */\n/* @type {{{TYPE}}} */", False),
        (f"/** x */\n/* @param {{string}} p\n * @type {{{TYPE}}} */", False),
        (f"/*** @type {{{TYPE}}} */", True),
        # Every tag that holds a type, with braces. `@prop` and `@property` load only in a
        # `@typedef` or a `@callback`; alone they keep the gap: fail closed.
        *(
            (f"/** @{tag} {{{TYPE}}} p */", True)
            for tag in (
                "type",
                "this",
                "enum",
                "satisfies",
                "return",
                "returns",
                "param",
                "arg",
                "argument",
                "prop",
                "property",
                "typedef",
                "template",
                "throws",
                "exception",
            )
        ),
        *((f"/** @{tag} {{B<{TYPE}>}} */", True) for tag in ("extends", "augments", "implements")),
        (f"/** @typedef {{object}} O\n * @property {{{TYPE}}} p */", True),
        # A `@template` default in brackets holds a type, with or without a constraint first.
        (f"/** @template [T={TYPE}] */", True),
        (f"/** @template [ T = {TYPE} ] */", True),
        (f"/** @template [const T={TYPE}] */", True),
        (f"/** @template {{number}} [T={TYPE}] */", True),
        (f"/** @template {{number}} T, [U={TYPE}] */", True),
        (f"/** @template A, B, [C={TYPE}] */", True),
        (f"/** @template [T={TYPE}[]] */", True),
        (f"/** @template [T=[number] | {TYPE}] */", True),
        (f"/** @template [T={{a: {TYPE}}}] */", True),
        (f"/** @template [T={TYPE}] a description */", True),
        (f"/** @template\n * [T={TYPE}] */", True),
        (f"/** @template {{{TYPE}}} T */", True),
        (f"/** @template [T={TYPE} */", True),
        # Prose after the template names is no type.
        ("/** @template T the dynamic import('./a') fails */", False),
        ("/** @template [T] import('./a') */", False),
        ("/** @template [T=number] the dynamic import('./a') fails */", False),
        ("/** @template {number} T the [docs] say import('./a') */", False),
        (f"/** @template T={TYPE} */", False),
        (f"/** @template [T=number]\n * @returns {{number}} after {TYPE} */", False),
        # Only a template reads a type in brackets: a parameter default is an expression.
        ("/** @param {number} [p=import('./a')] */", False),
        ("/** @param [p=import('./a')] */", False),
        ("/** @property {number} [p=import('./a')] */", False),
        # A quote can hide a bracket, so the reader cannot find the end of the default.
        (f"/** @template [T='a]' | {TYPE}] */", True),
        # Kept although tsc ends the template names before the brackets: fail closed.
        (f"/** @template A [B={TYPE}] */", True),
        (f"/** @template T,\n * [U={TYPE}] */", True),
        (f"/** @template [T=\n * {TYPE}] */", True),
        # The `@import` tag in each form.
        ("/** @import {A} from './a' */", True),
        ("/** @import A from './a' */", True),
        ("/** @import * as M from './a' */", True),
        ("/** @import{A}from'./a' */", True),
        # Space, line break and margin between `import` and `(`.
        ("/** @type {import ('./a').A} */", True),
        ("/** @type {import\n('./a').A} */", True),
        ("/** @type {import\n * ('./a').A} */", True),
        ("/** @type {{ a: import('./a').A }} */", True),
        ("/** @type {{a: 1} | import('./a').A} */", True),
        ("/** @type {[number] | import('./a').A} */", True),
        (f"/** @type {{`${{{TYPE}['n']}}`}} */", True),
        # Some tags may omit the braces.
        (f"/** @type {TYPE} */", True),
        (f"/** @satisfies {TYPE} */", True),
        (f"/** @this {TYPE} */", True),
        (f"/** @enum {TYPE} */", True),
        (f"/** @extends B<{TYPE}> */", True),
        (f"/** @augments B<{TYPE}> */", True),
        (f"/** @implements B<{TYPE}> */", True),
        (f"/** @returns {TYPE} */", False),
        ("/** import('./a') is prose.\n * @type X */", False),
        # A parameter name may come before the type.
        (f"/** @param p {{{TYPE}}} */", True),
        # tsc starts a tag after whitespace or a margin `*`, not inside a word.
        (f"/** see @type {{{TYPE}}} */", True),
        (f"/**\n *@type {{{TYPE}}} */", True),
        (f"/**@type {{{TYPE}}} */", True),
        (f"/** mail a@type {{{TYPE}}} */", False),
        # Tags that hold no type.
        ("/**\n * @example\n * const m = import('./a');\n */", False),
        (f"/** @example {{{TYPE}}} */", False),
        (f"/** @see {{@link {TYPE}}} */", False),
        (f"/** @see {{{TYPE}}} */", False),
        (f"/** @deprecated {{{TYPE}}} */", False),
        (f"/** @yields {{{TYPE}}} */", False),
        (f"/** @const {{{TYPE}}} */", False),
        (f"/** @foo {{{TYPE}}} */", False),
        # The description after a type is prose.
        ("/** @returns {number} after the dynamic import('./a') */", False),
        ("/** @param {string} p the dynamic import('./a') fails */", False),
        ("/** @param {'a'} p the dynamic import('./a') fails */", False),
        ("/** @param {string} p it's\n * @returns {number} after import('./a') */", False),
        ("/** @type {number} after the dynamic import('./a') */", False),
        (f"/** @param {{string}} p\n * @see {{{TYPE}}} */", False),
        (f"/** @type {{{TYPE} | {{a: 1}}}} */", True),
        # A quote can hide a brace, so the reader cannot find the end of the type.
        ("/** @type {'}' | import('./a').A} */", True),
        ("/** @type {' @x' | import('./a').A} */", True),
        ("/** @type {import('./a').A | ' @x'} */", True),
        ("/** import('./a') is prose.\n * @param {'}'} p */", False),
        ("/** import('./a') is prose.\n * @param {'a' | 'b'} p */", False),
        # Kept although tsc reads no type after a stray brace: fail closed.
        (f"/** @returns }} {{{TYPE}}} */", True),
        # Kept although tsc reads a string literal type: fail closed.
        ("/** @type {'import(\"./a\")'} */", True),
        # An unclosed type stays a gap only when an import follows.
        ("/** @type {import('./a').A */", True),
        ("/** @param {X */", False),
        ("/** import('./a') is prose.\n * @param {X */", False),
    ],
)
def test_only_a_type_or_an_import_tag_is_a_jsdoc_import(comment: str, gap: bool) -> None:
    assert _gap(f"{comment}\nexport const k = 1;\n") is gap


@pytest.mark.parametrize(
    "source",
    [
        f"export const k = 1;\n/** @type {{{TYPE}}} */\n",
        f"const k = /** @satisfies {{{TYPE}}} */ ({{}});\n",
        # Kept although tsc skips a comment after a statement on one line: fail closed.
        f"export const k = 1; /** @type {{{TYPE}}} */\n",
    ],
)
def test_the_position_of_the_comment_does_not_matter(source: str) -> None:
    assert _gap(source)


@pytest.mark.parametrize(
    ("path", "gap"),
    [
        ("main.js", True),
        ("main.jsx", True),
        ("main.mjs", True),
        ("main.cjs", True),
        # tsc ignores JSDoc types in TypeScript files: the comment adds no dependency.
        ("main.ts", False),
        ("main.tsx", False),
        ("main.mts", False),
        ("main.cts", False),
        ("main.d.ts", False),
        ("main.d.mts", False),
        # A file without a known suffix keeps the gap: fail closed.
        ("main", True),
    ],
)
def test_only_javascript_files_read_jsdoc_types(path: str, gap: bool) -> None:
    assert _gap(f"/** @type {{{TYPE}}} */\nexport const k = 1;\n", path) is gap
    assert _gap("/** @import {A} from './a' */\nexport const k = 1;\n", path) is gap


@pytest.mark.parametrize(
    "comment",
    [
        "/** " + "a import( b " * 20_000 + "*/",
        "/** import( @type " + "x @type x " * 20_000 + "*/",
        "/** @type " + "{" * 100_000 + "}" * 100_000 + " import( */",
        "/** @template " + "[" * 100_000 + "]" * 100_000 + " import( */",
        "/** import( " + "@param {a} p " * 20_000 + "*/",
    ],
    ids=["prose", "bare tags", "nested braces", "nested brackets", "braced tags"],
)
def test_a_large_comment_is_read_in_linear_time(comment: str) -> None:
    started = time.perf_counter()
    _gap(f"{comment}\nexport const k = 1;\n")
    assert time.perf_counter() - started < 2


def _reasons(tmp_path, files: dict[str, str], compiler: dict[str, object]) -> list[str]:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    options = {"target": "ES2022", "strict": True, **compiler}
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
    validate_source_facts(facts)
    return [gap.data.get("reason", "") for gap in facts.coverage.gaps]


@pytest.mark.parametrize(
    "comment",
    [
        "/**\n * After a deploy the dynamic import() fails.\n */",
        "/** call import(x) later */",
        f"/** @type {{{TYPE}}} */",
    ],
)
def test_the_collector_reports_no_jsdoc_import_in_a_typescript_file(tmp_path, comment) -> None:
    files = {"src/a.ts": "export type A = 1;\n", "src/b.ts": f"{comment}\nexport const k = 1;\n"}
    assert GAP not in _reasons(tmp_path, files, {})


@pytest.mark.parametrize(
    ("comment", "gap"),
    [
        ("/**\n * After a deploy the dynamic import() fails.\n */", False),
        (f"/** @type {{{TYPE}}} */", True),
        ("/** @import {A} from './a' */", True),
        (f"/** @template [T={TYPE}] */", True),
        ("/** @template [T=number] the dynamic import('./a') fails */", False),
    ],
)
def test_the_collector_reports_a_jsdoc_type_import_in_a_javascript_file(
    tmp_path, comment: str, gap: bool
) -> None:
    files = {"src/a.ts": "export type A = 1;\n", "src/b.js": f"{comment}\nexport const k = 1;\n"}
    assert (GAP in _reasons(tmp_path, files, {"allowJs": True})) is gap
