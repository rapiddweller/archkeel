// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::ParseFailure as Failure;
use super::*;

/// The parse on a thread with the stack of the binary (`main::STACK_BYTES`).
fn outcome(text: &str, minor: u32) -> Result<(), Failure> {
    let text = text.to_owned();
    std::thread::Builder::new()
        .stack_size(256 * 1024 * 1024)
        .spawn(move || parse(&text, crate::test_minor(minor)).map(|_| ()))
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
    assert!(failure(&format!("x = {}\n", vec!["a"; 4990].join("+")), 12)
        .2
        .contains("validation depth limit"));
}

#[test]
fn a_chain_past_the_parse_bound_is_refused_before_the_parse() {
    let deep = format!("x = {}a\n", "not ".repeat(40_000));
    let found = failure(&deep, 12);
    assert_eq!(found.0, ExceptionName::TooDeepError);
    assert_eq!(found.2, "expression nesting exceeds the parser stack");
}

const DIGITS: &str =
    "Exceeds the limit (4300 digits) for integer string conversion: value has 4301 \
                      digits; use sys.set_int_max_str_digits() to increase the limit - Consider \
                      hexadecimal for huge integer literals to avoid decimal conversion limits.";

#[test]
fn a_decimal_integer_over_4300_digits_fails_as_in_cpython() {
    let ok = format!("x = {}\n", "1".repeat(4300));
    assert!(outcome(&ok, 12).is_ok());
    let digits = "1".repeat(4301);
    let big = format!("x = {digits}\n");
    assert_eq!(
        failure(&big, 11),
        (ExceptionName::SyntaxError, 1, DIGITS.to_owned())
    );
    // An underscore is no digit; zeros only, hexadecimal, octal and binary have no limit.
    let underscores = format!("x = {}1\n", "1_".repeat(4300));
    assert_eq!(failure(&underscores, 14).2, DIGITS);
    for free in [
        format!("x = 0{}\n", "0".repeat(5000)),
        format!("x = 0x{}\n", "f".repeat(9000)),
        format!("x = 0o{}\n", "7".repeat(9000)),
        format!("x = 0b{}\n", "1".repeat(20_000)),
        format!("x = {}.0\n", "1".repeat(5000)),
        format!("x = {}j\n", "1".repeat(5000)),
    ] {
        assert!(outcome(&free, 12).is_ok(), "{}", &free[..12]);
    }
    for minor in [11, 12, 13, 14] {
        let in_match = format!("match x:\n    case {digits}:\n        pass\n");
        assert_eq!(failure(&in_match, minor).1, 2);
        assert!(outcome(&format!("x: {digits} = 1\n"), minor).is_err());
        assert!(outcome(&format!("x = f'{{{digits}}}'\n"), minor).is_err());
    }
}

/// `MAXSTACK` of the CPython parser: these shapes overflow it on 3.11 to 3.14.
#[test]
fn a_source_that_overflows_the_cpython_parser_stack_fails() {
    let shapes = [
        format!("x = {}0\n", "lambda: ".repeat(3000)),
        format!("{}\n", vec!["a"; 3000].join("**")),
        format!("{}0\n", "lambda: a if b else ".repeat(2000)),
        // Brackets alone: 200 levels of a comparison in a group.
        format!("x = {}a{}\n", "(a < ".repeat(200), ")".repeat(200)),
        // Blocks add to an expression: 99 nested functions and 5 274 `not`.
        format!(
            "{}{}x = {}a\n",
            (0..99)
                .map(|level| format!("{}def f():\n", " ".repeat(level)))
                .collect::<String>(),
            " ".repeat(99),
            "not ".repeat(5300)
        ),
        // The parameters of a lambda nest its body too.
        format!("x = {}0\n", "lambda a, b=1: ".repeat(3000)),
        format!("x = {}0{}\n", "lambda a=".repeat(800), ": 0".repeat(800)),
    ];
    for minor in [11, 14] {
        for shape in &shapes {
            let found = failure(shape, minor);
            assert_eq!(found.0, ExceptionName::TooDeepError, "{}", &shape[..40]);
        }
    }
}

