// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn float_ties_use_cpython_even_digits() {
    assert_eq!(repr_float(2.0f64.powi(-25), true), "2.9802322387695312e-08");
    assert_eq!(
        repr_float(f64::from_bits(0x42e26687db6b9b04), true),
        "161852602146008.12"
    );
}

#[test]
fn a_character_of_a_newer_unicode_is_printable_only_from_its_version() {
    // U+0CF3 KANNADA SIGN COMBINING ANUSVARA ABOVE RIGHT: Unicode 15.0 (Python 3.12).
    assert!(!printable('\u{cf3}', crate::test_minor(11)));
    assert!(printable('\u{cf3}', crate::test_minor(12)));
    assert_eq!(repr_str("\u{cf3}", crate::test_minor(11)), "'\\u0cf3'");
    assert_eq!(repr_str("\u{cf3}", crate::test_minor(12)), "'\u{cf3}'");
    assert!(!printable('\u{1}', crate::test_minor(14)));
    assert!(!printable('\u{7f}', crate::test_minor(14)));
}

#[test]
fn the_quotes_avoid_backslashes_as_cpython_does() {
    assert_eq!(
        avoiding_backslashes("a'b", &ALL_QUOTES, crate::test_minor(11)),
        "\"a'b\""
    );
    assert_eq!(
        avoiding_backslashes("a'\"b", &ALL_QUOTES, crate::test_minor(11)),
        "\"\"\"a'\"b\"\"\""
    );
    assert_eq!(
        avoiding_backslashes("'\"", &ALL_QUOTES, crate::test_minor(11)),
        "''''\"'''"
    );
}

#[test]
fn an_int_converts_to_decimal_without_its_underscores() {
    assert_eq!(repr_int("0b1_0"), Some("2".to_owned()));
    assert_eq!(repr_int("0o17"), Some("15".to_owned()));
    assert_eq!(repr_int("0x0"), Some("0".to_owned()));
    assert_eq!(repr_int(&"9".repeat(4300)), Some("9".repeat(4300)));
    assert_eq!(repr_int(&"9".repeat(4301)), None);
}
