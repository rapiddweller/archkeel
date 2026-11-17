# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The TypeScript plants of a closed class scope (AD-747).

`PLANTS` gives, for each plant: the files, the UML target, the row of the core and the cause of a
row that is not PASS. A closed scope of a class, an interface or an enum passes only when the
collector states the member inventory of each listed kind complete. Each form that can add a
member that the body does not show keeps the row UNKNOWN. The truth of each form is the one that
`tsc` gives (TypeScript 5.9, `--strict`): AD-747 records it.
"""

from __future__ import annotations

from test_cli_core_uml_compare import ONE, module
from uml_symbol_plants import FILES, closed, edit, sym, target
from uml_symbol_sources import SOURCE

MEMBERS = ["attribute", "method"]
CLIENT = "export class Client implements Port {"


def client(scope: list[str] = MEMBERS, **fields: object) -> dict:
    """The base target with one closed scope of the class `Client`."""
    return target(scopes=[closed("client", scope, [])], **fields)


def inside(text: str) -> dict[str, str]:
    """The base files with `text` as the first line of the body of `Client`."""
    return edit(CLIENT, f"{CLIENT}\n  {text}")


def beside(path: str, text: str) -> dict[str, str]:
    """The base files and one more file."""
    return {**FILES, path: text}


PARTIAL = "closed scope completeness: the member inventory is partial"
MIX = "function Mix(base: any): any { return base; }\n"
# A script file (no import, no export) declares its names in the global scope: any other script
# file and any declaration file can merge an interface into them.
SCRIPT = {
    "src/a/one.ts": "class Client {\n  run(value: number): string { return String(value); }\n}\n",
    "src/b/t.ts": "interface Client { extra(): void; }\n",
}
SCRIPT_TARGET = target(
    [
        module("one", ONE),
        sym("client", "class", "Client", visibility=None),
        sym("run", "method", "Client.run", "client"),
    ],
    relationships=[],
    scopes=[closed("client", ["method"], [])],
)

JS = "app.src.a.one_x2e_js"
JAVASCRIPT = {
    "tsconfig.json": '{"compilerOptions": {"strict": true, "allowJs": true, "checkJs": true}}\n',
    "src/a/one.js": "export class Client {\n  constructor() { this.extra = 1; }\n"
    "  run(value) { return String(value); }\n}\n",
    "src/b/t.ts": "export const t = 1;\n",
}
JAVASCRIPT_TARGET = target(
    [
        module("one", JS),
        {**sym("client", "class", "Client"), "qualified_name": f"{JS}.Client"},
        {
            **sym("init", "method", "Client.constructor", "client"),
            "qualified_name": f"{JS}.Client.constructor",
        },
        {**sym("run", "method", "Client.run", "client"), "qualified_name": f"{JS}.Client.run"},
    ],
    relationships=[],
    scopes=[closed("client", MEMBERS, [])],
)

# name: (files, UML target, row of the core, cause of a row that is not PASS)
PLANTS: dict[str, tuple[dict[str, str], dict, str, str]] = {
    "complete-class": (FILES, client(), "PASS", ""),
    "complete-class-methods": (FILES, client(["method"]), "PASS", ""),
    "complete-interface": (FILES, target(scopes=[closed("port", ["method"], [])]), "PASS", ""),
    "complete-enum": (FILES, target(scopes=[closed("state", ["enum_literal"], [])]), "PASS", ""),
    # tsc: a class decorator does not change the type of the class; `extra` is no member.
    "decorator-made-member": (
        edit(
            CLIENT,
            "function made<T extends new (...a: any[]) => object>(base: T) {\n"
            "  return class extends base { extra(): void {} };\n}\n"
            f"@made\n{CLIENT}",
        ),
        client(),
        "PASS",
        "",
    ),
    "extra-method": (
        inside("extra(): void {}"),
        client(),
        "FAIL",
        "closed scope holds an unlisted definition",
    ),
    # tsc: an index signature makes each string key a member.
    "index-signature": (inside("[key: string]: any;"), client(), "UNKNOWN", PARTIAL),
    "computed-name": (inside("['ex' + 'tra'](): void {}"), client(), "UNKNOWN", PARTIAL),
    # tsc: an interface of the same name in the same scope merges its members into the class.
    "interface-merge": (
        edit("export enum State", "export interface Client { extra(): void; }\nexport enum State"),
        client(),
        "UNKNOWN",
        "scope without one definition",
    ),
    # tsc: a namespace of the same name adds static members (`Client.extra()`).
    "namespace-merge": (
        edit(
            "export enum State",
            "export namespace Client { export function extra(): void {} }\nexport enum State",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    # tsc: a module augmentation in another file merges `extra` into the class type.
    # The augmentation is a coverage gap of its file (#976): the run is not complete.
    "module-augmentation": (
        beside(
            "src/b/aug.ts",
            "export {};\ndeclare module '../a/one' { interface Client { extra(): void; } }\n",
        ),
        client(),
        "UNKNOWN",
        "the scope of the run is not complete",
    ),
    "namespace-dotted-merge": (
        edit(
            "export enum State",
            "export namespace Client.Inner { export const k = 1; }\nexport enum State",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "enum-namespace-merge": (
        edit(
            "export function helper",
            "export namespace State { export const extra = 1; }\nexport function helper",
        ),
        target(scopes=[closed("state", ["attribute", "enum_literal"], [])]),
        "UNKNOWN",
        PARTIAL,
    ),
    # tsc reads `this.extra = 1` in the constructor of a JavaScript class as a member.
    "javascript-this-write": (JAVASCRIPT, JAVASCRIPT_TARGET, "UNKNOWN", PARTIAL),
    "global-script-merge": (SCRIPT, SCRIPT_TARGET, "UNKNOWN", PARTIAL),
    "prototype-assign": (
        beside(
            "src/a/patch.ts",
            "import { Client } from './one';\n"
            "Object.assign(Client.prototype, { extra(): number { return 1; } });\n",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "prototype-write": (
        beside(
            "src/a/patch.ts",
            "import { Client } from './one';\n(Client.prototype as any).extra = (): number => 1;\n",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "static-assign": (
        beside(
            "src/a/patch.ts",
            "import { Client } from './one';\n"
            "Object.defineProperty(Client, 'extra', { value: 1 });\n",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "instance-spread": (
        edit(
            "  run(value: number): string { return helper(value); }",
            "  run(value: number): string {\n    Object.assign(this, { extra: 1 });\n"
            "    return helper(value);\n  }",
        ),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "mixin-base": (
        edit(CLIENT, f"{MIX}export class Client extends Mix(Unit) implements Port {{"),
        client(),
        "UNKNOWN",
        PARTIAL,
    ),
    "class-expression": (
        edit(CLIENT, "export const Client = class implements Port {"),
        client(),
        "UNKNOWN",
        "scope without one definition",
    ),
}

assert CLIENT in SOURCE
