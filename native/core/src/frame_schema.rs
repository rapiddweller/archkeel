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
    definitions
        .remove(name)
        .unwrap_or_else(|| panic!("the schema has no definition {name}"))
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
    let unsupported = definitions
        .get_mut("UnsupportedParts")
        .and_then(Value::as_object_mut)
        .expect("the definition of UnsupportedParts");
    if let Some(Value::Object(found)) = unsupported.get_mut("properties") {
        found.insert("rules".to_owned(), reasons.into());
    }
    if let Some(Value::Array(found)) = unsupported.get_mut("required") {
        found.push(Value::String("rules".to_owned()));
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
    close(&mut schema);
    schema
}

/// The text of the schema file: pretty JSON and a final newline.
pub(crate) fn text() -> serde_json::Result<String> {
    serde_json::to_string_pretty(&schema()).map(|text| text + "\n")
}

#[cfg(test)]
#[path = "frame_schema_tests.rs"]
mod tests;
