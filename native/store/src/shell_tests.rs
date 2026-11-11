// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::{BTreeSet, HashMap};

use serde_json::{json, Map, Value};

use super::{frame, Shell};
use crate::canonical::{CLASSIFIED_SECTIONS, RECORD_FIELDS};

/// The compact form of `ir/codec_store.py:_shell_frame`: each shell record of a section as a row.
pub(crate) fn as_rows(mut model: Map<String, Value>) -> (Shell, Map<String, Value>) {
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
    (Shell { texts, fields }, model)
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

fn frame_of(value: Value) -> Result<(Shell, Map<String, Value>), String> {
    frame(value, &CLASSIFIED_SECTIONS)
}

fn shell() -> Shell {
    Shell {
        texts: vec!["a text".to_owned()],
        fields: HashMap::new(),
    }
}

#[test]
fn a_row_with_an_unknown_cell_or_length_is_an_error() {
    let head = ["id"];
    let cases = [
        (json!([5]), "names no text"),
        (json!([{"x": 1}]), "unknown tag"),
        (json!([{"n": "1"}]), "unknown tag"),
        (json!(["plain"]), "unknown form"),
        (json!([0, 0]), "does not match its fields"),
    ];
    for (row, message) in cases {
        let Value::Array(row) = row else { continue };
        let error = shell().record(&row, &head, &[]).err().unwrap_or_default();
        assert!(error.contains(message), "{message}: {error}");
    }
}

#[test]
fn an_absent_data_field_stays_absent() -> Result<(), String> {
    let fields = ["note".to_owned(), "gone".to_owned()];
    let row = vec![json!(0), json!(0), json!({"m": true})];
    let record = shell().record(&row, &["id"], &fields)?;
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
    assert!(error.contains("texts, fields and model only"), "{error}");
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
    let (shell, rows) = as_rows(model);
    let fields: std::collections::BTreeMap<_, _> = shell.fields.into_iter().collect();
    let written = json!({"texts": shell.texts, "fields": fields, "model": rows});
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
