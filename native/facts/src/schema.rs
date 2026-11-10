// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The JSON schema of the protocol 9 wire, generated from the types (schemars).
//!
//! The schema is a bundle: each type is a definition under `$defs`. A reader refers to
//! `#/$defs/Section` for a section and to `#/$defs/Record_GapFact` for a coverage gap. The
//! committed file `schema/archkeel-facts-9.schema.json` must equal `schema()` (`schema_tests`).
//! A published schema never changes, so a type change that changes the schema needs a new protocol.

use schemars::generate::SchemaSettings;
use serde_json::{json, Value};

use crate::producer::Producer;
use crate::reason::ReasonCode;
use crate::record::Record;
use crate::sections::{GapFact, Section};
use crate::vocab::Kind;

/// The path of the committed schema, relative to the crate.
pub const PATH: &str = "schema/archkeel-facts-9.schema.json";

/// The schema bundle of protocol 9.
pub fn schema() -> Value {
    let mut generator = SchemaSettings::draft2020_12().into_generator();
    generator.subschema_for::<Section>();
    generator.subschema_for::<Record<GapFact>>();
    generator.subschema_for::<Kind>();
    generator.subschema_for::<ReasonCode>();
    generator.subschema_for::<Producer>();
    let definitions = generator.take_definitions(true);
    json!({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "archkeel-facts protocol 9",
        "description": "The source records of a collector reply. Generated from the Rust types.",
        "$defs": definitions,
    })
}

/// The text of the schema file: pretty JSON and a final newline.
pub fn text() -> serde_json::Result<String> {
    serde_json::to_string_pretty(&schema()).map(|text| text + "\n")
}

#[cfg(test)]
#[path = "schema_tests.rs"]
mod tests;
