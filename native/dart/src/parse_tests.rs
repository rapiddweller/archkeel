// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected values come from `analyzer/dart/parse.parse` (Python 3.11).
// `tests/test_collector_native_dart_syntax.py` compares whole files byte for byte.

use super::*;

fn parse(text: &[u8]) -> Syntax {
    DartParser::new().unwrap().parse(text)
}

#[test]
fn the_language_version_is_the_first_override_line() {
    type Case = (&'static [u8], Option<&'static str>, Option<(usize, usize)>);
    let cases: [Case; 6] = [
        (
            b"// @dart=2.11\nvoid main() {}\n",
            Some("2.11"),
            Some((0, 13)),
        ),
        (
            b"\n\n  // @dart=3.13  \n\nclass A {}\n",
            Some("3.13"),
            Some((0, 20)),
        ),
        (
            b"  //  @dart=02.012.5\t\r\nclass A {}\n",
            Some("2.12"),
            None,
        ),
        (b"// @dart=3.x\n// @dart=3.0\n", Some("3.0"), None),
        (b"class A {} // @dart=2.0\n", None, None),
        (b"// @dart=9.0", Some("9.0"), Some((0, 12))),
    ];
    for (text, version, error) in cases {
        let syntax = parse(text);
        assert_eq!(syntax.language_version.as_deref(), version);
        let span = syntax
            .concerns
            .iter()
            .find(|item| item.kind == ConcernKind::LanguageVersionError)
            .map(|item| (item.span.start_byte, item.span.end_byte));
        assert_eq!(span, error, "{}", String::from_utf8_lossy(text));
    }
}

#[test]
fn the_first_error_is_the_first_error_concern_by_byte_and_kind() {
    let syntax = parse(b"mixin M on A {}\n// \xff\nclass A {}\nclass {\n");
    let found: Vec<(&str, usize, usize)> = syntax
        .concerns
        .iter()
        .map(|c| (c.kind.as_str(), c.span.line, c.span.start_byte))
        .collect();
    assert_eq!(
        found,
        [
            ("unsupported_declaration", 1, 0),
            ("invalid_encoding", 2, 19),
            ("syntax_error", 4, 32)
        ]
    );
    let first = syntax.first_error.unwrap();
    assert_eq!((first.line, first.start_byte), (2, 19));
    assert!(!syntax.complete);
}

#[test]
fn an_invalid_utf8_sequence_gives_the_python_error_range() {
    // Python `UnicodeDecodeError`: start 11, end 13 (the maximal invalid prefix).
    let syntax = parse(b"class A {}\n\xe2\x82(");
    let concern = syntax
        .concerns
        .iter()
        .find(|item| item.kind == ConcernKind::InvalidEncoding)
        .unwrap();
    assert_eq!((concern.span.start_byte, concern.span.end_byte), (11, 13));
    assert_eq!(concern.span.excerpt, "\u{fffd}");
    assert_eq!(syntax.first_error.unwrap().start_byte, 11);
}

#[test]
fn a_tree_deeper_than_the_limit_gives_one_syntax_concern() {
    let deep = format!("var x = {}1{};", "(".repeat(1000), ")".repeat(1000));
    let syntax = parse(deep.as_bytes());
    let deep_concerns = syntax
        .concerns
        .iter()
        .filter(|item| item.message.contains("nests deeper"))
        .count();
    assert_eq!(deep_concerns, 1);
    assert!(syntax.first_error.is_some());
    let shallow = format!("var x = {}1{};", "(".repeat(800), ")".repeat(800));
    assert!(parse(shallow.as_bytes()).complete);
}

#[test]
fn an_unclosed_comment_spans_to_the_end_of_the_source() {
    let syntax = parse(b"class A {}\n/* a /* b */\n");
    let concern = syntax
        .concerns
        .iter()
        .find(|item| item.message.contains("nested block comment"))
        .unwrap();
    assert_eq!((concern.span.start_byte, concern.span.end_byte), (11, 24));
}
