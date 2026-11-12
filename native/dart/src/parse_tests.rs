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

fn version_error(text: &[u8]) -> bool {
    parse(text)
        .concerns
        .iter()
        .any(|item| item.kind == ConcernKind::LanguageVersionError)
}

#[test]
fn the_supported_range_is_2_12_through_3_12() {
    // `version < (2, 12) or version > (3, 12)` in `_language_version`.
    assert!(!version_error(b"// @dart=3.12\n"));
    assert!(!version_error(b"// @dart=2.12\n"));
    assert!(version_error(b"// @dart=3.13\n"));
    assert!(version_error(b"// @dart=2.11\n"));
}

#[test]
fn a_version_number_over_4300_written_digits_is_out_of_range() {
    // Python `int` raises `ValueError` here, also when the digits are leading zeros.
    let mut minor = b"// @dart=3.".to_vec();
    minor.extend([b'0'; 5000]);
    minor.extend(b"1\n");
    assert!(version_error(&minor));
    let mut major = b"// @dart=".to_vec();
    major.extend([b'0'; 4400]);
    major.extend(b"3.0\n");
    assert!(version_error(&major));
    // 4 300 digits still convert in Python: `3.1`, in range.
    let mut limit = b"// @dart=3.".to_vec();
    limit.extend([b'0'; 4299]);
    limit.extend(b"1\n");
    let syntax = parse(&limit);
    assert_eq!(syntax.language_version.as_deref(), Some("3.1"));
    assert!(syntax.complete);
}

#[test]
fn a_code_point_that_unicode_14_does_not_assign_gives_an_encoding_concern() {
    let syntax = parse("var a = 1;\nvar s = 'x\u{10d40}';\n".as_bytes());
    let found: Vec<(&str, usize, usize)> = syntax
        .concerns
        .iter()
        .map(|c| {
            (
                c.message.as_str(),
                c.span.line,
                c.span.end_byte - c.span.start_byte,
            )
        })
        .collect();
    let message = "Dart source holds a code point that Unicode 14 does not assign.";
    assert_eq!(found, [(message, 2, 4)]);
    assert_eq!(syntax.first_error.unwrap().line, 2);
}

/// The deepest node below the root of `text`, counted from 0 as `Walk::depth` counts it.
fn max_depth(text: &str) -> usize {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(&archkeel_dart_grammar::LANGUAGE.into())
        .unwrap();
    let tree = parser.parse(text, None).unwrap();
    let mut nodes = walk(tree.root_node());
    let mut deepest = 0;
    while nodes.next().is_some() {
        deepest = deepest.max(nodes.depth);
    }
    deepest
}

#[test]
fn the_depth_limit_flags_depth_900_and_not_899() {
    let nested = |count: usize| format!("var x = {}1{};", "(".repeat(count), ")".repeat(count));
    let count = (850..950)
        .find(|count| max_depth(&nested(*count)) == MAX_DEPTH - 1)
        .unwrap();
    assert!(parse(nested(count).as_bytes()).complete);
    let deeper = nested(count + 1);
    assert_eq!(max_depth(&deeper), MAX_DEPTH);
    let syntax = parse(deeper.as_bytes());
    let deep = syntax
        .concerns
        .iter()
        .filter(|item| item.message.contains("nests deeper"))
        .count();
    assert_eq!(deep, 1);
}

#[test]
fn the_bracket_bound_is_ten_times_the_depth_limit() {
    // `nesting` cannot import `parse` (a module cycle), so the relation is held here.
    assert_eq!(crate::nesting::MAX_BRACKETS, MAX_DEPTH * 10);
}
