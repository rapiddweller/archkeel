// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script globals of a project (AD-508, #1547). File A reads `Math.min`. File B
// reads a member with a run-time key and calls the value later. Truth: node v26 runs each plant
// of `COVERED` with `o = () => 1`, `k = 'constructor'` and a text that overwrites `Math`, and
// `Math.min(1, 2)` is then 777 (the truth script is in the text of PR #1574). So each one must
// keep the read of `Math` in A from a proof. `DATA` holds uses that cannot call the value: they
// keep their proof.

use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "export const least = Math.min(1, 2);\n";

/// A helper that calls its argument.
const HELPERS: &str = "function run(f: any, t: any) { return f(t); }\n";

/// The project has a gap that holds the global `Math`.
fn gap(body: &str) -> bool {
    let b = format!("{HELPERS}export function f(o: any, k: string, t: any) {{\n{body}\n}}\n");
    let tree = Tree::new(&[("tsconfig.json", "{}"), ("src/a.ts", A), ("src/b.ts", &b)]);
    let facts = collect(&request(&tree, true), provenance());
    facts.gaps.iter().any(|gap| {
        gap.title.starts_with("Script global Math ")
            || gap
                .title
                .starts_with("A form that can write any global keeps every")
    })
}

/// The forms that call a looked-up value after it left the read (node writes `Math` in each).
const COVERED: [(&str, &str); 20] = [
    ("alias-call", "const p = o[k]; return p(t)();"),
    (
        "alias-call-member",
        "const p = o[k]; if (typeof p === 'function') { return p.call(o, t)(); }",
    ),
    (
        "alias-apply-member",
        "const p = o[k]; return p.apply(o, [t])();",
    ),
    ("array-literal", "const p = o[k]; return [p][0](t)();"),
    ("object-literal", "const q = { p: o[k] }; return q.p(t)();"),
    ("reflect-apply", "return Reflect.apply(o[k], o, [t])();"),
    ("bind-member", "const b = o[k].bind(o, t); return b()();"),
    (
        "prototype-bind",
        "const b = Function.prototype.bind.call(o[k], o, t); return b()();",
    ),
    ("assigned-later", "let p: any; p = o[k]; return p(t)();"),
    (
        "alias-of-alias",
        "const p = o[k]; const q = p; return q(t)();",
    ),
    ("array-pattern", "const [p] = [o[k]]; return p(t)();"),
    (
        "object-pattern",
        "const h = { p: o[k] }; const { p } = h; return p(t)();",
    ),
    ("argument", "const p = o[k]; return run(p, t)();"),
    (
        "returned",
        "function g(o2: any, k2: string) { return o2[k2]; } return g(o, k)(t)();",
    ),
    (
        "for-of-holder",
        "for (const p of [o[k]]) { return p(t)(); }",
    ),
    ("optional", "const p = o?.[k]; return p?.(t)();"),
    ("logical", "const p = o[k] || run; return p(t)();"),
    (
        "closure",
        "const p = o[k]; const c = () => p(t)(); return c();",
    ),
    (
        "json-key",
        "const key = JSON.parse('{\"k\":\"constructor\"}').k; const p = o[key]; return p(t)();",
    ),
    (
        "member-stored",
        "const h: any = {}; h.p = o[k]; return h.p(t)();",
    ),
];

#[test]
fn a_looked_up_value_that_is_called_later_keeps_the_global_from_a_proof() {
    let open: Vec<&str> = COVERED
        .iter()
        .filter(|(_, body)| !gap(body))
        .map(|(name, _)| *name)
        .collect();
    assert!(open.is_empty(), "no gap for: {open:?}");
}

/// Uses that cannot call the looked-up value: a test, a measure, a text, a member with a name
/// other than `call`, `apply` and `bind`, a write, and a loop over its elements.
const DATA: [(&str, &str); 13] = [
    ("typeof", "const v = o[k]; return typeof v === 'string';"),
    ("compare", "if (o[k] === undefined) { return 1; } return 0;"),
    ("condition", "const v = o[k]; return v ? 1 : 0;"),
    ("length", "const v = o[k]; return v.length;"),
    ("text", "return `${o[k]}`;"),
    ("sum", "const n = o[k] + 1; return n;"),
    ("write", "o[k] = t;"),
    ("compound", "o[k] += 1;"),
    ("delete", "delete o[k];"),
    (
        "plain-pattern",
        "const { a, b } = o[k]; return [a, b].length;",
    ),
    (
        "loop",
        "let n = 0; for (const x of o[k]) { n += x; } return n;",
    ),
    (
        "member-call",
        "const v = o[k]; return v.forEach((x: any) => x);",
    ),
    ("discarded", "o[k]; return 1;"),
];

#[test]
fn a_looked_up_value_that_no_call_can_reach_keeps_its_proof() {
    let gapped: Vec<&str> = DATA
        .iter()
        .filter(|(_, body)| gap(body))
        .map(|(name, _)| *name)
        .collect();
    assert!(gapped.is_empty(), "a gap for: {gapped:?}");
}

/// A hostile key keeps the gap: the text `constructor`, user input and a parsed key.
#[test]
fn a_hostile_key_keeps_the_gap() {
    for body in [
        "const p = o['constructor']; return p(t)();",
        "const p = o[t.key]; return p(t)();",
        "const p = o[JSON.parse(t).k]; return p(t)();",
        "const p = o[String(t)]; return [p][0](t)();",
    ] {
        assert!(gap(body), "a hostile key keeps the gap: {body}");
    }
}

/// A walk that leaves the file keeps the gap: an export, a top-level name of a script, a class
/// field and a default value.
#[test]
fn a_value_that_leaves_the_walk_keeps_the_gap() {
    for body in [
        "const p = o[k]; return p;",
        "const p = o[k]; return { p };",
        "const p = o[k]; return [...[p]];",
        "const p = o[k]; return function () { return p; };",
        "const p = o[k]; throw p;",
        "const p = o[k]; return new (class { q = p; })();",
        "const p = o[k]; return ((q = p) => q)();",
    ] {
        assert!(gap(body), "the value leaves the walk: {body}");
    }
    let exported = "export function h(o: any, k: string) { return 1; }\n\
                    declare const o: any; declare const k: string;\n\
                    export const p = o[k];\n";
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", A),
        ("src/b.ts", exported),
    ]);
    let facts = collect(&request(&tree, true), provenance());
    assert!(
        facts
            .gaps
            .iter()
            .any(|gap| gap.title.starts_with("A form that can write any global")),
        "an exported value leaves the walk"
    );
}
