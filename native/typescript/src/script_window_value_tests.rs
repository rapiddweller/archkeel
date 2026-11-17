// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script globals of a project (AD-460, AD-540, #1524). File A calls `window.open()`.
// File B writes through a value that the platform can make the window: an event target, the
// `this` of a method that a listener receives, or such a value passed on, returned or stored.
// The key is built at run time (`'op' + 'en'`). In a browser each plant replaces `open` (the
// audit of #1524 ran them in node with browser objects). So each one keeps `open` in A from a
// proof. `LOCAL` holds writes into values that the file makes: they keep their proof.

use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "window.open();\n";

#[test]
fn a_wrapped_platform_prototype_that_escapes_keeps_the_global_unproven() {
    assert!(gap("consume((((EventTarget.prototype as any))));"));
    assert!(gap("consume(((Object.getPrototypeOf(window) as any)));"));
}

/// The project has a gap that holds the global `open`.
fn gap(b: &str) -> bool {
    let b = format!("export {{}};\nconst k = ['op', 'en'].join('');\n{b}\n");
    let tree = Tree::new(&[("tsconfig.json", "{}"), ("src/a.ts", A), ("src/b.ts", &b)]);
    let facts = collect(&request(&tree, true), provenance());
    facts.gaps.iter().any(|gap| {
        gap.title.starts_with("Script global open ")
            || gap
                .title
                .starts_with("A form that can write any global keeps every")
    })
}

/// The 8 plants of #1524.
const WINDOW_VALUES: [(&str, &str); 8] = [
    (
        "event-target",
        "addEventListener('load', ev => { (ev.target as any)[k] = () => {}; });",
    ),
    (
        "event-src-element",
        "addEventListener('load', ev => { (ev.srcElement as any)[k] = () => {}; });",
    ),
    (
        "this-double-alias",
        "class C { m() { let a: any = this; let b = a; b[k] = () => {}; } }\n\
         addEventListener('load', new C().m);",
    ),
    (
        "super-result",
        "class C extends EventTarget { m() { const s: any = super.valueOf(); \
         s[k] = () => {}; } }\naddEventListener('load', new C().m);",
    ),
    (
        "this-argument",
        "function g(w: any) { w[k] = () => {}; }\nclass C { m() { g(this); } }\n\
         addEventListener('load', new C().m);",
    ),
    (
        "window-parameter",
        "function f(w: any) { w[k] = () => {}; }\n\
         addEventListener('load', ev => f(ev.target));",
    ),
    (
        "window-result",
        "function f(ev: any) { return ev.target; }\n\
         addEventListener('load', ev => { f(ev)[k] = () => {}; });",
    ),
    (
        "window-property",
        "addEventListener('load', ev => { const h = { w: ev.target as any }; \
         h.w[k] = () => {}; });",
    ),
];

/// Reflective writes through a window value (found while fixing #1524, same class).
const REFLECTIVE: [(&str, &str); 5] = [
    (
        "reflect-set",
        "addEventListener('load', ev => { Reflect.set(ev.target as any, k, () => {}); });",
    ),
    (
        "define-property",
        "addEventListener('load', ev => { Object.defineProperty(ev.target, k, { value: 1 }); });",
    ),
    (
        "assign",
        "addEventListener('load', ev => { Object.assign(ev.target as any, { open: 1 }); });",
    ),
    (
        "define-properties",
        "addEventListener('load', ev => { Object.defineProperties(ev.target, { open: {} }); });",
    ),
    (
        "reflect-define-property",
        "addEventListener('load', ev => { Reflect.defineProperty(ev.target as any, 'open', {}); });",
    ),
];

#[test]
fn a_write_with_a_run_time_key_through_a_window_value_keeps_the_global_from_a_proof() {
    let open: Vec<&str> = WINDOW_VALUES
        .iter()
        .chain(REFLECTIVE.iter())
        .filter(|(_, b)| !gap(b))
        .map(|(name, _)| *name)
        .collect();
    assert!(open.is_empty(), "no gap for: {open:?}");
}