#[test]
fn a_nesting_that_real_code_has_stays_under_the_stack_bound() {
    let calls = format!(
        "x = {}a{}\n",
        "f(g(a, [b, {c: (d,)}], k=".repeat(20),
        "))".repeat(20)
    );
    assert!(outcome(&calls, 12).is_ok());
    let blocks: String = (0..60)
        .map(|level| format!("{}if not a or b < c:\n", " ".repeat(level)))
        .collect();
    assert!(outcome(&format!("{blocks}{}pass\n", " ".repeat(60)), 12).is_ok());
}

#[test]
fn a_second_byte_order_mark_is_an_invalid_character() {
    let found = failure("\u{feff}x = 1\n", 12);
    let expected = "invalid non-printable character U+FEFF";
    assert_eq!(found, (ExceptionName::SyntaxError, 1, expected.to_owned()));
}

#[test]
fn an_identifier_has_the_unicode_version_of_its_python() {
    for joiner in ['\u{200c}', '\u{200d}'] {
        let text = format!("a{joiner}b = 1\n");
        for minor in [11, 12] {
            assert_eq!(failure(&text, minor).0, ExceptionName::SyntaxError);
        }
        for minor in [13, 14] {
            assert!(outcome(&text, minor).is_ok());
        }
    }
    // U+1C89 is a letter of Unicode 16 (Python 3.14), U+A7CB one of Unicode 16 too.
    assert!(outcome("\u{1c89} = 1\n", 13).is_err());
    assert!(outcome("\u{1c89} = 1\n", 14).is_ok());
}

#[test]
fn an_f_string_has_the_limits_of_its_python() {
    let nested = |levels: usize| format!("x = {}1{}\n", "f'{".repeat(levels), "}'".repeat(levels));
    for minor in [12, 13, 14] {
        assert!(outcome(&nested(100), minor).is_ok());
        // CPython accepts 149; the stack bound refuses it (a stricter difference of AD-334).
        assert_eq!(failure(&nested(149), minor).0, ExceptionName::TooDeepError);
        let found = failure(&nested(150), minor);
        assert_eq!(found.0, ExceptionName::SyntaxError);
        assert!(
            found.2.starts_with("too many nested f-strings"),
            "{}",
            found.2
        );
    }
    let fields = |inner: usize| format!("x = f'{{{}a{}}}'\n", "(".repeat(inner), ")".repeat(inner));
    assert!(outcome(&fields(100), 11).is_ok());
    // CPython 3.11 accepts 199; the stack bound refuses it (a stricter difference of AD-334).
    assert_eq!(failure(&fields(199), 11).0, ExceptionName::TooDeepError);
    for minor in [11, 12] {
        assert_eq!(failure(&fields(200), minor).0, ExceptionName::SyntaxError);
    }
    for refused in ["x = f'{a:{b:{c}}}'\n", "x = f'{*a}'\n"] {
        assert_eq!(
            failure(refused, 11).0,
            ExceptionName::SyntaxError,
            "{refused}"
        );
        assert!(outcome(refused, 12).is_ok(), "{refused}");
    }
    for allowed in ["x = f'{a:{b}}'\n", "x = f'{*a,}'\n", "x = f'{a, *b}'\n"] {
        assert!(outcome(allowed, 11).is_ok(), "{allowed}");
    }
}

#[test]
fn a_future_import_has_the_rules_of_its_python() {
    let braces = "\"doc\"\nfrom __future__ import braces\n";
    assert_eq!(
        failure(braces, 14),
        (ExceptionName::SyntaxError, 2, "not a chance".to_owned())
    );
    let unknown = "from __future__ import annotations, nope\n";
    let expected = "future feature nope is not defined";
    assert_eq!(
        failure(unknown, 14),
        (ExceptionName::SyntaxError, 1, expected.to_owned())
    );
    assert!(outcome("x = 1\nfrom __future__ import braces\n", 14).is_err());
    assert!(outcome("from .__future__ import braces\n", 14).is_ok());
    for minor in [11, 12, 13] {
        assert!(outcome(braces, minor).is_err());
        assert!(outcome(unknown, minor).is_err());
    }
    let barry = "if 0:\n    from __future__ import barry_as_FLUFL\nx = 1 != 2\n";
    assert!(outcome(barry, 11).is_err());
    for minor in [12, 13, 14] {
        assert_eq!(failure(barry, minor).1, 3);
    }
}
