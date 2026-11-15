// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script globals of a project (AD-540). File A reads `Math.min`. File B is the
// plant. `reads_math` states what TypeScript and the host do: whether the read of `Math` in A can
// be changed by B. The expected answer of the collector is `gap` when that is possible or when the
// form is not proven away; `complete` only for a form that cannot write a global without a host
// entry. Each plant says which one it is.

use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "export const least = Math.min(1, 2);\n";

/// Whether the project has a gap for the global `Math`.
fn gap(files: &[(&str, &str)]) -> bool {
    let mut all = vec![("tsconfig.json", "{}"), ("src/a.ts", A)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    let facts = collect(&request(&tree, true), provenance());
    facts.gaps.iter().any(|gap| {
        gap.title.starts_with("Script global Math ")
            || gap
                .title
                .starts_with("A form that can write any global keeps every")
    })
}

fn with_b(source: &str) -> bool {
    gap(&[("src/b.ts", source)])
}

/// A module file with a function that holds `body`, and `export {}` so that it is a module.
fn module(body: &str) -> String {
    format!("export function run(o: any, k: string, v: any, e: any) {{\n{body}\n}}\n")
}

#[test]
fn a_project_of_inert_names_has_no_gap() {
    assert!(!with_b("export const x = Object.keys({});"));
    assert!(!gap(&[]));
}

#[test]
fn an_amplifier_form_is_no_write_without_a_host_entry() {
    let keep = "function keep(x: any) { return x; }\n";
    let forms = [
        "export const a = (l: any) => keep(l.source);",
        "export const b = { it() { return this; } };",
        "export function c(rows: number[][], n: number) { for (let j = 0; j <= n; j++) { rows[0][j] = j; } }",
        "export const d = (o: any) => { const { source } = o; return source; };",
        "export const e = (o: any) => keep(o.parent);",
        "export function f(fns: Array<() => void>) { for (let i = 0; i < fns.length; i++) fns[i](); }",
        "export const g = (it: any) => it[Symbol.asyncIterator]();",
        "export function h(r: number[][], n: number) { return keep(r[(n - 2) % 3][n - 2]); }",
    ];
    for form in forms {
        let source = format!("{keep}{form}");
        assert!(!with_b(&source), "no host entry, no gap: {form}");
    }
}

#[test]
fn the_premise_is_not_closed() {
    // PREMISE: a caller outside the scan can give the window. Main reads `set` the same way.
    for source in [
        "export function set(o: any, k: string, v: any) { o[k] = v; }",
        "export function h(e: any) { return e.source; }",
    ] {
        assert!(!with_b(source), "the premise covers: {source}");
    }
}

#[test]
fn a_direct_form_blocks_in_a_scan_without_a_host_entry() {
    let forms = [
        "const g = globalThis; g[k] = v;",
        "Function('return this')()[k] = v;",
        "new Function(k)();",
        "(0, eval)('this')[k] = v;",
        "eval(k);",
        "({}).constructor.constructor('return this')()[k] = v;",
        "setTimeout('Math = 1');",
        "Reflect.set(globalThis, k, v);",
        "Object.defineProperty(window, k, {});",
        "Object.assign(self, o);",
        "const f = (() => 1)[k + 'x']; f;",
        "const c = 'con' + 'structor'; (() => 1)[c]('return this')()[k] = v;",
        "const c = 'con' + 'structor'; o[c][c]('return this')()[k] = v;",
        "let i = 0; i = k; const fns: any[] = []; fns[i]('x');",
        "let i = 0; i += k; const fns: any[] = []; fns[i]('x');",
        "o[k]('x');",
        // A write through a window-like member with a run-time key: a callback or a factory of
        // the caller can give the object (review of #1224, `callback-premise`, `factory-premise`).
        "o(); const h = { parent: {} }; const c = 'x' + 'y'; h.parent[c] = 1;",
        "const h = { parent: o() }; h.parent['Ma' + 'th'] = { min: () => 777 };",
        "e.source[k] = 1;",
        "this[k] = v;",
    ];
    for form in forms {
        assert!(with_b(&module(form)), "a direct form blocks: {form}");
    }
}

#[test]
fn a_host_entry_makes_an_amplifier_form_write() {
    let amplifier =
        "export const a = (l: any) => l.source[0];\nexport const b = (o: any) => o.parent;\n";
    let hosts = [
        "addEventListener('message', (e: any) => { e.source[k] = v; });",
        "document.defaultView[k] = v;",
        "setTimeout(function () { this[k] = v; });",
        "console.log(1);",
        "process.nextTick(() => 1);",
        "const x = globalThis.self || {}; x[k] = v;",
        "keep(typeof window, window.foo());",
        "keep(globalThis.process || 1);",
        "keep(require('fs'));",
    ];
    for host in hosts {
        let source =
            format!("{amplifier}export function z(k: string, v: any, keep: any) {{ {host} }}\n");
        assert!(with_b(&source), "a host name is an entry: {host}");
    }
    assert!(!with_b(amplifier), "the control has no host entry");
}

#[test]
fn a_contained_use_of_a_host_name_is_no_entry() {
    let amplifier = "export const a = (l: any) => l.source[0];\n";
    let uses = [
        "export const w = typeof window !== 'undefined';",
        "export const p = globalThis.process && process.env.NODE_ENV === 'production';",
        "export const q = !document.hidden;",
        "export const r = typeof globalThis;",
        "export function s() { if (window.foo) { return 1; } return 2; }",
        "export const t = window.name == 'x' ? 1 : 2;",
        "export const u = typeof process?.versions?.node === 'string';",
    ];
    for used in uses {
        let source = format!("{amplifier}{used}\n");
        assert!(!with_b(&source), "contained: {used}");
    }
}

#[test]
fn a_use_that_leaves_the_place_is_an_entry() {
    let amplifier = "export const a = (l: any) => l.source[0];\n";
    let uses = [
        "export const w = window;",
        "export const p = process;",
        "export const q = document.createElement('div');",
        "export const r = globalThis.process || {};",
        "export const s = globalThis.process ?? {};",
        "export const t = [typeof window, window.name];",
        "export const u = (window as any)[1];",
        "export const v = { document };",
        "export const x = typeof window.f();",
        "export const y = () => arguments;",
    ];
    for used in uses {
        let source = format!("{amplifier}{used}\n");
        assert!(with_b(&source), "not contained: {used}");
    }
}

#[test]
fn a_file_that_is_no_module_is_an_entry() {
    let amplifier = "export const a = (l: any) => l.source[0];\n";
    let scripts = [
        "var Math2 = 1; function f() { this.x = 1; }",
        "function f() { return this; }",
        "import fs = require('fs'); export {};",
        "const c = 1; export = c;",
        "export function g(o: any) { with (o) { o.x; } }",
    ];
    for script in scripts {
        let files = [("src/b.ts", amplifier), ("src/c.ts", script)];
        assert!(gap(&files), "no module: {script}");
    }
    assert!(!gap(&[("src/b.ts", amplifier), ("src/c.ts", "export {};")]));
}

#[test]
fn a_named_write_or_a_syntax_error_still_blocks() {
    assert!(with_b("export {}; (globalThis as any).Math = 1;"));
    assert!(with_b(
        "export {}; declare global { var Math: any; }\n(globalThis as any).Math = 1;"
    ));
    assert!(with_b("export function f(o: any) { o.Math = 1; }"));
    assert!(with_b("export const x = ;"));
    // A declare alone writes nothing.
    assert!(!with_b("export {}; declare global { var Mathx: any; }"));
}

#[test]
fn a_key_that_is_no_number_is_a_run_time_key() {
    let forms = [
        "export function f(i: any, fns: any[]) { return fns[i](1); }",
        "export function f(fns: any[]) { for (const i in fns) fns[i](1); }",
        "export function f(fns: any[]) { let i: any = 0; i = 'x'; fns[i](1); }",
        "export function f(fns: any[], n: any) { let i = n; fns[i](1); }",
        "export function f(fns: any[]) { let i = 0, i2 = i; i2 += 'x'; fns[i2](1); }",
        "export function f(fns: any[]) { for (let i = 0; i < 2; i++) { i = i + 'x'; fns[i](1); } }",
        "export function f(it: any) { return it[Symbol.for('constructor')](1); }",
        "export function f(it: any) { return it[Symbol.name](1); }",
    ];
    for form in forms {
        assert!(with_b(form), "a key that is no number: {form}");
    }
    let numbers = [
        "export function f(fns: any[]) { for (let i = 0; i < 2; i++) fns[i](1); }",
        "export function f(fns: any[]) { let i = 1; i *= 2; i++; return fns[i](1); }",
        "export function f(fns: any[], n: number) { return fns[(n - 1) % 3](1); }",
        "export function f(r: number[][], n: number) { let j = 0; j += n * 2; return r[0][j]; }",
    ];
    for form in numbers {
        assert!(!with_b(form), "a number key: {form}");
    }
}

fn titles_of(files: &[(&str, &str)]) -> Vec<(String, Option<String>)> {
    let mut all = vec![("tsconfig.json", "{}"), ("src/a.ts", A)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    let facts = collect(&request(&tree, true), provenance());
    facts
        .gaps
        .iter()
        .map(|gap| (gap.title.clone(), gap.data.collector_message()))
        .collect()
}

#[test]
fn a_direct_form_is_stated_once_and_not_once_for_each_use() {
    let b = "export function f(k: string) { Function('return this')(); eval(k); }\n\
             export const g = Object.keys({}).length + Math.max(1, 2);\n";
    let found = titles_of(&[("src/b.ts", b)]);
    let blockers: Vec<_> = found
        .iter()
        .filter(|(title, _)| title.starts_with("A form that can write any global keeps every"))
        .collect();
    assert_eq!(
        blockers.len(),
        2,
        "one gap for each blocking node: {found:?}"
    );
    assert!(
        found
            .iter()
            .all(|(title, _)| !title.starts_with("Script global ")),
        "{found:?}"
    );
    let said = blockers[0].1.as_deref().unwrap_or_default();
    assert!(said.ends_with("free standard names depend on it"), "{said}");
    assert!(said.contains("5 uses of 4 free"), "Math and Object: {said}");
    assert_eq!(
        blockers[0].1, blockers[1].1,
        "the count is the same for each node"
    );
    // The reason has no count and no line, so a baseline entry keeps its key.
    assert!(blockers
        .iter()
        .all(|(title, _)| !title.chars().any(|c| c.is_ascii_digit())));
}

#[test]
fn a_name_with_a_named_write_keeps_its_own_gap() {
    let b = "export function f(o: any) { o.Math = 1; Function('x'); }\n";
    let found = titles_of(&[("src/b.ts", b)]);
    assert!(
        found
            .iter()
            .any(|(title, _)| title.starts_with("Script global Math ")),
        "{found:?}"
    );
    assert!(found
        .iter()
        .any(|(title, _)| title.starts_with("A form that can write any global")));
    let clean = titles_of(&[("src/b.ts", "export const x = Object.keys({});\n")]);
    assert!(clean.is_empty(), "{clean:?}");
}

/// Whether the project has a gap for the free name `process`.
fn process_gap(files: &[(&str, &str)]) -> bool {
    titles_of(files)
        .iter()
        .any(|(title, _)| title.starts_with("Script global process "))
}

#[test]
fn a_contained_read_of_a_host_name_that_nothing_writes_is_no_gap() {
    let reads = [
        "export const p = globalThis.process && process.env.NODE_ENV === 'production';",
        "export const t = typeof process !== 'undefined';",
        "export const n = !process.env.CI;",
        "export function s() { if (process.env.A) { return 1; } return 2; }",
        "export const q = process.env.A == 'x' ? 1 : 2;",
    ];
    for read in reads {
        assert!(!process_gap(&[("src/b.ts", read)]), "a read: {read}");
        // A direct form of the project could write the name, so the read is stated under it.
        let with_form = [
            ("src/b.ts", read),
            ("src/c.ts", "export function c(k: string) { Function(k); }"),
        ];
        let found = titles_of(&with_form);
        assert!(found
            .iter()
            .all(|(title, _)| !title.starts_with("Script global process ")));
        assert!(found
            .iter()
            .any(|(title, _)| title.starts_with("A form that can write")));
    }
}

#[test]
fn a_use_that_calls_stores_or_passes_a_host_name_keeps_its_gap() {
    let uses = [
        "export function f() { process.nextTick(() => 1); }",
        "export const p = process;",
        "export const e = process.env.NODE_ENV || 'x';",
        "export const e = process.env.NODE_ENV ?? 'x';",
        "export const k = (name: string) => process.env[name] === 'x';",
        "export function g(f: any) { f(process.env); }",
    ];
    for used in uses {
        assert!(process_gap(&[("src/b.ts", used)]), "not a read: {used}");
    }
}

#[test]
fn a_host_name_that_a_file_writes_keeps_its_gap_for_a_read() {
    let read = "export const t = typeof process !== 'undefined';";
    for writer in [
        "export const w = ((globalThis as any).process = 1);",
        "export function w(o: any) { o.process = 1; }",
    ] {
        let files = [("src/b.ts", read), ("src/c.ts", writer)];
        assert!(process_gap(&files), "a write blocks the name: {writer}");
    }
    let script = [("src/b.ts", read), ("src/c.ts", "window.process = {};")];
    assert!(process_gap(&script), "a published name has a publisher");
}

#[test]
fn the_instance_of_shape_of_graphql_js_is_no_gap() {
    let source = "import { inspect } from './inspect';\n\
        const isProduction =\n  globalThis.process &&\n  // eslint-disable-next-line no-undef\n  process.env.NODE_ENV === 'production';\n\
        export const f = (v: unknown) => (isProduction ? inspect(v) : v);\n";
    let files = [
        ("src/b.ts", source),
        (
            "src/inspect.ts",
            "export const inspect = (v: unknown) => String(v);",
        ),
    ];
    assert!(!process_gap(&files), "{:?}", titles_of(&files));
}

#[test]
fn an_amplifier_form_in_a_scan_with_a_host_entry_is_stated_once() {
    let b = "export const a = (l: any) => l.source;\nexport function z() { console.log(1); }\n";
    let found = titles_of(&[("src/b.ts", b)]);
    assert!(
        found
            .iter()
            .all(|(title, _)| !title.starts_with("Script global ")),
        "{found:?}"
    );
    let stated: Vec<_> = found
        .iter()
        .filter(|(title, _)| title.contains("a member that can be the window"))
        .collect();
    assert_eq!(stated.len(), 1, "{found:?}");
    assert!(stated[0]
        .1
        .as_deref()
        .unwrap_or_default()
        .contains("depend on it"));
}
