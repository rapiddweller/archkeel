// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected values come from Python 3.11: `str.splitlines`, `str.strip` and `bytes.strip`.

use super::*;

#[test]
fn splitlines_breaks_where_python_breaks() {
    assert_eq!(splitlines("a\nb\r\nc\rd"), ["a", "b", "c", "d"]);
    assert_eq!(splitlines("a\n\nb\n"), ["a", "", "b"]);
    assert_eq!(
        splitlines("a\u{0b}b\u{0c}c\u{1c}d\u{85}e\u{2028}f"),
        ["a", "b", "c", "d", "e", "f"]
    );
    assert_eq!(splitlines(""), Vec::<&str>::new());
    assert_eq!(splitlines("\r\n"), [""]);
}

#[test]
fn strip_removes_python_white_space() {
    assert_eq!(strip("\u{1f} a \u{a0}"), "a");
    assert_eq!(lstrip("\u{3000}a "), "a ");
    assert_eq!(rstrip(" a\u{2029}"), " a");
    // U+FEFF is not white space in Python.
    assert_eq!(strip("\u{feff}a"), "\u{feff}a");
}

#[test]
fn a_blank_file_holds_only_ascii_white_space() {
    assert!(is_blank(b" \t\n\r\x0b\x0c"));
    assert!(is_blank(b""));
    // `bytes.strip` keeps U+00A0 (two bytes in UTF-8) and the byte 0x1c.
    assert!(!is_blank("\u{a0}".as_bytes()));
    assert!(!is_blank(b"\x1c"));
}
