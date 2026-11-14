# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The open forms of the script-global rule give no PASS (#880, AD-498).

Consumer: `archkeel validate` on a TypeScript project, through the release core. A module file of
`b` holds one form, and `a` calls `window.open()`: the form can replace `open` or run code, so
the rule must give UNKNOWN. Each plant gave PASS before AD-498, except the group `PINNED`, which
was a gap already and stays one. The group `PRECISION` must keep its PASS: the closure is not a
blanket refusal of computed keys, patterns, `this` or `location`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_native_global_writes import MODULE, _project, _verdict

DECLARE = "declare const k: string, x: any, g: any, el: any, e: any, t: string, o: any;\n"
LISTEN = "\naddEventListener('load', new C().m);"

# Group 1: a write through `this` of a class method. A caller can extract the method (AD-460).
METHOD_THIS = {
    "assign": "class C { m(this: any) { this[k] = 1; } }" + LISTEN,
    "no-this-parameter": "class C { m() { (this as any)[k] = 1; } }" + LISTEN,
    "compound": "class C { m(this: any) { this[k] += 1; } }" + LISTEN,
    "update": "class C { m(this: any) { this[k]++; } }" + LISTEN,
    "delete": "class C { m(this: any) { delete this[k]; } }" + LISTEN,
    "array-pattern": "class C { m(this: any) { [this[k]] = [1]; } }" + LISTEN,
    "object-pattern": "class C { m(this: any) { ({ a: this[k] } = x); } }" + LISTEN,
    "for-of": "class C { m(this: any) { for (this[k] of g) {} } }" + LISTEN,
    "static": "class C { static m(this: any) { this[k] = 1; } }\naddEventListener('load', C.m);",
    "accessor": (
        "class C { get v(): any { (this as any)[k] = 1; return 1; } }\nexport const c = new C();"
    ),
}

# Group 2: a call through a key that is built at run time, on a value that is no data.
KEY_CALL = {
    "parameter": "o[k](t);",
    "global-function": "Object[k](t)();",
    "constructed": "new o[k](t);",
    "import-namespace": "import * as ns from 'node:fs';\nns[k](t);",
    "tagged": "o[k]`code`;",
    "wrapped": "(o[k] as any)(t);",
    "constructed-wrapped": "new (o[k] as any)(t);",
    "optional": "o?.[k](t);",
    "call-member": "o[k].call(null, t);",
    "bind-member": "o[k].bind(null, t)();",
    "method-this": "class C { m(this: any) { this[k](t); } }" + LISTEN,
}

# Group 3: a reflection with a key that is built at run time can reach `constructor`.
REFLECTION = {
    "descriptor": "Object.getOwnPropertyDescriptor(() => {}, k)!.value(t)();",
    "descriptors": "Object.getOwnPropertyDescriptors(() => {})[k].value(t)();",
}

# Group 4: a value that is no literal can be a `javascript:` URL, which runs in this page.
LOCATION = {
    "assign": "location.assign(t);",
    "replace": "location.replace(t);",
    "href": "location.href = t;",
    "href-compound": "location.href += t;",
    "window-location": "window.location = t as any;",
    "document-location": "document.location = t as any;",
    "string-key-call": "location['assign'](t);",
    "runtime-key-call": "location[k](t);",
    "string-key-href": "location['href'] = t;",
    "runtime-key-write": "location[k] = t;",
    "document-string-key": "document['location'].assign(t);",
    "open-self": "open(t, '_self');",
    "window-open-self": "window.open(t, '_self');",
    "open-named": "open(t, k);",
}

# Group 5: a pattern that takes a window member out of a value binds a window (AD-492).
PATTERN = {
    "declaration": "const { source } = e;\nsource[k] = 1;",
    "parameter": "const h = ({ view }: any) => { view[k] = 1; };\nh(e);",
    "parameter-alias": "const h = ({ source: s }: any) => { s[k] = 1; };\nh(e);",
    "for-of": "for (const { view } of g) { view[k] = 1; }",
    "default-value": "const { view = x } = e;\nview[k] = 1;",
    "catch-clause": "try { g(); } catch ({ view }: any) { view[k] = 1; }",
    "string-key": "const { 'view': v } = e;\nv[k] = 1;",
    "assignment-in-for-of": "let v: any;\nfor ({ source: v } of g) { v[k] = 1; }",
    "window-name": "const { top } = e;\ntop[k] = 1;",
}

