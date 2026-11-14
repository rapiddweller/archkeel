# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The pattern plants of AD-512 (L-189): the names that a pattern binds or writes.

B-1: a function that calls a name that a pattern binds locally does not call the module symbol of
that name. B-2: a variable that a pattern, a compound operator, `++` or a `for` head writes does
not hold the value of its first write. Release 4.0.1 gives PASS for each plant (wrong); the core
gives UNKNOWN. Each row is `(files, UML target, release row, core row)`.
"""

from __future__ import annotations

from uml_symbol_plants import RELATIONSHIPS, edge, edit, more, signature, sym

Plant = tuple[dict[str, str], dict, str, str]


def _plant(source: str, entities: list[dict], edges: list[dict]) -> Plant:
    files = edit("export type Text", source + "export type Text")
    return (files, more(*entities, relationships=[*RELATIONSHIPS, *edges]), "PASS", "UNKNOWN")


def shadow(function: str, parameters: str, body: str) -> Plant:
    """`function` calls a name `helper` that its parameters or body bind; the target draws the
    call to the module function `helper`."""
    source = f"export function {function}({parameters}): void {{\n  {body}\n}}\n"
    entity = sym(function, "function", function)
    return _plant(source, [entity], [edge("calls", function, "helper")])


def written(function: str, body: str, annotation: str = "") -> Plant:
    """`body` writes `x` after `let x = new Unit()`; the target draws `x instance_of Unit`."""
    head = f"export function {function}(): void {{\n  let x{annotation} = new Unit();\n"
    source = head + f"  {body}\n}}\n"
    entities = [
        sym(function, "function", function, signature=signature("void")),
        sym(f"{function}-x", "binding", f"{function}.x", function, visibility=None),
    ]
    return _plant(source, entities, [edge("instance_of", f"{function}-x", "unit")])


PATTERN_PLANTS: dict[str, Plant] = {
    "bind-parameter-shorthand": shadow("p1", "{ helper }: { helper: any }", "helper(1);"),
    "bind-parameter-renamed": shadow("p2", "{ h: helper }: { h: any }", "helper(1);"),
    "bind-parameter-array": shadow("p3", "[helper]: any[]", "helper(1);"),
    "bind-parameter-rest": shadow("p4", "{ ...helper }: any", "helper(1);"),
    "bind-parameter-default": shadow("p5", "{ helper = Math.abs }: any", "helper(1);"),
    "bind-parameter-nested": shadow("p6", "{ a: { b: [helper] } }: any", "helper(1);"),
    "bind-parameter-rest-array": shadow("p7", "...[helper]: any[]", "helper(1);"),
    "bind-catch-pattern": shadow("c1", "", "try { } catch ({ helper }) { helper(1); }"),
    "bind-catch-array": shadow("c2", "", "try { } catch ([helper]) { helper(1); }"),
    "bind-for-of": shadow("f1", "fs: any[]", "for (const helper of fs) { helper(1); }"),
    "bind-for-of-pattern": shadow("f2", "fs: any[]", "for (const { helper } of fs) { helper(1); }"),
    "bind-for-in": shadow("f3", "table: any", "for (const helper in table) { helper(1); }"),
    "bind-for-head": shadow("f4", "", "for (let helper = go; helper; ) { helper(1); }"),
    "bind-declarator-pattern": shadow("d1", "holder: any", "const { helper } = holder; helper(1);"),
    "bind-declarator-array": shadow("d2", "holder: any[]", "const [helper] = holder; helper(1);"),
    "bind-enum": shadow("e1", "", "enum helper { A } helper(1);"),
    "bind-namespace": shadow("n1", "", "namespace helper { export const a = 1; } helper(1);"),
    "write-array": written("w1", "[x] = [new Client()];"),
    "write-object": written("w2", "({ x } = { x: new Client() });"),
    "write-for-of": written("w3", "for (x of [new Client()]) { }"),
    "write-for-in": written("w4", "for (x in { a: 1 }) { }"),
    "write-and-and": written("w5", "x &&= new Client();"),
    "write-or-or": written("w6", "x ||= new Client();"),
    "write-nullish": written("w7", "x ??= new Client();"),
    "write-increment": written("w8", "x++;"),
    "write-decrement": written("w9", "--x;"),
    "write-compound": written("wa", "x += 1;"),
    "write-array-rest": written("wb", "[...x] = [new Client()];"),
    "write-array-default": written("wc", "[x = new Client()] = [];"),
    "write-nested": written("wd", "({ a: [x] } = { a: [new Client()] });"),
    "write-renamed": written("we", "({ y: x } = { y: new Client() });"),
    "write-object-rest": written("wf", "({ ...x } = { z: 1 });"),
    "write-object-annotation": written("wg", "[x] = [new Client()];", ": object"),
    "write-compound-annotation": written("wh", "x &&= new Client();", ": object"),
}

# The head `for (let helper = ...)` is UNKNOWN in 4.0.1 too.
PATTERN_PLANTS["bind-for-head"] = (*PATTERN_PLANTS["bind-for-head"][:2], "UNKNOWN", "UNKNOWN")
WRONG_RELEASE_PATTERNS = {name for name in PATTERN_PLANTS if name != "bind-for-head"}

PATTERN_CAUSES = {
    **{name: "unresolved calls site" for name in PATTERN_PLANTS if name.startswith("bind-")},
    **{name: "absent symbol" for name in PATTERN_PLANTS if name.startswith("write-")},
}
