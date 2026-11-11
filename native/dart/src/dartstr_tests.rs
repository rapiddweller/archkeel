// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected values come from `_decode_dart_string`, `_string_sequence`, `_directive_uri` and
// `_unclosed_block_comment` of `analyzer/dart/parse.py` (Python 3.11).

use super::*;

#[test]
fn a_string_literal_decodes_as_python_decodes_it() {
    let cases: [(&str, Option<&str>); 17] = [
        ("'a'", Some("a")),
        ("\"a\"", Some("a")),
        ("r'a$b'", None),
        ("'a$b'", None),
        ("'''x'''", Some("x")),
        ("'''", None),
        ("''", Some("")),
        (
            "'\\n\\t\\x41\\u0041\\u{1F600}\\$'",
            Some("\n\tAA\u{1F600}$"),
        ),
        ("'\\q'", None),
        ("'\\u{110000}'", None),
        ("'\\u{1234567}'", None),
        ("R\"x\"", Some("x")),
        ("'a", None),
        ("'''a'", None),
        ("'\\u{}'", None),
        ("'\\''", Some("'")),
        ("'\\b\\f\\v\\\\'", Some("\u{8}\u{c}\u{b}\\")),
    ];
    for (raw, expected) in cases {
        assert_eq!(decode_dart_string(raw).as_deref(), expected, "{raw}");
    }
}

#[test]
fn a_surrogate_escape_is_not_a_plain_string() {
    // Python gives a lone surrogate here. A Rust string cannot hold it (AD-369).
    assert_eq!(decode_dart_string("'\\uD800'"), None);
}

#[test]
fn adjacent_literals_and_comments_give_one_uri() {
    let sequence = |data: &[u8], start: usize| string_sequence(data, start, data.len());
    assert_eq!(sequence(b"import 'a' 'b';", 6).as_deref(), Some("ab"));
    assert_eq!(
        sequence(b"import /* c /* d */ */ 'x';", 6).as_deref(),
        Some("x")
    );
    assert_eq!(sequence(b"import // c\n 'y';", 6).as_deref(), Some("y"));
    assert_eq!(sequence(b"export \"a\" r'b$';", 6), None);
    assert_eq!(sequence(b"part 'a$b';", 4), None);
    // Python `_string_end` never skips an escape, so the literal ends at `\'`.
    assert_eq!(sequence(b"import 'a\\'b';", 6), None);
    assert_eq!(sequence(b"import x;", 6), None);
}

#[test]
fn a_directive_uri_needs_the_keyword_as_a_whole_word() {
    let uri = |data: &[u8]| directive_uri(data, 0, data.len());
    assert_eq!(uri(b"import 'a';").as_deref(), Some("a"));
    assert_eq!(uri(b"part 'b';").as_deref(), Some("b"));
    assert_eq!(uri(b"parts 'a';"), None);
    assert_eq!(uri(b"library 'a';"), None);
}

#[test]
fn an_unclosed_block_comment_is_found_outside_strings() {
    let cases: [(&[u8], Option<usize>); 9] = [
        (b"/* a", Some(0)),
        (b"/* /* */", Some(0)),
        (b"/* */", None),
        (b"'/*'", None),
        (b"r'\\' /*", Some(5)),
        (b"'\\' /*'", None),
        (b"// /*\nx", None),
        (b"'''a''' /* /* */ */ /*", Some(20)),
        (b"\"/*\" r\"x\" /*", Some(10)),
    ];
    for (content, expected) in cases {
        assert_eq!(
            unclosed_block_comment(content),
            expected,
            "{}",
            String::from_utf8_lossy(content)
        );
    }
}
