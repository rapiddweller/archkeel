# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A patch of a platform prototype gives no PASS (#1527, AD-460).

Consumer: `archkeel validate` on a TypeScript project, through the release core. A module file of
`b` changes a prototype that the global object inherits from, and `a` calls
`window.dispatchEvent(...)`. The call then runs the code of `b`, so the rule must not PASS. Node
26 runs each patched plant in a VM with a synthetic `EventTarget` and reaches the function of `b`.
The group `PRECISION` must keep its PASS: a read of a prototype member, an element of it and a
comparison are no patch of the global object.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_native_global_writes import MODULE, _project, _requires, _verdict

DECLARE = "declare const k: string, x: any, g: any;\n"
USE = "window.dispatchEvent(new Event('audit'));\n"
SET = "{ value: () => true }"

# Each form below can replace `dispatchEvent` of `EventTarget.prototype` or of the global object.
PATCHES = {
    # The audit plant of #1527.
    "define-property": f"Object.defineProperty(EventTarget.prototype, 'dispatchEvent', {SET});",
    "define-properties": (
        f"Object.defineProperties(EventTarget.prototype, {{ dispatchEvent: {SET} }});"
    ),
    "reflect-define": f"Reflect.defineProperty(EventTarget.prototype, 'dispatchEvent', {SET});",
    "reflect-set": "Reflect.set(EventTarget.prototype, 'dispatchEvent', () => true);",
    "assign": "Object.assign(EventTarget.prototype, { dispatchEvent: () => true });",
    "runtime-key": "(EventTarget.prototype as any)[k] = () => true;",
    "string-key-prototype": "(EventTarget as any)['prototype'][k] = () => true;",
    "stored-prototype": "const p: any = EventTarget.prototype;\np.dispatchEvent = () => true;",
    "passed-prototype": "g(EventTarget.prototype);",
    "alias-constructor": (
        f"const E = EventTarget;\nObject.defineProperty(E.prototype, 'dispatchEvent', {SET});"
    ),
    "prototype-of-window": (
        f"Object.defineProperty(Object.getPrototypeOf(window), 'dispatchEvent', {SET});"
    ),
    "prototype-of-document": (
        "let p: any = document;\n"
        "while (!Object.prototype.hasOwnProperty.call(p, 'dispatchEvent'))\n"
        "  p = Object.getPrototypeOf(p);\np[k] = () => true;"
    ),
    "proto-member": f"Object.defineProperty((window as any).__proto__, 'dispatchEvent', {SET});",
    "proto-write": "(window as any).__proto__ = { dispatchEvent: () => true };",
    "event-proto-write": (
        "addEventListener('load', (ev: any) => { ev.target.__proto__ = { dispatchEvent: g }; });"
    ),
    "set-prototype-of": "Object.setPrototypeOf(window, { dispatchEvent: () => true });",
    # The `prototype` of a function can be written; only a class keeps its own prototype.
    "function-prototype": (
        "function F() {}\nF.prototype = EventTarget.prototype;\n"
        "(F.prototype as any)[k] = () => true;"
    ),
    "class-written": (
        "let C: any = class {};\nC = EventTarget;\n"
        f"Object.defineProperty(C.prototype, 'dispatchEvent', {SET});"
    ),
}

# A read of a prototype member, a comparison and a patch of a class of the file keep the PASS.
PRECISION = {
    "has-own": "export const has = (o: object) => Object.prototype.hasOwnProperty.call(o, 'a');",
    "slice": "export const list = (a: any) => Array.prototype.slice.call(a);",
    "compare": "export const plain = (o: object) => Object.getPrototypeOf(o) === Object.prototype;",
    # The form of graphql-js `instanceOf.ts:30`: an element of a prototype is no prototype.
    "element-read": "export const first = (c: any) => c.prototype[0];",
}


@pytest.mark.parametrize("name", sorted(PATCHES))
def test_a_prototype_patch_holds_the_rule(tmp_path: Path, release_core: Path, name: str) -> None:
    root = _project(tmp_path, MODULE + DECLARE + PATCHES[name], USE)
    code, document = _verdict(root, release_core)
    assert _requires(document) in {"FAIL", "UNKNOWN"}, (name, document.get("frame"))
    assert code != 0, name


@pytest.mark.parametrize("name", sorted(PRECISION))
def test_a_prototype_read_keeps_the_pass(tmp_path: Path, release_core: Path, name: str) -> None:
    root = _project(tmp_path, MODULE + PRECISION[name], USE)
    code, document = _verdict(root, release_core)
    assert (code, document["status"]) == (0, "PASS"), (name, document.get("frame"))
