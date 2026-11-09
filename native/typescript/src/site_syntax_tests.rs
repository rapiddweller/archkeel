// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the sites of a file. The expected values are what `parse.parse()` gives.

use crate::parse::parse;
use crate::syntax::Parsers;

fn comparisons(source: &str) -> Vec<String> {
    let syntax = parse(&mut Parsers::new(), "a.ts", source.as_bytes()).syntax;
    syntax
        .sites
        .comparisons
        .iter()
        .map(|item| item.span.excerpt.clone())
        .collect()
}

fn ambiguous(source: &str) -> Vec<bool> {
    let syntax = parse(&mut Parsers::new(), "a.js", source.as_bytes()).syntax;
    syntax
        .sites
        .sites
        .iter()
        .map(|site| site.scope_ambiguous)
        .collect()
}

#[test]
fn a_string_is_found_through_the_wrappers_that_keep_its_value() {
    assert_eq!(comparisons("a === ('x');"), ["'x'"]);
    assert_eq!(comparisons("a == ('x' as const);"), ["'x'"]);
    assert_eq!(comparisons("a != 'x'!;"), ["'x'"]);
    assert_eq!(comparisons("'x' satisfies string === a;"), ["'x'"]);
    assert_eq!(comparisons("a === `plain\\n`;"), ["`plain\\n`"]);
}

#[test]
fn a_template_with_a_substitution_and_a_non_equality_are_no_comparison() {
    assert!(comparisons("a === `x${b}`;").is_empty());
    assert!(comparisons("a < 'x'; a + 'x'; a >= 'x';").is_empty());
    assert_eq!(comparisons("switch (a) { case 'x': case y: }"), ["'x'"]);
}

#[test]
fn an_object_literal_a_unmodeled_block_and_a_plain_function_make_a_scope_uncertain() {
    // A call inside an object literal, inside a loose block, inside an arrow function.
    assert_eq!(ambiguous("({ k: f() });"), [true, true]);
    assert_eq!(ambiguous("{ f(); }"), [true]);
    assert_eq!(ambiguous("const g = () => f();"), [true]);
    assert_eq!(ambiguous("f();"), [false]);
    // An immediately called wrapper that passes the global object keeps the scope certain.
    assert_eq!(
        ambiguous("(function (window) { f(); })(window);"),
        [false; 3]
    );
}
