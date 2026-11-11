// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

fn problem(text: &str, minor: u32) -> Option<(ExceptionName, usize, String)> {
    let lines = Lines::new(text);
    scan(text, &lines, minor)
        .problem
        .map(|problem| (problem.exception, problem.line, problem.message))
}

fn depth(text: &str) -> usize {
    scan(text, &Lines::new(text), 12).stack
}

#[test]
fn the_201st_open_bracket_is_the_cpython_limit() {
    let ok = format!("x = {}1{}\n", "(".repeat(200), ")".repeat(200));
    assert_eq!(problem(&ok, 12), None);
    let deep = format!("x = 1\ny = {}{}\n", "[".repeat(201), "]".repeat(201));
    let found = problem(&deep, 12).unwrap();
    assert_eq!(found.0, ExceptionName::SyntaxError);
    assert_eq!(
        (found.1, found.2.as_str()),
        (2, "too many nested parentheses")
    );
}

#[test]
fn the_braces_of_an_f_string_are_brackets_from_python_3_12() {
    let text = format!("x = f\"{}\"\n", "{a}".repeat(3));
    assert_eq!(problem(&text, 11), None);
    let nested = format!("x = {}f'{{a}}'{}\n", "(".repeat(200), ")".repeat(200));
    assert_eq!(problem(&nested, 11), None);
    assert!(problem(&nested, 12).is_some());
}

#[test]
fn the_indentation_rules_of_the_tokenizer_give_their_cpython_errors() {
    let tabs = "if 1:\n\tif 1:\n        pass\n";
    let tab_error = problem(tabs, 12).unwrap();
    assert_eq!((tab_error.0, tab_error.1), (ExceptionName::TabError, 3));
    let unindent = problem("def f():\n    x\n  y\n", 12).unwrap();
    assert_eq!(unindent.0, ExceptionName::IndentationError);
    assert_eq!(
        unindent.2,
        "unindent does not match any outer indentation level"
    );
    let levels: String = (0..101)
        .map(|level| format!("{}if 1:\n", " ".repeat(level)))
        .collect();
    let deep = problem(&levels, 12).unwrap();
    assert_eq!(
        (deep.1, deep.2.as_str()),
        (101, "too many levels of indentation")
    );
    // A comment line and a line inside brackets are not logical lines.
    assert_eq!(
        problem("if 1:\n    x = (1,\n\t2)\n\t# note\n    y\n", 12),
        None
    );
}

#[test]
fn a_closing_bracket_must_match_the_innermost_open_one() {
    let same = problem("x = [1, 2)\n", 12).unwrap();
    assert_eq!(
        same.2,
        "closing parenthesis ')' does not match opening parenthesis '['"
    );
    let other = problem("x = (1,\n  2]\n", 12).unwrap();
    assert_eq!(
        (other.1, other.2.as_str()),
        (
            2,
            "closing parenthesis ']' does not match opening parenthesis '(' on line 1"
        )
    );
    assert_eq!(problem("x = 1)\n", 12).unwrap().2, "unmatched ')'");
    let lines = Lines::new("f(a,\n  [b,\n");
    assert_eq!(scan("f(a,\n  [b,\n", &lines, 12).unclosed, Some(('[', 2)));
}

#[test]
fn a_chain_that_makes_the_parser_recurse_counts_once_for_each_link() {
    let not = format!("x = {}a\n", "not ".repeat(3000));
    assert!(depth(&not) >= 3000);
    let lambda = format!("f = {}0\n", "lambda: ".repeat(500));
    assert!(depth(&lambda) >= 500);
    let power = format!("x = a{}\n", " ** a".repeat(700));
    assert!(depth(&power) >= 700);
    let conditional = format!("x = a{}\n", " if c else a".repeat(400));
    assert!(depth(&conditional) >= 400);
}

#[test]
fn a_flat_list_or_a_left_chain_stays_shallow() {
    let negative: Vec<String> = (0..20_000).map(|number| format!("-{number}")).collect();
    assert!(depth(&format!("x = [{}]\n", negative.join(", "))) < 200);
    let plus = vec!["a"; 20_000].join(" + -");
    assert!(depth(&format!("x = {plus}\n")) < 200);
    assert!(depth("x = a is not b\nif not a: pass\n") < 200);
}

#[test]
fn a_deeper_line_with_fewer_columns_of_tab_size_1_is_a_tab_error() {
    // Line 3 is deeper with tab size 8 (8 > 7) and not deeper with tab size 1 (1 <= 7).
    let found = problem("if 1:\n       if 1:\n\tpass\n", 12).unwrap();
    assert_eq!((found.0, found.1), (ExceptionName::TabError, 3));
}
