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
    let error = frame(json!({"texts": [], "fields": {}, "model": {}, "more": 1}))
        .err()
        .unwrap_or_default();
    assert!(error.contains("texts, fields and model only"), "{error}");
    assert!(frame(json!({"texts": [], "fields": {}, "model": {}})).is_ok());
}
