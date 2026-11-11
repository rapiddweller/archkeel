// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

/// The parse on a thread with the stack of the binary (`main::STACK_BYTES`).
fn outcome(text: &str, minor: u32) -> Result<(), Failure> {
    let text = text.to_owned();
    std::thread::Builder::new()
        .stack_size(256 * 1024 * 1024)
        .spawn(move || parse(&text, minor).map(|_| ()))
        .unwrap()
        .join()
        .unwrap()
}

fn failure(text: &str, minor: u32) -> (ExceptionName, usize, String) {
    let found = outcome(text, minor).unwrap_err();
    (found.exception, found.line, found.message)
}

#[test]
fn a_construct_of_a_newer_version_is_a_syntax_error() {
    assert_eq!(failure("type X = int\n", 11).0, ExceptionName::SyntaxError);
    assert!(outcome("type X = int\n", 12).is_ok());
    assert_eq!(failure("x = t'{a}'\n", 13).0, ExceptionName::SyntaxError);
    assert!(outcome("x = t'{a}'\n", 14).is_ok());
}

#[test]
fn the_null_byte_and_the_open_bracket_have_the_cpython_text() {
    let null = failure("x = 1\0\n", 11);
    let expected = "source code string cannot contain null bytes";
    assert_eq!(null, (ExceptionName::SyntaxError, 1, expected.to_owned()));
    let open = failure("x = 1\nf(a,\n  [b,\n", 12);
    assert_eq!(
        open,
        (
            ExceptionName::SyntaxError,
            3,
            "'[' was never closed".to_owned()
        )
    );
}

#[test]
fn an_indentation_error_of_the_parser_keeps_its_class() {
    assert_eq!(
        failure("if ok:\npass\n", 12).0,
        ExceptionName::IndentationError
    );
    assert_eq!(
        failure("x = 1\n    y = 2\n", 12).0,
        ExceptionName::IndentationError
    );
}

#[test]
fn a_tree_deeper_than_5000_levels_is_refused_with_its_depth() {
    let deep = format!("x = {}\n", vec!["a"; 5000].join("+"));
    let found = failure(&deep, 12);
    assert_eq!(found.0, ExceptionName::TooDeepError);
    assert_eq!(found.2, "expression nesting of 5003 levels exceeds 5000");
    assert!(outcome(&format!("x = {}\n", vec!["a"; 4990].join("+")), 12).is_ok());
}

#[test]
fn a_chain_past_the_parse_bound_is_refused_before_the_parse() {
    let deep = format!("x = {}a\n", "not ".repeat(40_000));
    let found = failure(&deep, 12);
    assert_eq!(found.0, ExceptionName::TooDeepError);
    assert_eq!(found.2, "expression nesting exceeds the parser stack");
}
