// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use ruff_python_ast::Stmt;

use super::*;

/// The text of the expression of the one statement `source`.
fn text(source: &str, minor: u32) -> Result<String, Failure> {
    let module = crate::parse::parse(source, minor).expect("the probe parses");
    let Some(Stmt::Expr(statement)) = module.body.first() else {
        return Err(Failure::Invalid);
    };
    unparse(&statement.value, minor, source)
}

fn same(source: &str, expected: &str) {
    for minor in 11..=14 {
        assert_eq!(
            text(source, minor).as_deref(),
            Ok(expected),
            "{source} on 3.{minor}"
        );
    }
}

#[test]
fn the_precedence_writes_the_parentheses_of_cpython() {
    same("(a + b) * c\n", "(a + b) * c");
    same("a ** b ** c\n", "a ** b ** c");
    same("(a ** b) ** c\n", "(a ** b) ** c");
    same("a and b and (not c)\n", "a and b and (not c)");
    same("not a and b\n", "not a and b");
    same("(yield)\n", "(yield)");
    same("a, b\n", "(a, b)");
    same("x[a, b]\n", "x[a, b]");
    same("x[(a, b),]\n", "x[(a, b),]");
    same("f(x for x in y)\n", "f((x for x in y))");
    same("lambda: (yield)\n", "lambda: (yield)");
    same(
        "lambda a, /, b=1, *c, d, e=2, **f: 0\n",
        "lambda a, /, b=1, *c, d, e=2, **f: 0",
    );
    same("(x := 1)\n", "(x := 1)");
    same("1 .real\n", "1 .real");
    same("True.real\n", "True .real");
    same("{**a, 'b': 1}\n", "{**a, 'b': 1}");
    same("{*()}\n", "{*()}");
}

#[test]
fn the_literals_have_the_repr_of_cpython() {
    same("1e16\n", "1e+16");
    same("1e15\n", "1000000000000000.0");
    same("0.00001\n", "1e-05");
    same("0.0001\n", "0.0001");
    same("1e400\n", "1e309");
    same("2j\n", "2j");
    same("1e400j\n", "1e309j");
    same("0x_ff\n", "255");
    same("0xffffffffffffffffff\n", "4722366482869645213695");
    same("u'a' 'b'\n", "u'ab'");
    same("b'\\x00\"'\n", "b'\\x00\"'");
    same("'it\\'s'\n", "\"it's\"");
    same("...\n", "...");
}

#[test]
fn an_int_over_4300_digits_is_invalid() {
    let big = format!("0x{}\n", "f".repeat(4000));
    assert_eq!(text(&big, 12), Err(Failure::Invalid));
}

#[test]
fn a_surrogate_escape_is_unseen() {
    assert_eq!(text("'\\ud800'\n", 12), Err(Failure::Unseen));
}

#[test]
fn a_deep_expression_stops_at_the_bound() {
    let deep = format!("{}a\n", "-".repeat(MAX_DEPTH as usize + 1));
    assert_eq!(text(&deep, 12), Err(Failure::Deep));
    let fits = format!("{}a\n", "-".repeat(MAX_DEPTH as usize - 1));
    assert!(text(&fits, 12).is_ok());
}

#[test]
fn the_fstrings_follow_the_rules_of_each_version() {
    same("f'{x=}'\n", "f'x={x!r}'");
    same("f'a{x=:>4}'\n", "f'ax={x:>4}'");
    same("f'{x:}'\n", "f'{x:}'");
    same("'a' f'b{x}' 'c'\n", "f'ab{x}c'");
    same("f'{x:a{{b}}c}'\n", "f'{x:a{ {b}}c}'");
    assert_eq!(
        text("f'{xs:\\n}'\n", 11).as_deref(),
        Ok("f\"\"\"{xs:\n}\"\"\"")
    );
    assert_eq!(text("f'{xs:\\n}'\n", 12).as_deref(), Ok("f'{xs:\\n}'"));
    assert_eq!(text("t'{ x + 1 }'\n", 14).as_deref(), Ok("t'{ x + 1}'"));
    assert_eq!(text("t'{ x = !r}'\n", 14).as_deref(), Ok("t' x = { x!r}'"));
}
