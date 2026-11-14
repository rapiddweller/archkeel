# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Code from a text, and a write that changes a published global, give no PASS (#880, AD-460).

Consumer: `archkeel validate` on a TypeScript project, through the release core. The first group
puts code that runs a text into a module file of `b`, and `a` calls `window.open()`: that text can
replace `open`. The second group lets `a` use `b` only. A script of `b` publishes `Lib`, `a` calls
`Lib.run()`, and a module file of `c` changes `Lib`. The call can then reach `c`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from corpus_support import commit_tree
from test_cli_native_global_writes import MODULE, _project, _verdict
from test_collector_false_pass_sources import BASE, CONTRACT

CODE = {
    "destructured-constructor": 'const { constructor: F } = (() => {}) as any; F("open = 1")();',
    "computed-constructor-text": 'const k = "constructor"; (({}) as any)[k][k]("open = 1")();',
    "concatenated-constructor": '((() => {}) as any)["const" + "ructor"]("open = 1")();',
    "reflect-constructor": 'Reflect.get(() => {}, "constructor")("open = 1")();',
    "shorthand-function": 'const o = { Function }; o.Function("open = 1")();',
    "constructor-call": '(() => {}).constructor.call(null, "open = 1")();',
    "window-eval": 'window.eval("open = 1");',
    "self-function": '(self as any).Function("open = 1")();',
    "logical-eval": 'declare const x: any; (x || eval)("open = 1");',
    "tagged-function": "Function`open = 1`();",
    "reflect-construct": 'Reflect.construct(Function, ["open = 1"])();',
    "timer-call": 'setTimeout.call(null, "open = 1");',
    "timer-variable": 'const t: any = "open = 1"; setTimeout(t);',
    "timer-member": "export class T { t: any; go() { window.setTimeout(this.t, 1); } }",
    "timer-alias": "export const st = setTimeout;",
    "script-element": 'const s = document.createElement("script"); s.text = "open = 1";',
    "document-write": 'document.write("<script>open = () => {}</script>");',
    "handler-attribute": 'document.body.setAttribute("onclick", "open = 1");',
    "html-handler": "document.body.innerHTML = \"<img src=x onerror='open=1'>\";",
    "html-call": 'document.body.insertAdjacentHTML("beforeend", "<img onerror=x>");',
    "javascript-link": 'location.href = "javascript:open=1";',
    "data-import": 'import("data:text/javascript,open=1");',
    "dynamic-import": "declare const u: string; import(u);",
}


# Review of #1161: each form gave PASS on its head and must stay a gap (B1, B2, D1, F2).
REVIEW_DECLARATIONS = "declare const k: string, x: any, g: any, el: any, e: any, t: string;\n"
REVIEW = {
    "b1-logical-parent": "(x || document.defaultView).parent[k] = 1;",
    "b1-ternary-top": "(x ? el.contentWindow : x).top[k] = 1;",
    "b1-sequence-top": "(0, document.defaultView).top[k] = 1;",
    "b1-escape-parent": "g((x || document.defaultView).parent);",
    "b1-parent-eval": "(x || document.defaultView).parent.eval('open = 1');",
    "b2-continuation": "el.innerHTML = '<details open o\\\nntoggle=open=1>';",
    "b2-template": "el.innerHTML = `<details open o\\\nntoggle=open=1>`;",
    "b2-crlf": "el.innerHTML = '<details open o\\\r\nntoggle=open=1>';",
    "b2-separator": "el.innerHTML = '<details open o\\\u2028ntoggle=open=1>';",
    "b2-fragment": "el.createContextualFragment('<scr\\\nipt>open = 1</script>');",
    "d1-source-key": "e.source[k] = 1;",
    "d1-view-key": "e.view[k] = 1;",
    "d1-view-escape": "g(e.view);",
    "d1-view-assign": "Object.assign(e.view, { [k]: 1 });",
    "d1-source-top": "e.source.top[k] = 1;",
    "d1-opener-key": "x.opener[k] = 1;",
    "d1-view-eval": "e.view.eval(t);",
    "d1-source-function": "e.source.Function(t)();",
    "d1-target-eval": "e.currentTarget.eval(t);",
    "d1-new-function": "new x.Function(t);",
    "d1-eval-call": "x.eval.call(null, t);",
    "d1-function-alias": "declare const Level: any;\nconst F = Level.Function;\nF(t)();",
    "d1-method-eval": (
        'class C { m(this: any) { this.eval(t); } }\naddEventListener("load", new C().m);'
    ),
    "f2-comment-html": (
        "el.insertAdjacentHTML(/* c */ 'beforeend', '<details open ontoggle=open=1>');"
    ),
    "f2-comment-attribute": "el.setAttributeNS(/* c */ 'x', 'onclick', t);",
    "f2-comment-element": "document.createElementNS(/* c */ 'x', 'script');",
    "f2-html-key": "el['innerHTML'] = t;",
    "f2-html-pattern": "[el.innerHTML] = [t];",
    "f2-eval-key": "x['eval'](t);",
    "f2-function-pattern": "const { Function: F } = x;\nF(t)();",
    "f2-tab-scheme": "el.src = 'java\\tscript:open=1';",
    "f2-raw-tab-scheme": "el.src = 'java\tscript:open=1';",
}


