// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the manifest reader. The text is a real `Cargo.toml` shape.

use super::*;

fn at<'a>(table: &'a Table, path: &[&str]) -> Option<&'a Value> {
    let (last, parents) = path.split_last()?;
    let mut table = table;
    for key in parents {
        table = table.get(*key)?.table()?;
    }
    table.get(*last)
}

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
fn a_number_a_boolean_and_a_multiline_string_are_other() {
    let table = parse("a = 1\nb = true\nc = \"\"\"x\ny\"\"\"\nd = [1, 2]\n").unwrap();
    assert_eq!(table["a"], Value::Other);
    assert_eq!(table["b"], Value::Other);
    assert_eq!(table["c"], Value::Other);
    assert_eq!(table["d"], Value::Array(vec![Value::Other, Value::Other]));
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
