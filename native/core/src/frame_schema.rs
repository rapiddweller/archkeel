// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The JSON schema of the frame `archkeel-core-frame-1`, generated from the types that write it.
//!
//! The frame is the one interface between the core and the shell. Its keys come from the
//! `Ruling` of the report and from `Parts` of the core (`engine_frame::write` joins them). This
//! module takes the object schema of each, joins the properties into one object and adds the two
//! keys that the join writes itself: `unsupported.rules` and `html`. Each object is closed. The
//! committed file `schema/archkeel-core-frame-1.schema.json` must equal `schema()`; the shell
//! reads that file and keeps no list of keys of its own.

use schemars::generate::SchemaSettings;
use serde_json::{json, Value};

use crate::dual_run::FrameParts as Parts;

/// The path of the committed schema, relative to the crate.
pub(crate) const PATH: &str = "../../schema/archkeel-core-frame-1.schema.json";

/// The object schema that `$defs` holds for a type.
fn definition(definitions: &mut serde_json::Map<String, Value>, name: &str) -> Value {
    definitions.remove(name).unwrap_or(Value::Null)
}

/// One branch of a flattened `oneOf` with the own properties and the own required names added.
fn merged_branch(
    mut branch: Value,
    own: &serde_json::Map<String, Value>,
    required: &[Value],
) -> Value {
    let Value::Object(object) = &mut branch else {
        return branch;
    };
    let mut properties = own.clone();
    if let Some(Value::Object(found)) = object.get("properties") {
        properties.extend(found.clone());
    }
    object.insert("properties".to_owned(), Value::Object(properties));
    let mut names = required.to_vec();
    if let Some(Value::Array(found)) = object.get("required") {
        names.extend(found.iter().cloned());
    }
    object.insert("required".to_owned(), Value::Array(names));
    branch
}

/// A flattened tagged enum gives a node with its own `properties` beside a `oneOf` of objects.
/// Each branch becomes the whole object (the own properties and the branch properties), so that
/// closing the branch does not refuse the fields of the envelope.
fn merge_flattened(value: &mut Value) {
    match value {
        Value::Object(map) => {
            map.values_mut().for_each(merge_flattened);
            let own = map.get("properties").and_then(Value::as_object).cloned();
            let branches = map.get("oneOf").and_then(Value::as_array).cloned();
            if let (Some(own), Some(branches)) = (own, branches) {
                let required = map
                    .get("required")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default();
                let merged = branches
                    .into_iter()
                    .map(|branch| merged_branch(branch, &own, &required))
                    .collect();
                map.remove("properties");
                map.remove("required");
                map.insert("oneOf".to_owned(), Value::Array(merged));
            }
        }
        Value::Array(items) => items.iter_mut().for_each(merge_flattened),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
}

/// Close each object schema: a key that no type writes is not in the frame.
fn close(value: &mut Value) {
    match value {
        Value::Object(map) => {
            if map.contains_key("properties") && !map.contains_key("additionalProperties") {
                map.insert("additionalProperties".to_owned(), Value::Bool(false));
            }
            map.values_mut().for_each(close);
        }
        Value::Array(items) => items.iter_mut().for_each(close),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
}

/// The schema of one frame.
pub(crate) fn schema() -> Value {
    let mut generator = SchemaSettings::draft2020_12()
        .for_serialize()
        .into_generator();
    generator.subschema_for::<archkeel_report::Ruling>();
    generator.subschema_for::<Parts>();
    let reasons = generator.subschema_for::<archkeel_report::RuleReasons>();
    let mut definitions = generator.take_definitions(true);
    let ruling = definition(&mut definitions, "Ruling");
    let parts = definition(&mut definitions, "Parts");
    let mut properties = serde_json::Map::new();
    let mut required: Vec<Value> = Vec::new();
    for part in [&ruling, &parts] {
        if let Some(Value::Object(found)) = part.get("properties") {
            properties.extend(found.clone());
        }
        if let Some(Value::Array(found)) = part.get("required") {
            required.extend(found.iter().cloned());
        }
    }
    // `unsupported` of the parts has no `rules`: the join adds the reasons of the ruling.
    if let Some(unsupported) = definitions
        .get_mut("UnsupportedParts")
        .and_then(Value::as_object_mut)
    {
        if let Some(Value::Object(found)) = unsupported.get_mut("properties") {
            found.insert("rules".to_owned(), reasons.into());
        }
        if let Some(Value::Array(found)) = unsupported.get_mut("required") {
            found.push(Value::String("rules".to_owned()));
        }
    }
    // The part that `engine_frame::write` renders (`html.rs`): a protocol word, the status and
    // the one document.
    properties.insert(
        "html".to_owned(),
        json!({
            "type": "object",
            "properties": {
                "protocol": {"const": "archkeel-core-html-1"},
                "status": {"type": "string"},
                "document": {"type": "string"},
            },
            "required": ["protocol", "status", "document"],
        }),
    );
    required.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
    required.dedup();
    let mut schema = json!({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "archkeel core frame, protocol archkeel-core-frame-1",
        "description": "The one frame that the core writes and the shell reads. Generated from the types that write it.",
        "type": "object",
        "properties": properties,
        "required": required,
        "$defs": definitions,
    });
    merge_flattened(&mut schema);
    close(&mut schema);
    schema
}

/// The path of the committed schema of the refusal, relative to the crate.
pub(crate) const REFUSAL_PATH: &str = "../../schema/archkeel-core-refusal-1.schema.json";

/// The schema of the refusal on stderr, generated from `refusal::Refusal`.
pub(crate) fn refusal_schema() -> Value {
    let mut generator = SchemaSettings::draft2020_12()
        .for_serialize()
        .into_generator();
    let root = generator.subschema_for::<crate::refusal::Refusal<'static>>();
    let mut definitions = generator.take_definitions(true);
    let name = root
        .get("$ref")
        .and_then(Value::as_str)
        .and_then(|reference| reference.rsplit('/').next())
        .unwrap_or("Refusal")
        .to_owned();
    let mut schema = definition(&mut definitions, &name);
    if let Value::Object(map) = &mut schema {
        map.insert(
            "$schema".to_owned(),
            json!("https://json-schema.org/draft/2020-12/schema"),
        );
        map.insert(
            "title".to_owned(),
            json!("archkeel core refusal, protocol archkeel-core-refusal-1"),
        );
        map.insert("$defs".to_owned(), Value::Object(definitions));
    }
    close(&mut schema);
    schema
}

/// The text of the refusal schema file.
pub(crate) fn refusal_text() -> serde_json::Result<String> {
    serde_json::to_string_pretty(&refusal_schema()).map(|text| text + "\n")
}

/// The text of the schema file: pretty JSON and a final newline.
pub(crate) fn text() -> serde_json::Result<String> {
    serde_json::to_string_pretty(&schema()).map(|text| text + "\n")
}

#[cfg(test)]
#[path = "frame_schema_tests.rs"]
mod tests;
