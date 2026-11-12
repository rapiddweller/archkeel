// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The output of the definitions equals `analyzer/dart/parse.py` byte for byte:
// `tests/test_collector_native_dart_syntax.py` compares whole files. These tests hold the work
// account of the walks (AD-376): a walk that stops counting its work changes the pinned value.

use super::*;

const PINNED_WORK: u64 = 168;

/// The definitions of `text` and the work of the walks, with the limit `limit`.
fn walked(text: &str, limit: u64) -> (Result<Vec<Definition>, Gap>, u64) {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(&archkeel_dart_grammar::LANGUAGE.into())
        .unwrap();
    let tree = parser.parse(text, None).unwrap();
    let source = Source::new(text.as_bytes());
    let work = Work::new(limit);
    let found = definitions(tree.root_node(), &source, &work);
    (found, work.spent())
}

fn work_of(text: &str) -> u64 {
    let (found, spent) = walked(text, u64::MAX);
    assert!(found.is_ok());
    spent
}

#[test]
fn each_walk_and_each_scan_of_the_definitions_counts_its_work() {
    // A class with members, a declaration with two items, parameters with a default and a
    // function type, an annotation before a member, and top-level variables and functions.
    let text = concat!(
        "class A { int a = 1, b = 2; @o void m(int x, [int y = 3]) {} A(); }\n",
        "var v = 1, w = 2;\n",
        "void f(void g(int z), {required int k}) {}\n",
    );
    assert_eq!(work_of(text), PINNED_WORK);
}

#[test]
fn the_work_limit_stops_the_definitions_with_a_gap() {
    let text = "class A { int a = 1; void m() {} }\nvar v = 1;\n";
    assert!(walked(text, 1 << 20).0.is_ok());
    assert_eq!(
        walked(text, 3).0.err(),
        Some(Gap("the work passes the limit of the definition walks"))
    );
}

#[test]
fn the_work_grows_linearly_with_the_members_of_a_class() {
    let class = |count: usize| {
        let fields: String = (0..count).map(|i| format!("int f{i} = {i};\n")).collect();
        let methods: String = (0..count).map(|i| format!("void m{i}() {{}}\n")).collect();
        format!("class A {{\n{fields}{methods}}}\n")
    };
    let (small, large) = (work_of(&class(1_000)), work_of(&class(4_000)));
    assert!(large < small * 5, "{small} {large}");
}

#[test]
fn the_work_grows_linearly_with_the_top_level_definitions() {
    let file = |count: usize| {
        let variables: String = (0..count).map(|i| format!("var v{i} = {i};\n")).collect();
        let functions: String = (0..count).map(|i| format!("void g{i}() {{}}\n")).collect();
        format!("{variables}{functions}")
    };
    let (small, large) = (work_of(&file(1_000)), work_of(&file(4_000)));
    assert!(large < small * 5, "{small} {large}");
}

#[test]
fn the_work_grows_linearly_with_the_parameters_of_a_function() {
    let file = |count: usize| {
        let parameters: Vec<String> = (0..count).map(|i| format!("int p{i} = {i}")).collect();
        format!("void f([{}]) {{}}\n", parameters.join(", "))
    };
    let (small, large) = (work_of(&file(1_000)), work_of(&file(4_000)));
    assert!(large < small * 5, "{small} {large}");
}

#[test]
fn the_head_that_each_item_of_a_declaration_copies_counts_as_work() {
    // The annotation of an item starts at the declaration, so 20 000 items copy the head 20 000
    // times: Python does the same, native stops at the limit.
    let items: Vec<String> = (0..20_000).map(|i| format!("v{i} = {i}")).collect();
    let text = format!("var {};\n", items.join(", "));
    let limit = crate::sites::work_limit(text.len());
    assert_eq!(
        walked(&text, limit).0.err(),
        Some(Gap("the work passes the limit of the definition walks"))
    );
}