@pytest.mark.parametrize("name", sorted(REVIEW))
def test_a_review_form_of_1161_gives_no_pass(tmp_path: Path, release_core: Path, name: str) -> None:
    write = MODULE + REVIEW_DECLARATIONS + REVIEW[name]
    code, document = _verdict(_project(tmp_path, write, "window.open();\n"), release_core)
    assert (code, document["status"]) != (0, "PASS"), name


# Each markup literal that the write check refuses (AD-460): every one can run or load code.
MARKUP = {
    "upper-case-handler": "<IMG SRC=x ONERROR=y>",
    "slash-handler": "<img/onerror=y>",
    "quote-handler": '<img alt="x"onerror=y>',
    "entity": "<p>&#106;avascript:</p>",
    "svg": "<svg></svg>",
    "math": "<math></math>",
    "formaction": "<button formaction=x>b</button>",
    "style": '<p style="x">p</p>',
    "anchor": '<a href="#">a</a>',
    "form-action": "<form action=x></form>",
    "link": "<link rel=x>",
    "template": "<template><p>p</p></template>",
    "image-source": "<img src=x>",
    "script": "<script>open = 1</script>",
    "code-scheme": "<p>vbscript:x</p>",
}


@pytest.mark.parametrize("name", sorted(MARKUP))
def test_markup_that_can_run_code_gives_no_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    text = json.dumps(MARKUP[name])
    write = f"declare const e: any;\ne.innerHTML = {text};"
    code, document = _verdict(_project(tmp_path, MODULE + write, "window.open();\n"), release_core)
    assert (code, document["status"]) != (0, "PASS"), name


@pytest.mark.parametrize("name", sorted(CODE))
def test_code_from_a_text_gives_no_pass(tmp_path: Path, release_core: Path, name: str) -> None:
    root = _project(tmp_path, MODULE + CODE[name], "window.open();\n")
    code, document = _verdict(root, release_core)
    assert "refusal" not in document, (name, document.get("refusal"))
    assert (code, document["status"]) != (0, "PASS"), name


def _component(name: str, requires: list[str]) -> dict[str, object]:
    component = dict(CONTRACT["components"][0])
    component.update(
        id=f"COMP-{name.upper()}",
        label=name,
        packages=[f"app.src.{name}"],
        public=[f"app.src.{name}"],
        responsibilities=[f"Hold {name}."],
        requires=[
            {
                "component": item,
                "rationale": "The client calls the library that the script publishes.",
            }
            for item in requires
        ],
    )
    return component


PUBLISHED = {
    "architecture-contract.json": json.dumps(
        {
            **CONTRACT,
            "components": [_component("a", ["b"]), _component("b", []), _component("c", ["b"])],
        }
    ),
    "src/b/b.js": "function run() {}\nwindow.Lib = { run };\n",
    # AD-466: the provenance document draws the observed component edge.
    "README.md": (
        "# probe\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n    a --> b\n```\n"
    ),
}
CHANGES = {
    "parent": "parent.Lib = { run() {} };",
    "top-window": "top.window.Lib = { run() {} };",
    "opener": "opener.Lib = { run() {} };",
    "parent-member": "parent.Lib.run = () => {};",
    "default-view": "document.defaultView.Lib = { run() {} };",
    "target-as": "(window.Lib as any) = { run() {} };",
    "destructuring": "[parent.Lib] = [{ run() {} }];",
    "eval": '(0, eval)("Lib = 1");',
    "constructor": '({}).constructor.constructor("Lib = 1")();',
}


def _published(tmp_path: Path, change: str) -> Path:
    root = tmp_path / "repo"
    files = {
        **BASE,
        **PUBLISHED,
        "src/a/a.ts": "Lib.run();\n",
        "src/c/c.ts": MODULE + change + "\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(root)
    return root


def test_an_unchanged_publication_keeps_its_pass(tmp_path: Path, release_core: Path) -> None:
    code, document = _verdict(_published(tmp_path, "export const c = 1;"), release_core)
    assert (code, document["status"]) == (0, "PASS"), document.get("frame")


@pytest.mark.parametrize("name", sorted(CHANGES))
def test_a_change_of_a_published_global_gives_no_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    code, document = _verdict(_published(tmp_path, CHANGES[name]), release_core)
    assert "refusal" not in document, (name, document.get("refusal"))
    assert (code, document["status"]) != (0, "PASS"), name
