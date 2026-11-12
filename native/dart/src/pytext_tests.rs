// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected values come from Python 3.11: `str.strip` and `bytes.strip`.

use super::*;

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

/// The Python `repr` of a table, the text whose SHA-256 the generated file names.
fn python_repr(table: &[(u32, u32)]) -> String {
    let items: Vec<String> = table
        .iter()
        .map(|(start, end)| format!("({start}, {end})"))
        .collect();
    format!("[{}]", items.join(", "))
}

#[test]
fn each_table_equals_the_dump_of_the_oracle() {
    // The SHA-256 values that `tools/dart_unicode_tables.py` wrote from Python 3.11.12
    // (Unicode 14.0.0); `tests/test_collector_native_dart_syntax.py` runs the script with
    // `--check`. A hand edit of a table fails here.
    use crate::unicode_tables::{
        ALNUM, ASSIGNED, BYTE_DIGIT, BYTE_SPACE, BYTE_WORD, LINE_BREAK, SPACE, WORD,
    };
    let source = include_str!("unicode_tables.rs");
    for text in [
        WORD, SPACE, LINE_BREAK, ASSIGNED, ALNUM, BYTE_WORD, BYTE_SPACE, BYTE_DIGIT,
    ] {
        let table = ranges(text);
        assert_eq!(table.len(), text.split_whitespace().count());
        let digest = archkeel_facts::identity::sha256_hex(python_repr(&table).as_bytes());
        assert!(source.contains(&format!("SHA-256 {digest},")), "{digest}");
    }
}

#[test]
fn python_word_characters_are_the_python_311_set() {
    for c in [
        '\u{345}',
        '\u{93e}',
        '\u{64b}',
        '\u{24b6}',
        '\u{10d40}',
        '-',
        ' ',
    ] {
        assert!(
            !is_word(c),
            "U+{:04X} is not \\w in Python 3.11",
            u32::from(c)
        );
    }
    for c in ['_', 'a', '\u{b2}', '\u{663}', '\u{2160}', '\u{e9}'] {
        assert!(is_word(c), "U+{:04X} is \\w in Python 3.11", u32::from(c));
    }
    assert!(has_word("x = 'late\u{93e}'", "late"));
    assert!(!has_word("x = '_late'", "late"));
    assert!(!has_word("x_static", "static"));
}

#[test]
fn python_alphanumeric_characters_are_the_python_311_set() {
    // `str.isalnum` differs from `\w` at `_` and at each combining mark, and from
    // `char::is_alphanumeric` at U+0345 and at the code points that Unicode 14 does not assign.
    for c in ['_', '$', '\u{345}', '\u{93e}', '\u{10d40}', '\u{fffd}', ' '] {
        assert!(
            !is_alnum(c),
            "U+{:04X} is not isalnum in 3.11",
            u32::from(c)
        );
    }
    for c in [
        'a', 'Z', '0', '\u{b2}', '\u{bd}', '\u{663}', '\u{2160}', '\u{e9}',
    ] {
        assert!(is_alnum(c), "U+{:04X} is isalnum in 3.11", u32::from(c));
    }
}

#[test]
fn a_code_point_that_unicode_14_does_not_assign_is_unassigned() {
    assert!(is_assigned('a') && is_assigned('\u{e000}') && is_assigned('\u{1fae0}'));
    for c in [
        '\u{10d40}',
        '\u{1fae8}',
        '\u{378}',
        '\u{fffe}',
        '\u{10ffff}',
    ] {
        assert!(!is_assigned(c), "U+{:04X}", u32::from(c));
    }
}

#[test]
fn the_byte_predicates_equal_python_over_each_byte() {
    use crate::unicode_tables::{BYTE_DIGIT, BYTE_SPACE, BYTE_WORD};
    let (word, space, digit) = (ranges(BYTE_WORD), ranges(BYTE_SPACE), ranges(BYTE_DIGIT));
    for value in 0..=255u8 {
        let c = char::from(value);
        assert_eq!(is_word_byte(value), in_table(&word, c), "{value}");
        assert_eq!(is_space_byte(value), in_table(&space, c), "{value}");
        assert_eq!(value.is_ascii_digit(), in_table(&digit, c), "{value}");
    }
}

#[test]
fn splitlines_breaks_where_python_311_breaks_for_each_code_point() {
    let line_break = ranges(crate::unicode_tables::LINE_BREAK);
    for code in (0..=0x10_FFFFu32).filter(|code| !(0xD800..0xE000).contains(code)) {
        let Some(c) = char::from_u32(code) else {
            continue;
        };
        let text = format!("a{c}b");
        let breaks = archkeel_pytext::splitlines(&text).len() == 2;
        assert_eq!(breaks, in_table(&line_break, c), "U+{code:04X}");
    }
}

#[test]
#[ignore = "a report for AD-369, not a gate: run with --ignored --nocapture"]
fn report_the_differences_of_the_rust_predicates() {
    let (word_table, space_table) = (
        ranges(crate::unicode_tables::WORD),
        ranges(crate::unicode_tables::SPACE),
    );
    let (mut word, mut space) = (0, 0);
    for c in (0..=0x10_FFFFu32).filter_map(char::from_u32) {
        word += usize::from((c.is_alphanumeric() || c == '_') != in_table(&word_table, c));
        let rust_space = c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c);
        space += usize::from(rust_space != in_table(&space_table, c));
    }
    println!("is_alphanumeric differs on {word}, is_whitespace on {space}");
}
