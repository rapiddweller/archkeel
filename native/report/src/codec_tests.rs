// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The canonical bytes of AD-361 point 9: each escape, and each kind of bytes that decode but are
//! not canonical.

use crate::corpus_tests::bytes;
use crate::payload::{DecodeError, Payload};

fn smallest() -> Vec<u8> {
    bytes("E-runtime")
}

fn with_language(language: &str) -> Vec<u8> {
    let mut payload = Payload::decode(&smallest()).unwrap();
    payload.run.language = language.to_owned();
    payload.encode().unwrap()
}

fn replaced(from: &str, to: &str) -> Vec<u8> {
    let text = String::from_utf8(smallest()).unwrap();
    assert!(text.contains(from), "{from}");
    text.replacen(from, to, 1).into_bytes()
}

#[test]
fn a_string_escapes_only_the_quote_the_backslash_and_the_control_characters() {
    let mut text = String::from("\"\\/\u{7f}\u{e9}\u{2028}\u{1f600}");
    text.extend((0u8..0x20).map(char::from));
    let encoded = String::from_utf8(with_language(&text)).unwrap();
    let mut wanted = String::from("\"language\":\"\\\"\\\\/\u{7f}\u{e9}\u{2028}\u{1f600}");
    for byte in 0u8..0x20 {
        wanted.push_str(&match byte {
            0x08 => "\\b".to_owned(),
            0x09 => "\\t".to_owned(),
            0x0a => "\\n".to_owned(),
            0x0c => "\\f".to_owned(),
            0x0d => "\\r".to_owned(),
            other => format!("\\u{other:04x}"),
        });
    }
    wanted.push('"');
    assert!(encoded.contains(&wanted), "{encoded}");
    assert!(encoded.contains("\\u001f"), "lowercase hex");
}

#[test]
fn the_bytes_end_with_one_newline_and_hold_no_whitespace_between_tokens() {
    let encoded = smallest();
    assert_eq!(encoded.last(), Some(&b'\n'));
    assert_ne!(encoded.get(encoded.len() - 2), Some(&b'\n'));
    assert!(!encoded.starts_with(b"{ "));
    assert!(!String::from_utf8(encoded).unwrap().contains("\": "));
}

#[test]
fn bytes_that_decode_but_are_not_canonical_are_refused() {
    let cases = [
        replaced("{\"schema_version\"", "{ \"schema_version\""),
        replaced("\"language\":\"python\"", "\"language\":\"pyth\\u006fn\""),
        replaced("\"dirty\":false,", "\"dirty\":false ,"),
        replaced("\"git_head\":\"", "\"git_head\" :\""),
        smallest().strip_suffix(b"\n").unwrap().to_vec(),
        [smallest(), b"\n".to_vec()].concat(),
    ];
    for case in cases {
        assert!(matches!(
            Payload::decode(&case),
            Err(DecodeError::NotCanonical)
        ));
    }
}

#[test]
fn a_missing_nullable_key_or_another_key_order_is_not_canonical() {
    let text = String::from_utf8(smallest()).unwrap();
    let start = text.find("\"git_head\":").unwrap();
    let end = start + text[start..].find(',').unwrap() + 1;
    let without = format!("{}{}", &text[..start], &text[end..]);
    assert!(matches!(
        Payload::decode(without.as_bytes()),
        Err(DecodeError::NotCanonical)
    ));
    let mut value: serde_json::Value = serde_json::from_str(&text).unwrap();
    let run = value["run"].as_object_mut().unwrap();
    let language = run.shift_remove("language").unwrap();
    run.insert("language".to_owned(), language);
    let mut moved = serde_json::to_vec(&value).unwrap();
    moved.push(b'\n');
    assert!(matches!(
        Payload::decode(&moved),
        Err(DecodeError::NotCanonical)
    ));
}

#[test]
fn an_unknown_repeated_or_negative_field_is_no_payload() {
    let cases = [
        replaced(
            "{\"schema_version\"",
            "{\"producer\":\"x\",\"schema_version\"",
        ),
        replaced("\"dirty\":false", "\"dirty\":false,\"dirty\":false"),
        replaced("\"files_read\":", "\"files_read\":-"),
        replaced("\"target\":true", "\"target\":1"),
        replaced("\"schema_version\":\"2.0.0\"", "\"schema_version\":2"),
    ];
    for case in cases {
        assert!(
            matches!(Payload::decode(&case), Err(DecodeError::Shape(_))),
            "{case:?}"
        );
    }
}