/// Writes into values that the file makes, with a host entry: they keep the proof.
const LOCAL: [(&str, &str); 7] = [
    (
        "module-literal",
        "const cache: any = {};\naddEventListener('load', () => { cache[k] = 1; });",
    ),
    (
        "local-array",
        "addEventListener('load', () => { const r: any = []; r[k] = 1; });",
    ),
    (
        "assign-new-object",
        "addEventListener('load', () => Object.assign({}, { open: 1 }));",
    ),
    (
        "assign-created-object",
        "addEventListener('load', () => Object.assign(Object.create(null), { open: 1 }));",
    ),
    (
        "getter-on-local",
        "const o: any = {};\naddEventListener('load', () => o.__defineGetter__(k, () => 1));",
    ),
    (
        "compiled-enum",
        "var E: any;\n(function (E: any) { E[E['A'] = 0] = 'A'; })(E || (E = {}));\n\
         addEventListener('load', () => 1);",
    ),
    (
        "constructor-this",
        "class C { constructor() { (this as any)[k] = 1; } }\n\
         addEventListener('load', () => new C());",
    ),
];

#[test]
fn a_write_into_a_value_that_the_file_makes_keeps_the_proof() {
    let gapped: Vec<&str> = LOCAL
        .iter()
        .filter(|(_, b)| gap(b))
        .map(|(name, _)| *name)
        .collect();
    assert!(gapped.is_empty(), "a gap for: {gapped:?}");
}

/// A named write through a window value names its global. (Without a host entry a write through
/// a parameter keeps the proof: `the_premise_is_not_closed` in `script_host_tests.rs`.)
#[test]
fn a_named_write_through_a_window_value_names_its_global() {
    assert!(gap(
        "addEventListener('load', ev => { (ev.target as any).open = () => {}; });"
    ));
}

/// A reflective write through an alias of the member, through `call` or `apply`, and a getter or
/// setter that `__defineGetter__` or `__defineSetter__` puts on a window value.
const INDIRECT: [(&str, &str); 11] = [
    (
        "stored-member",
        "const a = Object.assign;\naddEventListener('load', ev => a(ev.target, { open: 1 }));",
    ),
    (
        "call-member",
        "addEventListener('load', ev => Object.assign.call(null, ev.target, { open: 1 }));",
    ),
    (
        "reflect-apply-set",
        "addEventListener('load', ev => Reflect.apply(Reflect.set, null, [ev.target, k, 1]));",
    ),
    (
        "destructured",
        "const { assign } = Object;\naddEventListener('load', ev => assign(ev.target, { open: 1 }));",
    ),
    (
        "object-alias",
        "const O = Object;\n\
         addEventListener('load', ev => O.defineProperty(ev.target, k, { value: 1 }));",
    ),
    (
        "through-global-this",
        "addEventListener('load', ev => globalThis.Object.assign(ev.target, { open: 1 }));",
    ),
    (
        "through-window-key",
        "addEventListener('load', ev => window['Reflect'].set(ev.target as any, k, 1));",
    ),
    (
        "define-getter",
        "addEventListener('load', ev => (ev.target as any).__defineGetter__(k, () => 1));",
    ),
    (
        "define-setter-literal-key",
        "addEventListener('load', ev => (ev.target as any)['__defineSetter__'](k, () => 1));",
    ),
    (
        "prototype-getter-call",
        "addEventListener('load', ev => \
         Object.prototype.__defineGetter__.call(ev.target, k, () => 1));",
    ),
    (
        "stored-getter",
        "addEventListener('load', ev => { const t: any = ev.target; \
         const d = t.__defineGetter__; d.call(t, k, () => 1); });",
    ),
];

#[test]
fn an_indirect_reflective_write_through_a_window_value_keeps_the_global_from_a_proof() {
    let open: Vec<&str> = INDIRECT
        .iter()
        .filter(|(_, b)| !gap(b))
        .map(|(name, _)| *name)
        .collect();
    assert!(open.is_empty(), "no gap for: {open:?}");
}
