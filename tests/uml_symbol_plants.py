# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The TypeScript plants of the symbol part of a UML target (AD-512).

`PLANTS` gives, for each plant: the files, the UML target, the row of release 4.0.1 on the same
tree and the row of the core. The core row is equal to the release row or stricter. `CAUSES` names
the cause of each row that is not PASS.
"""

from __future__ import annotations

from typing import Any

from test_cli_core_uml_compare import ONE, PROVENANCE, module

ROW = "UML-TARGET-a2e40c5592b1b06a"
PUBLIC = {"kind": "public", "basis": "declared"}
PRIVATE = {"kind": "private", "basis": "declared"}


def sym(identity: str, kind: str, name: str, parent: str = "one", **extra: Any) -> dict:
    """A planned symbol entity of the module `one`; `name` is below the module name."""
    entity = {
        "id": identity,
        "kind": kind,
        "qualified_name": f"{ONE}.{name}",
        "parent_id": parent,
        "language": "typescript",
        "presence": "planned",
        "provenance": PROVENANCE,
        "responsibilities": ["Hold it."],
        "visibility": PUBLIC,
        **extra,
    }
    return {key: value for key, value in entity.items() if value is not None}


def referenced(identity: str, kind: str, name: str, **extra: Any) -> dict:
    """An entity that the target only names: it is not planned and states no detail."""
    return {
        "id": identity,
        "kind": kind,
        "qualified_name": f"{ONE}.{name}",
        "language": "typescript",
        "presence": "referenced",
        "provenance": PROVENANCE,
        **extra,
    }


def edge(kind: str, source: str, target: str) -> dict:
    return {
        "id": f"{source}-{kind}-{target}",
        "kind": kind,
        "source_id": source,
        "target_id": target,
        "provenance": PROVENANCE,
    }


def param(name: str, annotation: str = "number") -> dict:
    return {"name": name, "annotation": annotation, "kind": "positional", "default_known": True}


def signature(returns: str, *parameters: dict) -> dict:
    return {"parameters": list(parameters), "returns": returns}


SOURCE = """import { t } from '../b/t';
export const used = t;
export interface Port { run(value: number): string; }
export class Unit {}
export class Client implements Port {
  private token: string = '';
  run(value: number): string { return helper(value); }
}
export enum State { READY = 'ready', STOPPED = 'stopped' }
export function helper(value: number): string { return String(value); }
export function build(): Unit {
  const item = new Unit();
  return item;
}
export type Text = string;
export const VERSION = 1;
"""
FILES = {"src/a/one.ts": SOURCE, "src/b/t.ts": "export const t = 1;\n"}
ENTITIES = [
    module("one", ONE),
    sym("port", "interface", "Port"),
    sym("port-run", "method", "Port.run", "port", signature=signature("string", param("value"))),
    sym("unit", "class", "Unit"),
    sym("client", "class", "Client"),
    sym("token", "attribute", "Client.token", "client", visibility=PRIVATE, annotation="string"),
    sym("run", "method", "Client.run", "client", signature=signature("string", param("value"))),
    sym("state", "enum", "State"),
    sym("ready", "enum_literal", "State.READY", "state"),
    sym("stopped", "enum_literal", "State.STOPPED", "state"),
    sym("helper", "function", "helper", signature=signature("string", param("value"))),
    sym("build", "function", "build", signature=signature("Unit")),
    sym("item", "binding", "build.item", "build", visibility=None),
    sym("text", "type_alias", "Text"),
    sym("version", "constant", "VERSION"),
]
RELATIONSHIPS = [
    edge("calls", "run", "helper"),
    edge("creates", "build", "unit"),
    edge("instance_of", "item", "unit"),
    edge("references", "build", "unit"),
]


def change(identity: str, **fields: Any) -> list[dict]:
    """The base entities with `fields` set on one of them; a `None` value removes the field."""
    changed = []
    for entity in ENTITIES:
        if entity["id"] == identity:
            entity = {**entity, **fields}
        changed.append({k: v for k, v in entity.items() if v is not None})
    return changed


def without(*identities: str) -> dict:
    """The base target without some entities and the relationships that name them."""
    gone = set(identities)
    return target(
        [e for e in ENTITIES if e["id"] not in gone],
        relationships=[
            r for r in RELATIONSHIPS if gone.isdisjoint({r["source_id"], r["target_id"]})
        ],
    )


def target(entities: list[dict] | None = None, **fields: Any) -> dict:
    return {
        "schema_version": "1.1.0",
        "entities": ENTITIES if entities is None else entities,
        "relationships": RELATIONSHIPS,
        "scopes": [],
        **fields,
    }


def closed(owner: str, entity_kinds: list[str], relationship_kinds: list[str]) -> dict:
    return {
        "scope_id": owner,
        "mode": "closed",
        "rationale": "Keep it closed.",
        "provenance": PROVENANCE,
        "entity_kinds": entity_kinds,
        "relationship_kinds": relationship_kinds,
    }


LOCAL_FUNCTION = """export function go(): number {
  function helper(value: number): string { return ''; }
  return helper(1).length;
}
"""
LOCAL_METHOD = """export class Holder {
  hold(): number {
    function helper(value: number): string { return ''; }
    return helper(1).length;
  }
}
"""
CATCH = """export function guard(): void {
  try { } catch (helper: any) { helper(1); }
}
"""
LOCAL_CLASS = """export function make(): void {
  class Unit {}
  const made = new Unit();
}
"""
TYPE_PARAMETER = "export function gen<Unit>(x: Unit): Unit { return x; }\n"
LOCAL_INTERFACE = """export function usePort(): void {
  interface Port {}
  const p: Port | undefined = undefined;
}
"""
LOCAL_BASE = """export function derive(): void {
  class Unit {}
  class Derived extends Unit {}
}
"""
ARROW = """export function arrow(): number {
  const helper = (value: number): string => '';
  return helper(1).length;
}
"""
PARAMETER = "export function take(helper: any): number { return helper(1); }\n"
REBOUND = """export function swap(): void {
  let swapped = new Unit();
  swapped = new Client();
}
"""
LOOSE = """export function loose(): void {
  let held: any = new Unit();
}
"""


MIXIN = """function Mix(base: any): any { return base; }
export interface I9 {}\nexport class Mx extends Mix(Unit) implements I9 {}
"""
CTOR = "export class PP { constructor(z: number) {} }\n"
HASH = "export class Pv { #x = 1; }\n"
DECORATED = """function mk(target: any): void {}
@mk
export class Dec {}
"""
MERGED = """export class Nm {}
export namespace Nm { export function f(): void {} }
"""
AMBIENT = "declare module 'ext' { export class Amb { z: number } }\n"
NAMESPACE = "export namespace Ns { export const k = 1; }\n"
OTHER = {
    "src/b/t.ts": "export function tfn(): void {}\nexport { real as shown } from './u';\n",
    "src/b/u.ts": "export function real(): void {}\n",
}


TARGET = "app.src.b.t_x2e_ts"
DYNAMIC = """export async function dyn(): Promise<void> {
  const loaded = await import('../b/t');
  loaded.tfn();
}
"""
NAMESPACE_IMPORT = """import * as ns from '../b/t';
export function viaNs(): void { ns.tfn(); }
"""
TYPE_IMPORT = """import type { Alias } from '../b/t';
export function useType(x: Alias): void {}
"""
RENAMED = """import { shown } from '../b/t';
export function viaShown(): void { shown(); }
"""
REQUIRED = """const t = require('../b/t');
export function viaRequire(): void { t.tfn(); }
"""
DROPPING = '{"compilerOptions": {"strict": true}, "exclude": ["src/a/hidden.ts"]}\n'
HIDDEN = """import { helper } from './one';
export function hid(): void { helper(1); }
"""


def foreign(identity: str, name: str, kind: str = "function") -> dict:
    """A planned symbol of another module of the plant."""
    extra = {"signature": signature("void")} if kind == "function" else {}
    entity = sym(identity, kind, name, parent=None, **extra)
    return {**entity, "qualified_name": f"{TARGET}.{name}"}


def edit(old: str, new: str) -> dict[str, str]:
    assert old in SOURCE
    return {**FILES, "src/a/one.ts": SOURCE.replace(old, new)}


BROKEN = {"src/b/bad.ts": "export const = ;\n"}


def more(*entities: dict, **fields: Any) -> dict:
    return target([*ENTITIES, *entities], **fields)


# name: (files, UML target, row of 4.0.1, row of the core)
PLANTS: dict[str, tuple[dict[str, str], dict, str, str]] = {
    "sym-pass": (FILES, target(), "PASS", "PASS"),
    "kind-differs": (FILES, target(change("helper", kind="class", signature=None)), "FAIL", "FAIL"),
    "parent-differs": (FILES, target(change("run", parent_id="unit")), "FAIL", "FAIL"),
    "return-differs": (
        FILES,
        target(change("helper", signature=signature("number", param("value")))),
        "FAIL",
        "FAIL",
    ),
    "parameter-name-differs": (
        FILES,
        target(change("helper", signature=signature("string", param("val")))),
        "FAIL",
        "FAIL",
    ),
    "parameter-count-differs": (
        FILES,
        target(change("helper", signature=signature("string", param("value"), param("more")))),
        "FAIL",
        "FAIL",
    ),
    "visibility-differs": (FILES, target(change("token", visibility=PUBLIC)), "FAIL", "FAIL"),
    "annotation-differs": (FILES, target(change("token", annotation="number")), "FAIL", "FAIL"),
    "initializer-differs": (
        FILES,
        target(change("item", initializer="new Other()")),
        "FAIL",
        "FAIL",
    ),
    "initializer-equal": (
        FILES,
        target(change("item", initializer="new Unit()")),
        "PASS",
        "PASS",
    ),
    "absent-symbol": (
        FILES,
        more(sym("ghost", "function", "ghost", signature=signature("void"))),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "ambiguous-name": (
        edit(
            "export type Text",
            "export function helper(value: number): string { return ''; }\nexport type Text",
        ),
        target(),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "namespace-interface": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "interface", "Both")),
        "PASS",
        "PASS",
    ),
    "namespace-constant": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "constant", "Both")),
        "PASS",
        "PASS",
    ),
    "namespace-class": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "class", "Both")),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-call": (
        FILES,
        target(relationships=[*RELATIONSHIPS, edge("calls", "helper", "build")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "closed-calls-listed": (
        FILES,
        target(
            relationships=[*RELATIONSHIPS, edge("calls", "build", "unit")],
            scopes=[closed("one", [], ["calls"])],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "unresolved-call-site": (
        edit("return helper(value); }", "return helper(value) + (value as any).go(); }"),
        target(
            relationships=[*RELATIONSHIPS, edge("calls", "build", "unit")],
            scopes=[closed("one", [], ["calls"])],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base": (
        FILES,
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "FAIL",
        "FAIL",
    ),
    "missing-base-incomplete": (
        {**FILES, **BROKEN},
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "present-base": (
        edit("export class Client implements", "export class Client extends Unit implements"),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "PASS",
        "PASS",
    ),
    "closed-function": (
        FILES,
        without("build", "item") | {"scopes": [closed("one", ["function"], [])]},
        "FAIL",
        "FAIL",
    ),
    "closed-calls": (
        FILES,
        target(relationships=[], scopes=[closed("one", [], ["calls"])]),
        "FAIL",
        "FAIL",
    ),
    "closed-method-extra": (
        FILES,
        without("run") | {"scopes": [closed("client", ["method"], [])]},
        "FAIL",
        "FAIL",
    ),
    "closed-method-listed": (
        FILES,
        target(scopes=[closed("client", ["method"], [])]),
        "PASS",
        "UNKNOWN",
    ),
    "referenced-found": (
        FILES,
        more(
            referenced("ref", "function", "helper"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "PASS",
        "PASS",
    ),
    "referenced-kind-differs": (
        FILES,
        more(
            referenced("ref", "class", "helper"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "PASS",
        "PASS",
    ),
    "referenced-absent": (
        FILES,
        more(
            referenced("ref", "function", "nothing"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-unresolved": (
        edit(
            "export class Client implements",
            "export class Client extends (globalThis as any).Base implements",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-external": (
        edit(
            "export class Client implements",
            "import { Ext } from 'external-lib';\nexport class Client extends Ext implements",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "global-name-is-no-definition": (
        FILES,
        more({**sym("string", "class", "x", parent=None), "qualified_name": "String"}),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "symbol-named-as-module": (
        FILES,
        more({**sym("named", "class", "x", parent=None), "qualified_name": ONE}),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-inner-unresolved": (
        edit(
            "run(value: number): string { return helper(value); }",
            "run(value: number): string { class Inner extends (globalThis as any).B {} "
            "return helper(value); }",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "closed-kind-differs": (
        FILES,
        target(
            change("helper", kind="class", signature=None), scopes=[closed("one", ["function"], [])]
        ),
        "FAIL",
        "FAIL",
    ),
    "closed-calls-kind-differs": (
        FILES,
        target(
            relationships=[
                edge("references", "run", "helper"),
                edge("calls", "build", "unit"),
            ],
            scopes=[closed("one", [], ["calls"])],
        ),
        "FAIL",
        "FAIL",
    ),
    # B-1: a name that a scope below the module declares is not the module symbol. 4.0.1 gives
    # PASS for each of these plants (wrong); the core gives UNKNOWN.
    "local-function-shadow": (
        edit("export type Text", LOCAL_FUNCTION + "export type Text"),
        more(
            sym("go", "function", "go", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "go", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-method-shadow": (
        edit("export type Text", LOCAL_METHOD + "export type Text"),
        more(
            sym("holder", "class", "Holder"),
            sym("hold", "method", "Holder.hold", "holder", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "hold", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "catch-binding-shadow": (
        edit("export type Text", CATCH + "export type Text"),
        more(
            sym("guard", "function", "guard", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("calls", "guard", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-class-creates-shadow": (
        edit("export type Text", LOCAL_CLASS + "export type Text"),
        more(
            sym("make", "function", "make", signature=signature("void")),
            sym("made", "binding", "make.made", "make", visibility=None),
            relationships=[
                *RELATIONSHIPS,
                edge("creates", "make", "unit"),
                edge("instance_of", "made", "unit"),
            ],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "type-parameter-shadow": (
        edit("export type Text", TYPE_PARAMETER + "export type Text"),
        more(
            sym("gen", "function", "gen", signature=signature("Unit", param("x", "Unit"))),
            relationships=[*RELATIONSHIPS, edge("references", "gen", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-interface-shadow": (
        edit("export type Text", LOCAL_INTERFACE + "export type Text"),
        more(
            sym("use-port", "function", "usePort", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("references", "use-port", "port")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-base-shadow": (
        edit("export type Text", LOCAL_BASE + "export type Text"),
        more(
            sym("derived", "class", "derive.Derived", "derive"),
            sym("derive", "function", "derive", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("inherits", "derived", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    # Controls: 4.0.1 and the core give UNKNOWN already.
    "local-arrow-control": (
        edit("export type Text", ARROW + "export type Text"),
        more(
            sym("arrow", "function", "arrow", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "arrow", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "parameter-control": (
        edit("export type Text", PARAMETER + "export type Text"),
        more(
            sym("take", "function", "take", signature=signature("number", param("helper", "any"))),
            relationships=[*RELATIONSHIPS, edge("calls", "take", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    # B-2: a variable that is written twice or typed any or unknown is not proven.
    "rebound-binding": (
        edit("export type Text", REBOUND + "export type Text"),
        more(
            sym("swap", "function", "swap", signature=signature("void")),
            sym("swapped", "binding", "swap.swapped", "swap", visibility=None),
            relationships=[*RELATIONSHIPS, edge("instance_of", "swapped", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "any-binding": (
        edit("export type Text", LOOSE + "export type Text"),
        more(
            sym("loose", "function", "loose", signature=signature("void")),
            sym("held", "binding", "loose.held", "loose", visibility=None),
            relationships=[*RELATIONSHIPS, edge("instance_of", "held", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    # Part A: planned class members that the class lacks are FAIL in 4.0.1 and UNKNOWN in the core.
    "mixin-base-receipt": (
        edit("export type Text", MIXIN + "export type Text"),
        more(
            sym("mx", "class", "Mx"),
            relationships=[*RELATIONSHIPS, edge("realizes", "mx", "port")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "member-plain-constructor-parameter": (
        edit("export type Text", CTOR + "export type Text"),
        more(sym("pp", "class", "PP"), sym("pp-z", "attribute", "PP.z", "pp")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-hash-private": (
        edit("export type Text", HASH + "export type Text"),
        more(sym("pv", "class", "Pv"), sym("pv-x", "attribute", "Pv.x", "pv")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-enum-literal-gone": (
        FILES,
        more(sym("gone", "enum_literal", "State.GONE", "state")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-decorator-made": (
        edit("export type Text", DECORATED + "export type Text"),
        more(
            sym("dec", "class", "Dec"),
            sym("dec-gen", "method", "Dec.gen", "dec", signature=signature("void")),
        ),
        "FAIL",
        "UNKNOWN",
    ),
    "member-namespace-merge": (
        edit("export type Text", MERGED + "export type Text"),
        more(
            sym("nm", "class", "Nm"),
            sym("nm-f", "method", "Nm.f", "nm", signature=signature("void")),
        ),
        "FAIL",
        "UNKNOWN",
    ),
    # Part A: a symbol of an ambient module or a namespace is no module-level symbol of the file.
    "ambient-module-class": (
        edit("export type Text", AMBIENT + "export type Text"),
        more(
            sym("amb", "class", "Amb"),
            sym("amb-z", "attribute", "Amb.z", "amb", annotation="number"),
        ),
        "PASS",
        "UNKNOWN",
    ),
    "namespace-member-constant": (
        edit("export type Text", NAMESPACE + "export type Text"),
        more(sym("k", "constant", "k")),
        "PASS",
        "UNKNOWN",
    ),
    # Not run by the reviewers: each form must not give PASS without proof.
    "dynamic-import": (
        {**edit("export type Text", DYNAMIC + "export type Text"), **OTHER},
        more(
            sym("dyn", "function", "dyn", signature=signature("Promise<void>")),
            foreign("tfn", "tfn"),
            relationships=[*RELATIONSHIPS, edge("calls", "dyn", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "namespace-import-call": (
        {**edit("export type Text", NAMESPACE_IMPORT + "export type Text"), **OTHER},
        more(
            sym("via-ns", "function", "viaNs", signature=signature("void")),
            foreign("tfn", "tfn"),
            relationships=[*RELATIONSHIPS, edge("calls", "via-ns", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "type-import-reference": (
        {**edit("export type Text", TYPE_IMPORT + "export type Text"), **OTHER},
        more(
            sym(
                "use-type", "function", "useType", signature=signature("void", param("x", "Alias"))
            ),
            foreign("alias", "Alias", "type_alias"),
            relationships=[*RELATIONSHIPS, edge("references", "use-type", "alias")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "renamed-reexport-call": (
        {**edit("export type Text", RENAMED + "export type Text"), **OTHER},
        more(
            sym("via-shown", "function", "viaShown", signature=signature("void")),
            foreign("shown", "shown"),
            relationships=[*RELATIONSHIPS, edge("calls", "via-shown", "shown")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "require-in-cts": (
        {**OTHER, "src/a/c.cts": REQUIRED},
        target(
            [
                module("c", ONE.replace("one_x2e_ts", "c_x2e_cts")),
                sym("via-require", "function", "viaRequire", signature=signature("void"))
                | {
                    "qualified_name": ONE.replace("one_x2e_ts", "c_x2e_cts") + ".viaRequire",
                    "parent_id": "c",
                },
                foreign("tfn", "tfn"),
            ],
            relationships=[edge("calls", "via-require", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "site-in-dropped-file": (
        {
            **FILES,
            "src/a/hidden.ts": HIDDEN,
            "tsconfig.json": DROPPING,
        },
        more(
            sym("hid", "function", "hid", signature=signature("void"))
            | {
                "qualified_name": ONE.replace("one_x2e_ts", "hidden_x2e_ts") + ".hid",
                "parent_id": "one",
            },
            relationships=[*RELATIONSHIPS, edge("calls", "hid", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "pass-incomplete": ({**FILES, **BROKEN}, target(), "UNKNOWN", "UNKNOWN"),
}


# The named cause of each row that is not PASS: a part of the reason of an UNKNOWN row, or of the
# cause of a FAIL detail. A row with another cause is another defect.
CAUSES: dict[str, str | tuple[str, ...]] = {
    "kind-differs": "recorded entity kind differs",
    "parent-differs": "lexical parent differs",
    "return-differs": "return annotation differs",
    "parameter-name-differs": "parameter name or order differs",
    "parameter-count-differs": "parameter count differs",
    "visibility-differs": "visibility or its basis differs",
    "annotation-differs": "annotation differs",
    "initializer-differs": "initializer syntax differs",
    "absent-symbol": "absent symbol",
    "ambiguous-name": "several definitions share a declared name",
    "namespace-class": "several definitions share a declared name",
    "missing-call": "unresolved calls site",
    "closed-calls": "closed scope holds an unlisted relationship",
    "closed-calls-listed": "closed scope completeness",
    "unresolved-call-site": "closed scope completeness",
    "missing-base": "declared base is absent",
    "missing-base-incomplete": "inherits inventory is not complete",
    "missing-base-unresolved": "unresolved inherits site",
    "missing-base-external": "unresolved inherits site",
    "closed-function": "closed scope holds an unlisted definition",
    "closed-method-extra": "closed scope holds an unlisted definition",
    "closed-method-listed": "closed scope completeness",
    "referenced-absent": "relationship endpoints cannot be identified uniquely",
    "global-name-is-no-definition": "absent symbol",
    "symbol-named-as-module": "absent symbol",
    "missing-base-inner-unresolved": "inherits inventory is not complete",
    "closed-kind-differs": (
        "recorded entity kind differs",
        "closed scope holds an unlisted definition",
    ),
    "closed-calls-kind-differs": "closed scope holds an unlisted relationship",
    "pass-incomplete": "the scope of the run is not complete",
    "local-function-shadow": "unresolved calls site",
    "local-method-shadow": "unresolved calls site",
    "catch-binding-shadow": "unresolved calls site",
    "local-class-creates-shadow": "unresolved creates site",
    "type-parameter-shadow": "unresolved references site",
    "local-interface-shadow": "unresolved references site",
    "local-base-shadow": "unresolved inherits site",
    "local-arrow-control": "unresolved calls site",
    "parameter-control": "unresolved calls site",
    "rebound-binding": "absent symbol",
    "any-binding": "absent symbol",
    "mixin-base-receipt": "realizes inventory is not complete",
    "member-plain-constructor-parameter": "absent symbol",
    "member-hash-private": "absent symbol",
    "member-enum-literal-gone": "absent symbol",
    "member-decorator-made": "absent symbol",
    "member-namespace-merge": "absent symbol",
    "ambient-module-class": "absent symbol",
    "namespace-member-constant": "absent symbol",
    "dynamic-import": "unresolved calls site",
    "namespace-import-call": "unresolved calls site",
    "type-import-reference": "absent symbol",
    "renamed-reexport-call": "absent symbol",
    "require-in-cts": "unresolved calls site",
    "site-in-dropped-file": "absent symbol",
}


# The core PASS needs resolved definitions and a complete scope. Where 4.0.1 passes on partial
# coverage, the core stays UNKNOWN (AD-512 lists the forms). Any other difference is a bug.
# (equal, PASS to UNKNOWN, FAIL to UNKNOWN, all plants)
COUNTS = (44, 12, 5, 61)
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# Plants where the 4.0.1 PASS is wrong: the drawn relationship or symbol is absent in the code.
# The core gives UNKNOWN for them, so they are no limit of the core (AD-512).
WRONG_RELEASE_PASS = {
    "local-function-shadow",
    "local-method-shadow",
    "catch-binding-shadow",
    "local-class-creates-shadow",
    "type-parameter-shadow",
    "local-interface-shadow",
    "local-base-shadow",
    "rebound-binding",
    "any-binding",
    "ambient-module-class",
    "namespace-member-constant",
}
