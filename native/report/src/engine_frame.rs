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

mod output;
pub(crate) use output::{EngineFrame, FrameError};

fn object(value: Result<Value, serde_json::Error>) -> Result<Map<String, Value>, FrameError> {
    match value.map_err(|error| FrameError::Encode(error.to_string()))? {
        Value::Object(map) => Ok(map),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) | Value::Array(_) => {
            Err(FrameError::NotAnObject)
        }
    }
}

/// The page of a frame that the core joined itself: a system frame (AD-618). The page reads the
/// frame and decides nothing.
pub fn page(frame: &Map<String, Value>) -> Result<Value, serde_json::Error> {
    html::render(frame)
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
    let part_of = parts.remove("part_of");
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
        // E4: the system of a part is an input of the page only; the frame does not carry it.
        let rendered = match part_of {
            Some(link) => {
                let mut input = frame.clone();
                input.insert("part_of".to_owned(), link);
                html::render(&input)
            }
            None => html::render(&frame),
        }
        .map_err(|error| FrameError::Encode(error.to_string()))?;
        frame.insert("html".to_owned(), rendered);
    }
    let bytes = serde_json::to_vec(&Value::Object(frame))
        .map_err(|error| FrameError::Encode(error.to_string()))?;
    Ok(output::frame(bytes))
}
