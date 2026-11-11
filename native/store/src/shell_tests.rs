// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::{BTreeSet, HashMap};

use serde_json::{json, Map, Value};

use super::{frame, Entry, Shell, Top};
use crate::canonical::{CLASSIFIED_SECTIONS, RECORD_FIELDS};

/// The compact form of `ir/codec_store.py:_shell_frame`: each shell record of a section as a row.
pub(crate) fn as_rows(mut model: Map<String, Value>) -> Value {
    let mut texts: Vec<String> = Vec::new();
    let mut index: HashMap<String, usize> = HashMap::new();
    let mut fields = HashMap::new();
    for name in CLASSIFIED_SECTIONS {
        let Some(Value::Array(items)) = model.get(name).cloned() else {
            continue;
        };
        let keys: Vec<String> = items
            .iter()
            .filter_map(|item| item.get("data")?.as_object())
            .flat_map(|data| data.keys().cloned())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let rows = items
            .into_iter()
            .map(|item| match item {
                Value::Object(record) => {
                    let mut row: Vec<Value> = RECORD_FIELDS[..RECORD_FIELDS.len() - 1]
                        .iter()
                        .map(|key| cell(&record[*key], &mut texts, &mut index))
                        .collect();
                    for key in &keys {
                        row.push(match record["data"].get(key) {
                            Some(value) => cell(value, &mut texts, &mut index),
                            None => json!({"m": true}),
                        });
                    }
                    Value::Array(row)
                }
                stored => stored,
            })
            .collect();
        model.insert(name.to_owned(), Value::Array(rows));
        fields.insert(name.to_owned(), keys);
    }
    let fields: std::collections::BTreeMap<_, _> = fields.into_iter().collect();
    json!({"texts": texts, "fields": fields, "model": model})
}

fn cell(value: &Value, texts: &mut Vec<String>, index: &mut HashMap<String, usize>) -> Value {
    match value {
        Value::String(text) => {
            let next = texts.len();
            let at = *index.entry(text.clone()).or_insert(next);
            if at == next {
                texts.push(text.clone());
            }
            json!(at)
        }
        Value::Number(_) => json!({ "n": value }),
        Value::Bool(_) => json!({ "b": value }),
        Value::Array(items) => {
            Value::Array(items.iter().map(|item| cell(item, texts, index)).collect())
        }
        Value::Object(map) => {
            let inner: Map<String, Value> = map
                .iter()
                .map(|(key, item)| (key.clone(), cell(item, texts, index)))
                .collect();
            json!({ "o": inner })
        }
        Value::Null => Value::Null,
    }
}

fn frame_of(value: Value) -> Result<(Shell, HashMap<String, Top>), String> {
    frame(
        serde_json::to_vec(&value).unwrap_or_default().as_slice(),
        &CLASSIFIED_SECTIONS,
    )
}

/// The shell and the model of a frame written as JSON.
pub(crate) fn framed(value: Value) -> (Shell, HashMap<String, Top>) {
    frame_of(value).unwrap_or_default()
}

/// The record of one row written as JSON, in a frame with the one text "a text".
fn row_record(row: Value, head: &[&str], fields: &[String]) -> Result<Map<String, Value>, String> {
    let (shell, mut model) =
        frame_of(json!({"texts": ["a text"], "fields": {}, "model": {"metrics": [row]}}))?;
    let Some(Top::Entries(entries)) = model.remove("metrics") else {
        return Err("no row".to_owned());
    };
    let Some(Entry::Row(start, end)) = entries.first() else {
        return Err("no row".to_owned());
    };
    shell.record(*start, *end, head, fields)
}

#[test]
fn a_row_with_an_unknown_cell_or_length_is_an_error() {
    let head = ["id"];
    let cases = [
        (json!([5]), "names no text"),
        (json!([{"x": 1}]), "unknown tag"),
        (json!([{"n": "1"}]), "unknown tag"),
        (json!(["plain"]), "expected a shell cell"),
        (json!([0, 0]), "does not match its fields"),
    ];
    for (row, message) in cases {
        let error = row_record(row, &head, &[]).err().unwrap_or_default();
        assert!(error.contains(message), "{message}: {error}");
    }
}

#[test]
fn an_absent_data_field_stays_absent() -> Result<(), String> {
    let fields = ["note".to_owned(), "gone".to_owned()];
    let record = row_record(json!([0, 0, {"m": true}]), &["id"], &fields)?;
    assert_eq!(
        Value::Object(record),
        json!({"id": "a text", "data": {"note": "a text"}})
    );
    Ok(())
}

#[test]
fn the_frame_has_three_keys() {
    let error = frame_of(json!({"texts": [], "fields": {}, "model": {}, "more": 1}))
        .err()
        .unwrap_or_default();
    assert!(error.contains("unknown field `more`"), "{error}");
    assert!(frame_of(json!({"texts": [], "fields": {}, "model": {}})).is_ok());
    let unknown = frame_of(json!({"texts": [], "fields": {"nowhere": []}, "model": {}}));
    assert!(unknown
        .err()
        .unwrap_or_default()
        .contains("no record section nowhere"));
    let twice = frame_of(json!({"texts": [], "fields": {"imports": ["a", "a"]}, "model": {}}));
    assert!(twice.err().unwrap_or_default().contains("repeat a name"));
}

/// The rows of the canonical fixture: `tests/test_collector_native_store_frame.py` checks that the Python encoder
/// gives the same rows, so this copy cannot drift from it. `ARCHKEEL_WRITE_FRAME=1` rewrites it.
#[test]
fn the_rows_of_the_fixture_are_the_committed_frame() -> Result<(), String> {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata");
    let parts: Value = serde_json::from_slice(
        &std::fs::read(root.join("canonical-parts.json")).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let Value::Object(model) = parts["model"].clone() else {
        return Err("no model".to_owned());
    };
    let written = as_rows(model);
    let path = root.join("canonical-frame.json");
    if std::env::var_os("ARCHKEEL_WRITE_FRAME").is_some() {
        let text = serde_json::to_string_pretty(&written).map_err(|e| e.to_string())?;
        std::fs::write(&path, text + "\n").map_err(|e| e.to_string())?;
    }
    let committed: Value =
        serde_json::from_slice(&std::fs::read(&path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    assert!(committed == written, "rewrite with ARCHKEEL_WRITE_FRAME=1");
    Ok(())
}

/// Python never sends a text twice; a repeat would split the count of one text in two.
#[test]
fn a_frame_whose_texts_repeat_is_an_error() {
    let twice = frame_of(json!({"texts": ["a", "b", "a"], "fields": {}, "model": {}}));
    assert!(twice.err().unwrap_or_default().contains("texts repeat"));
    assert!(frame_of(json!({"texts": ["a", "b"], "fields": {}, "model": {}})).is_ok());
}

/// Only the exact marker `{"m": true}` makes a data field absent, also for a field named `m`.
#[test]
fn only_the_exact_missing_marker_makes_a_field_absent() -> Result<(), String> {
    let fields = ["m".to_owned()];
    let record = row_record(json!([0, {"m": true}]), &["id"], &fields)?;
    assert_eq!(Value::Object(record), json!({"id": "a text", "data": {}}));
    for cell in [
        json!({"m": false}),
        json!({"m": true, "n": 1}),
        json!({"m": 1}),
    ] {
        let error = row_record(json!([0, cell]), &["id"], &fields)
            .err()
            .unwrap_or_default();
        assert!(error.contains("unknown tag"), "{cell}: {error}");
    }
    Ok(())
}
