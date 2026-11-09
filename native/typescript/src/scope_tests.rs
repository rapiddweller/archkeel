// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk. The lookup through the frames and the targets of a nested pattern follow
// `_script_bound_scope` and `_assignment_targets`; the walk tests compare them with Python.

use super::*;
use crate::parse::parse;
use crate::syntax::Parsers;

#[test]
fn a_lookup_climbs_to_the_nearest_frame_that_binds_the_name() {
    let mut frames = Frames::new();
    let outer = frames.push(ROOT);
    let inner = frames.push(outer);
    frames.bind(ROOT, "top".to_owned());
    frames.bind(outer, "mid".to_owned());
    frames.bind(outer, "top".to_owned());
    assert_eq!(frames.bound_scope(inner, "top"), Some(outer));
    assert_eq!(frames.bound_scope(inner, "mid"), Some(outer));
    assert_eq!(frames.bound_scope(ROOT, "top"), Some(ROOT));
    assert_eq!(frames.bound_scope(inner, "none"), None);
    assert_eq!(frames.count(outer, "top"), 1);
    assert!(!frames.is_ambiguous(inner));
    frames.blur(inner);
    assert!(frames.is_ambiguous(inner));
}

#[test]
fn the_names_of_a_frame_are_sorted_like_python_sorted() {
    let mut frames = Frames::new();
    for name in ["b", "a", "É", "Z", "a"] {
        frames.bind(ROOT, name.to_owned());
    }
    // `sorted` orders by code point; the bytes of UTF-8 order the same way.
    assert_eq!(frames.sorted_names(ROOT), ["Z", "a", "b", "É"]);
    assert_eq!(frames.count(ROOT, "a"), 2);
}

#[test]
fn a_pattern_nested_30000_deep_gives_its_target_without_recursion() {
    let depth = 30_000;
    let text = format!(
        "var {}x{} = y;\nvar z = 1;",
        "[".repeat(depth),
        "]".repeat(depth)
    );
    let mut parsers = Parsers::new();
    let syntax = parse(&mut parsers, "deep.ts", text.as_bytes()).syntax;
    assert_eq!(syntax.script_bindings, ["x", "z"]);
}

#[test]
fn a_hole_or_a_computed_target_blurs_the_frame() {
    let mut parsers = Parsers::new();
    // `a.b` is no plain name, so the frame of the file blocks every name (`source_unique` false).
    let text = "import { v } from './m';\nfor (a.b of xs) {}\nvar [c.d] = e;\n";
    let syntax = parse(&mut parsers, "blur.ts", text.as_bytes()).syntax;
    assert_eq!(syntax.import_bindings.len(), 1);
    assert!(!syntax.import_bindings[0].source_unique);
}

#[test]
fn a_class_with_5000_methods_and_a_file_with_5000_functions_give_every_definition() {
    // A walk that asks the parent of each member would be quadratic here; Python is.
    let methods: String = (0..5000)
        .map(|n| format!("  m{n}(a: number): void {{}}\n"))
        .collect();
    let functions: String = (0..5000)
        .map(|n| format!("export function f{n}() {{}}\n"))
        .collect();
    let text = format!("export class Big {{\n{methods}}}\n{functions}");
    let mut parsers = Parsers::new();
    let syntax = parse(&mut parsers, "wide.ts", text.as_bytes()).syntax;
    assert_eq!(syntax.definitions.len(), 1 + 5000 + 5000);
    assert_eq!(
        syntax.parent_name(&syntax.definitions[1]).as_deref(),
        Some("Big")
    );
    assert_eq!(syntax.module_exports.len(), 5001);
}

#[test]
fn a_qualified_name_is_the_chain_of_the_parent_names() {
    let text = "class A { m() { function inner() { const k = 1; } } }";
    let mut parsers = Parsers::new();
    let syntax = parse(&mut parsers, "chain.ts", text.as_bytes()).syntax;
    let names: Vec<(String, Option<String>)> = syntax
        .definitions
        .iter()
        .map(|item| (item.name.clone(), syntax.parent_name(item)))
        .collect();
    assert_eq!(
        names,
        [
            ("A".to_owned(), None),
            ("m".to_owned(), Some("A".to_owned())),
            ("inner".to_owned(), Some("A.m".to_owned())),
            ("k".to_owned(), Some("A.m.inner".to_owned())),
        ]
    );
}

#[test]
fn the_memo_gives_the_answer_of_the_plain_climb() {
    let mut frames = Frames::new();
    let mut chain = vec![ROOT];
    for _ in 0..50 {
        chain.push(frames.push(*chain.last().unwrap_or(&ROOT)));
    }
    frames.bind(chain[0], "a".to_owned());
    frames.bind(chain[20], "a".to_owned());
    frames.bind(chain[35], "b".to_owned());
    let mut memo = std::collections::HashMap::new();
    // Ask from the middle first and from the ends later: a memo that kept a wrong frame shows.
    for from in [
        chain[25], chain[50], chain[10], chain[0], chain[36], chain[19], chain[50],
    ] {
        for name in ["a", "b", "c"] {
            assert_eq!(
                frames.bound_scope_memo(&mut memo, from, name),
                frames.bound_scope(from, name),
                "{from} {name}"
            );
        }
    }
}
