// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the manifest reader. The text is a real `Cargo.toml` shape.

use super::*;
use crate::manifest::get as at;

#[test]
fn reads_tables_dotted_keys_and_inline_tables() {
    let table = parse(
        "# comment\n[package]\nname = \"a-b\" # trailing\nversion.workspace = true\n\
         [dependencies]\nserde = { version = \"1\", package = 'serde2', features = [\"x\",\n  \"y\"] }\n\
         [dependencies.tokio]\nworkspace = true\n",
    )
    .unwrap();
    assert_eq!(
        at(&table, &["package", "name"]),
        Some(&Value::Text("a-b".to_owned()))
    );
    assert!(at(&table, &["package", "version", "workspace"]).is_some());
    let serde = at(&table, &["dependencies", "serde"])
        .unwrap()
        .table()
        .unwrap();
    assert_eq!(serde["package"].text(), Some("serde2"));
    assert!(at(&table, &["dependencies", "tokio", "workspace"]).is_some());
}

#[test]
fn an_array_of_tables_adds_one_table_for_each_header() {
    let table = parse("[[bin]]\nname = \"x\"\n[[bin]]\nname = \"y\"\npath = \"y.rs\"\n").unwrap();
    let bins = match table.get("bin") {
        Some(Value::Array(bins)) => bins,
        _ => &Vec::new(),
    };
    assert_eq!(bins.len(), 2);
    let names: Vec<_> = bins
        .iter()
        .filter_map(|bin| bin.table()?["name"].text())
        .collect();
    assert_eq!(names, ["x", "y"]);
}

#[test]
fn unsigned_integers_and_booleans_retain_their_value() {
    let table = parse("a = 1\nb = true\nd = [1, 2]\n").unwrap();
    assert_eq!(table["a"], Value::Integer(1));
    assert_eq!(table["b"], Value::Boolean(true));
    assert_eq!(parse("b = false").unwrap()["b"], Value::Boolean(false));
    assert_eq!(
        table["d"],
        Value::Array(vec![Value::Integer(1), Value::Integer(2)])
    );
}

#[test]
fn a_broken_file_is_an_error_with_its_line() {
    for (text, message) in [
        ("[package\nname = 1\n", "expected `]` at line 1"),
        ("a = \"open\n", "a string does not end at line 1"),
        ("a = 1\na = 2\n", "the key `a` is set twice"),
        ("a = \"x\" y\n", "unexpected text after a value at line 1"),
    ] {
        assert_eq!(parse(text).unwrap_err(), message, "{text}");
    }
}

#[test]
fn a_deep_array_stops_the_reader_instead_of_the_process() {
    let text = format!("a = {}{}\n", "[".repeat(100_000), "]".repeat(100_000));
    assert_eq!(
        parse(&text).unwrap_err(),
        "values are nested too deep at line 1"
    );
}

fn name_of(text: &str) -> Result<String, String> {
    let table = parse(text)?;
    Ok(at(&table, &["k"])
        .and_then(Value::text)
        .unwrap_or("")
        .to_owned())
}

#[test]
fn a_basic_string_decodes_each_escape_of_toml() {
    let read = |text: &str| name_of(&format!("k = \"{text}\"\n"));
    assert_eq!(read(r"base-crate").unwrap(), "base-crate");
    assert_eq!(read(r"\U0001F600é").unwrap(), "\u{1F600}\u{e9}");
    assert_eq!(read(r"a\n\r\b\f").unwrap(), "a\n\r\u{8}\u{c}");
    assert_eq!(read(r#"a\tb\\\""#).unwrap(), "a\tb\\\"");
}

#[test]
fn an_escape_that_toml_does_not_define_is_an_error() {
    for text in [r"\q", r"\u12", r"\u12G4", r"\ud800", r"\U00110000", r"\e"] {
        assert!(name_of(&format!("k = \"{text}\"\n")).is_err(), "{text}");
    }
}

#[test]
fn a_key_decodes_its_escapes() {
    let table = parse("[dependencies]\n\"base\\u002dcrate\" = \"1\"\n").unwrap();
    assert!(at(&table, &["dependencies", "base-crate"]).is_some());
}

#[test]
fn a_multi_line_string_keeps_its_text() {
    let basic = name_of("k = \"\"\"base-crate\"\"\"\n").unwrap();
    assert_eq!(basic, "base-crate");
    assert_eq!(name_of("k = '''base-crate'''\n").unwrap(), "base-crate");
    assert_eq!(name_of("k = \"\"\"\nab\ncd\"\"\"\n").unwrap(), "ab\ncd");
    assert_eq!(name_of("k = \"\"\"\r\nab\"\"\"\n").unwrap(), "ab");
    assert_eq!(name_of("k = '''\n\\u0041'''\n").unwrap(), "\\u0041");
    assert_eq!(name_of("k = \"\"\"\\u0041\\\n    b\"\"\"\n").unwrap(), "Ab");
    assert_eq!(name_of("k = \"\"\"a\"\"\"\"\n").unwrap(), "a\"");
    assert_eq!(name_of("k = '''a'''''\n").unwrap(), "a''");
}

#[test]
fn a_multi_line_string_that_does_not_end_is_an_error() {
    assert!(name_of("k = \"\"\"abc\n").is_err());
    assert!(name_of("k = \"\"\"a\"\"\"\"\"\"\n").is_err());
}
