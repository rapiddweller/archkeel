// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `EngineFrame`: the bytes of one engine frame of the core (AD-388, review N1 of #1090).
//!
//! Only `Ruling::frame` makes one, through `write`. It writes the keys of the ruling (`status`, `rules`,
//! `explained`, `violations`, `beyond`, `scope` and `unsupported.rules`) and adds the parts of the
//! core (the engine, the sections, the other unsupported parts, the self test). A part with a key
//! of the ruling is refused, so a core cannot write a second status next to the ruling's.

use serde::Serialize;
use serde_json::{Map, Value};

#[path = "html.rs"]
mod html;

/// The canonical bytes of one engine frame. The field is private: only `Ruling::frame` makes one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EngineFrame {
    bytes: Vec<u8>,
}

impl EngineFrame {
    /// The bytes, to be written one time.
    pub fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

/// Why the parts of the core give no frame.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FrameError {
    /// The parts are not a JSON object.
    NotAnObject,
    /// A part has a key that only the ruling writes.
    RulingKey(String),
    /// The bytes cannot be written.
    Encode(String),
}

impl std::fmt::Display for FrameError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FrameError::NotAnObject => formatter.write_str("the parts of the frame are no object"),
            FrameError::RulingKey(key) => {
                write!(
                    formatter,
                    "the part {key} is a key that only the ruling writes"
                )
            }
            FrameError::Encode(error) => formatter.write_str(error),
        }
    }
}

fn object(value: Result<Value, serde_json::Error>) -> Result<Map<String, Value>, FrameError> {
    match value.map_err(|error| FrameError::Encode(error.to_string()))? {
        Value::Object(map) => Ok(map),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) | Value::Array(_) => {
            Err(FrameError::NotAnObject)
        }
    }
}

/// The frame of a ruling (`Ruling::frame`): the keys of the ruling, its `unsupported.rules`
/// and the parts of the core. A part that holds a key of the ruling is refused.
pub(crate) fn write<P: Serialize>(
    ruling: Result<Value, serde_json::Error>,
    reasons: Result<Value, serde_json::Error>,
    parts: &P,
    html: bool,
) -> Result<EngineFrame, FrameError> {
    let ruling = object(ruling)?;
    let mut parts = object(serde_json::to_value(parts))?;
    if parts.contains_key("html") {
        return Err(FrameError::RulingKey("html".to_owned()));
    }
    if let Some(key) = parts.keys().find(|key| ruling.contains_key(*key)) {
        return Err(FrameError::RulingKey(key.clone()));
    }
    let unsupported = match parts.remove("unsupported") {
        Some(value) => object(Ok(value))?,
        None => Map::new(),
    };
    if unsupported.contains_key("rules") {
        return Err(FrameError::RulingKey("unsupported.rules".to_owned()));
    }
    let reasons = reasons.map_err(|error| FrameError::Encode(error.to_string()))?;
    let mut merged = Map::new();
    merged.insert("rules".to_owned(), reasons);
    merged.extend(unsupported);
    let mut frame = Map::new();
    if let Some(engine) = parts.remove("engine") {
        frame.insert("engine".to_owned(), engine);
    }
    frame.extend(ruling);
    frame.extend(parts);
    frame.insert("unsupported".to_owned(), Value::Object(merged));
    if html {
        let rendered =
            html::render(&frame).map_err(|error| FrameError::Encode(error.to_string()))?;
        frame.insert("html".to_owned(), rendered);
    }
    let bytes = serde_json::to_vec(&Value::Object(frame))
        .map_err(|error| FrameError::Encode(error.to_string()))?;
    Ok(EngineFrame { bytes })
}
