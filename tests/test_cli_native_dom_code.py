# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""DOM code from a text that the file builds gives no PASS (#1526, AD-460).

Consumer: `archkeel validate` on a TypeScript project, through the release core. A module file of
`b` hands a text to the page as code, and `a` calls `window.open()`. A text such as
`<script>open=()=>{}</script>` or `javascript:open=()=>{}` replaces the global `open`. The rule
must give UNKNOWN. The page runs the text in these places: `document.write` after
`document.open`, a link or frame address, a form action, and `insertHTML`. The group `PRECISION`
must keep its PASS: a literal address, a member read of a document and another attribute do not
run a text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_native_global_writes import MODULE, _project, _requires, _verdict

DECLARE = "declare const k: string, x: any, t: string, el: any;\n"
USE = "window.open();\n"
CODE = "['java','script:open=()=>{}'].join('')"

FORMS = {
    # The three audit plants of #1526.
    "open-result": "const w = open('', '_self');\n(w as any)[k] = () => {};",
    "document-open": "const d = document.open();\nd.write('<script>open=()=>{}</script>');",
    "link-click": f"const a = document.createElement('a');\na.href = {CODE};\na.click();",
    # A document that the file keeps or passes on.
    "document-alias": "const d = document;\nd.write(t);",
    "document-passed": "function w(d: any) { d.write(t); }\nw(document);",
    "owner-document": "const d = el.ownerDocument;\nd.write(t);",
    "frame-document": "const d = el.contentDocument;\nd.writeln(t);",
    "window-document": "const p: any = open('', '_self');\nconst d = p.document;\nd.write(t);",
    "document-pattern": "const { document: d } = window as any;\nd.write(t);",
    # The write of a document used as a value.
    "write-call": "document.write.call(document, t);",
    "write-bind": "const w = document.write.bind(document);\nw(t);",
    "write-string-key": "document['write'](t);",
    "open-three": "document.open(t, '_self', '');",
    # An address of a link, a frame or a form that the file builds.
    "frame-src": (
        "const f = document.createElement('iframe');\nf.src = t;\ndocument.body.append(f);"
    ),
    "form-action": "const f = document.createElement('form');\nf.action = t;\nf.submit();",
    "form-action-button": "el.formAction = t;\nel.click();",
    "object-data": "const o = document.createElement('object');\no.data = t;",
    "string-key-href": "el['href'] = t;\nel.click();",
    "compound-href": "el.href += t;\nel.click();",
    "svg-href": "el.href.baseVal = t;",
    "set-attribute": "el.setAttribute('href', t);\nel.click();",
    "set-attribute-case": "el.setAttribute('HREF', t);\nel.click();",
    "set-attribute-ns": "el.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', t);",
    "insert-html": "document.execCommand('insertHTML', false, t);",
}

PRECISION = {
    "literal-href": "el.href = '/home';",
    "title": "document.title = t;",
    "read": "export const node = document.getElementById(t);",
    "class-attribute": "el.setAttribute('class', t);",
    "copy-command": "document.execCommand('copy');",
    "popup": "const w = window.open('/help', '_blank');\nw?.focus();",
}


@pytest.mark.parametrize("name", sorted(FORMS))
def test_dom_code_from_a_text_holds_the_rule(tmp_path: Path, release_core: Path, name: str) -> None:
    root = _project(tmp_path, MODULE + DECLARE + FORMS[name], USE)
    code, document = _verdict(root, release_core)
    assert _requires(document) in {"FAIL", "UNKNOWN"}, (name, document.get("frame"))
    assert code != 0, name


@pytest.mark.parametrize("name", sorted(PRECISION))
def test_dom_code_without_a_text_keeps_the_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    root = _project(tmp_path, MODULE + DECLARE + PRECISION[name], USE)
    code, document = _verdict(root, release_core)
    assert (code, document["status"]) == (0, "PASS"), (name, document.get("frame"))
