// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use ruff_python_ast::Stmt;

use super::*;

/// The text of the expression of the one statement `source`.
fn text(source: &str, minor: u32) -> Result<String, Failure> {
    let source = crate::source::newlines(source);
    let source = source.as_ref();
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

#[test]
fn a_surrogate_escape_in_an_fstring_part_or_spec_is_unseen() {
    for minor in 11..=14 {
        assert_eq!(text("f'\\ud800{a}'\n", minor), Err(Failure::Unseen));
        assert_eq!(text("f'{a:\\ud800}'\n", minor), Err(Failure::Unseen));
        assert_eq!(text("'a' f'\\udfff{a}'\n", minor), Err(Failure::Unseen));
    }
    assert_eq!(text("t'\\ud800{a}'\n", 14), Err(Failure::Unseen));
}

#[test]
fn a_cr_inside_a_string_is_a_newline_as_in_cpython() {
    same("'''a\r\nb'''\r\n", "'a\\nb'");
    same("b'''a\rb'''\r", "b'a\\nb'");
    same("r'''a\\\r\nb'''\r\n", "'a\\\\\\nb'");
    same("'''a\\\r\nb'''\r\n", "'ab'");
    same("f'''a\r\n{b}'''\r\n", "f'a\\n{b}'");
}

#[test]
fn a_spec_that_python_3_12_reads_in_its_own_way_is_a_gap_on_3_12_only() {
    assert_eq!(text("f'{a:\\N{BULLET}}'\n", 12), Err(Failure::Spec312));
    assert_eq!(text("rf'{a:\\n}'\n", 12), Err(Failure::Spec312));
    assert_eq!(
        text("f'{a:\\N{BULLET}}'\n", 13).as_deref(),
        Ok("f'{a:\u{2022}}'")
    );
    assert_eq!(text("rf'{a:\\n}'\n", 11).as_deref(), Ok("f'{a:\\\\n}'"));
    assert_eq!(text("rf'{a:\\n}'\n", 14).as_deref(), Ok("f'{a:\\\\n}'"));
}

#[test]
fn a_spec_deeper_than_cpython_keeps_is_a_gap_and_not_cut() {
    assert_eq!(text("f'{a:{b:{c:{d}}}}'\n", 13), Err(Failure::SpecDepth));
}

#[test]
fn a_version_outside_3_11_to_3_14_has_no_text() {
    let module = crate::parse::parse("x\n", 14).expect("the probe parses");
    let Some(Stmt::Expr(statement)) = module.body.first() else {
        return;
    };
    for minor in [10, 15] {
        assert_eq!(
            unparse(&statement.value, minor, "x\n"),
            Err(Failure::Version)
        );
        assert_eq!(
            annotation_text(Some(&statement.value), minor, "x\n"),
            Err(Failure::Version)
        );
    }
}

#[test]
fn xor_and_and_keep_their_parentheses() {
    same("a ^ b & c\n", "a ^ b & c");
    same("(a ^ b) & c\n", "(a ^ b) & c");
    same("a & (b ^ c)\n", "a & (b ^ c)");
}

#[test]
fn a_field_of_3_11_avoids_backslashes_and_3_12_escapes() {
    assert_eq!(text("f'{\"\u{200b}\"}'\n", 11), Err(Failure::Invalid));
    assert_eq!(
        text("f'{\"\u{200b}\"}'\n", 12).as_deref(),
        Ok("f\"{'\\u200b'}\"")
    );
    // From 3.12 on a field is written with `repr`: the newline stays an escape.
    for minor in 12..=14 {
        assert_eq!(
            text("f'{\"a\\nb\"}'\n", minor).as_deref(),
            Ok("f\"{'a\\nb'}\"")
        );
    }
}

#[test]
fn a_tstring_field_keeps_its_line_join_and_drops_its_comment() {
    assert_eq!(text("t'{a\\\n}'\n", 14).as_deref(), Ok("t'{a\\}'"));
    assert_eq!(text("t'{ a \\\n }'\n", 14).as_deref(), Ok("t'{ a \\}'"));
    assert_eq!(text("t'''{ a # c\n}'''\n", 14).as_deref(), Ok("t'{ a}'"));
}