# Group 6: a gap before AD-498, kept as a gap (a pin and no code).
PINNED = {
    "html-string-key": "el['innerHTML'] = t;",
    "html-template-key": "el[`innerHTML`] = t;",
    "html-outer-key": "el['outerHTML'] = t;",
    "html-srcdoc-key": "el['srcdoc'] = t;",
    "eval-string-key": "x['eval'](t);",
    "eval-template-key": "x[`eval`](t);",
    "function-string-key": "x['Function'](t)();",
    "scheme-tab": "el.src = 'java\\tscript:open=1';",
    "scheme-newline": "el.href = 'java\\nscript:open=1';",
    "scheme-leading-control": "el.href = '\\u0001javascript:open=1';",
    "scheme-leading-space": "el.href = ' javascript:open=1';",
    "scheme-upper-case": "el.href = 'JAVASCRIPT:open=1';",
    "scheme-raw-tab": "el.src = 'java\tscript:open=1';",
    "scheme-template": "el.href = `java\\tscript:open=1`;",
    "scheme-attribute": "el.setAttribute('href', 'java\\tscript:open=1');",
    "scheme-open-literal": "open('java\\tscript:open=1', '_self');",
    "scheme-location-literal": "location.href = 'java\\tscript:open=1';",
    "method-eval": "class C { m(this: any) { this.eval(t); } }" + LISTEN,
    "method-function": "class C { m(this: any) { this.Function(t)(); } }" + LISTEN,
    "handle-event": (
        "class C { handleEvent() { (this as any).eval(t); } }\n"
        "addEventListener('load', new C() as any);"
    ),
    "bound-method": "class C { m() { (this as any).eval(t); } }" + LISTEN,
    "this-alias": "class C { m() { const s: any = this; s.eval(t); } }" + LISTEN,
    "this-write": "class C { m() { (this as any).open = 1; } }" + LISTEN,
    "destructured-eval": "const { view } = e;\nview.eval(t);",
    "pattern-assignment": "let w: any;\n({ view: w } = e);\nw.eval(t);",
    "nested-pattern": "const { a: { view } } = e;\nview.eval(t);",
    "rest-pattern": "const { ...r } = e;\nr.view[k] = 1;",
    "reflect-get": "Reflect.get(() => {}, k)(t)();",
    "reflect-namespace-key": "Reflect[k](() => {}, k);",
    "reflect-descriptor": "Reflect.getOwnPropertyDescriptor(() => {}, k)!.value(t)();",
    "reflect-literal-method": "Reflect['getOwnPropertyDescriptor'](() => {}, k);",
}

CLOSED = {
    **{f"this-{name}": text for name, text in METHOD_THIS.items()},
    **{f"key-call-{name}": text for name, text in KEY_CALL.items()},
    **{f"reflection-{name}": text for name, text in REFLECTION.items()},
    **{f"location-{name}": text for name, text in LOCATION.items()},
    **{f"pattern-{name}": text for name, text in PATTERN.items()},
}

# The closure is a rule about run-time keys, `this` of a method, `location` and window members.
PRECISION = {
    "namespace-key": "Math[k as 'abs'](1);",
    "data-key": "const table = { a: () => 1 };\ntable[k as 'a']();",
    "array-index": "const xs = [1, 2];\nexport const y = xs[0];",
    "array-call": "const fns = [() => 1];\nfns[0]();\nfns.map((q) => q());",
    "plain-pattern": "const { name, value } = e;\nexport const z = name + value;",
    "array-pattern": "const [a, b] = g;\nexport const s = a + b;",
    "target-pattern": "const { target } = e;\nexport const w = target;",
    "literal-location": "location.href = '/home';\nlocation.assign('/a');",
    "blank-window": "open(t, '_blank');\nopen('/x');",
    "this-literal-key": (
        "class C { m() { (this as any)['x'] = 1; (this as any)[0] = 2; } }\n"
        "export const c = new C();"
    ),
    "this-named-key": "class C { m() { this.x = 1; } x = 0; }\nexport const c = new C();",
    "arrow-field-this": (
        "class C { h = () => { (this as any)[k] = 1; }; }\nexport const c = new C();"
    ),
    "record-write": "const m: Record<string, number> = {};\nm[k] = 1;",
}


def _gives_pass(tmp_path: Path, release_core: Path, text: str) -> tuple[int, str, dict]:
    root = _project(tmp_path, MODULE + DECLARE + text, "window.open();\n")
    code, document = _verdict(root, release_core)
    assert "refusal" not in document, document.get("refusal")
    return code, document["status"], document


@pytest.mark.parametrize("name", sorted(CLOSED))
def test_a_closed_form_gives_no_pass(tmp_path: Path, release_core: Path, name: str) -> None:
    code, status, _ = _gives_pass(tmp_path, release_core, CLOSED[name])
    assert (code, status) == (2, "UNKNOWN"), name


@pytest.mark.parametrize("name", sorted(PINNED))
def test_a_form_that_was_a_gap_stays_a_gap(tmp_path: Path, release_core: Path, name: str) -> None:
    code, status, _ = _gives_pass(tmp_path, release_core, PINNED[name])
    assert (code, status) == (2, "UNKNOWN"), name


@pytest.mark.parametrize("name", sorted(PRECISION))
def test_a_form_without_the_risk_keeps_its_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    code, status, document = _gives_pass(tmp_path, release_core, PRECISION[name])
    assert (code, status) == (0, "PASS"), (name, document.get("frame", {}).get("scope"))
