// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binding digest of a member inventory proof (`ir/member_inventory._inventory_binding`).
//!
//! It is the SHA-256 of the sorted JSON of `dataclasses.asdict` of the observation parts. The
//! shell names each stored record and evidence entry by its id; the store writes its `asdict`
//! form: a `RecordData` is `{"entries": [[key, value], ...]}` with sorted keys (AD-346). The
//! parts of the shell are JSON (stage 1 byte equality); a stored record is JSON only for the call.

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::pyjson::{write_value, Plain};
use crate::stored::Store;

/// `asdict` of a frozen JSON value: an object is a `RecordData`, a list is a tuple.
fn frozen(value: &Value) -> Value {
    match value {
        Value::Object(map) => record_data(map),
        Value::Array(items) => Value::Array(items.iter().map(frozen).collect()),
        other => other.clone(),
    }
}

fn record_data(map: &Map<String, Value>) -> Value {
    let mut keys: Vec<&String> = map.keys().collect();
    keys.sort();
    let entries: Vec<Value> = keys
        .into_iter()
        .map(|key| json!([key, frozen(&map[key.as_str()])]))
        .collect();
    json!({ "entries": entries })
}

/// `asdict` of a Python `Record` built from the wire form of a record.
fn record(map: &Map<String, Value>) -> Value {
    let mut result = map.clone();
    if let Some(Value::Object(data)) = map.get("data") {
        result.insert("data".to_owned(), record_data(data));
    }
    Value::Object(result)
}

fn records(value: Option<&mut Value>, store: &Store) -> Result<(), String> {
    let Some(Value::Array(items)) = value else {
        return Ok(());
    };
    for item in items {
        if let Value::String(id) = item {
            *item = record(&store.saved(id)?);
        }
    }
    Ok(())
}

/// The digest of the parts of the shell, with the stored entries in their `asdict` form.
pub(crate) fn digest(mut value: Value, store: &Store) -> Result<String, String> {
    if let Some(Value::Array(items)) = value.get_mut("evidence") {
        for item in items {
            if let Value::String(id) = item {
                *item = serde_json::to_value(store.evidence(id)?).map_err(|e| e.to_string())?;
            }
        }
    }
    records(value.pointer_mut("/coverage/failures"), store)?;
    if let Some(Value::Object(sections)) = value.get_mut("sections") {
        for section in sections.values_mut() {
            records(Some(section), store)?;
        }
    }
    let mut out = Vec::new();
    write_value(&value, &Plain, &mut out)?;
    let hash = Sha256::digest(&out);
    Ok(hash.iter().map(|byte| format!("{byte:02x}")).collect())
}
