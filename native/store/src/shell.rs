// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compact form of the shell's record sections in the `W` frame (AD-346).
//!
//! The frame is `{"texts": [...], "fields": {section: [...]}, "model": {...}}`. In `model`, a record
//! of the shell in a record section is a row: the record fields without `data`, then the values
//! of the section's shell data fields in the order of `fields`. In a row, a number is the index of
//! a text in `texts`. Any other number is `{"n": value}`, a bool `{"b": value}`, an object
//! `{"o": {...}}` and an absent data field `{"m": true}`. So the store holds each text once and
//! a row as small numbers. It builds the record object of one row only while it reads it
//! (`canonical.rs:with_record`), so the bytes are those of the plain record.

use std::collections::{HashMap, HashSet};

use serde_json::{Map, Value};

/// The texts and the data fields of the shell rows of one `W` frame.
pub(crate) struct Shell {
    pub(crate) texts: Vec<String>,
    pub(crate) fields: HashMap<String, Vec<String>>,
}

/// Split a `W` frame into the shell texts and fields, and the model. `sections` names the record
/// sections that a shell field list may name.
pub(crate) fn frame(
    value: Value,
    sections: &[&str],
) -> Result<(Shell, Map<String, Value>), String> {
    let Value::Object(mut frame) = value else {
        return Err("the observation frame must be an object".to_owned());
    };
    let (Some(texts), Some(fields), Some(Value::Object(model)), 3) = (
        frame.remove("texts"),
        frame.remove("fields"),
        frame.remove("model"),
        frame.len() + 3,
    ) else {
        return Err("the observation frame has the keys texts, fields and model only".to_owned());
    };
    let texts: Vec<String> = serde_json::from_value(texts).map_err(|error| error.to_string())?;
    let fields: HashMap<String, Vec<String>> =
        serde_json::from_value(fields).map_err(|error| error.to_string())?;
    for (section, names) in &fields {
        if !sections.contains(&section.as_str()) {
            return Err(format!("the shell names no record section {section}"));
        }
        if names.iter().collect::<HashSet<_>>().len() != names.len() {
            return Err(format!("the shell fields of {section} repeat a name"));
        }
    }
    Ok((Shell { texts, fields }, model))
}

impl Shell {
    #[cfg(test)]
    pub(crate) fn empty() -> Self {
        Shell {
            texts: Vec::new(),
            fields: HashMap::new(),
        }
    }

    /// The data fields of the shell rows of `section`.
    pub(crate) fn fields(&self, section: &str) -> &[String] {
        self.fields.get(section).map_or(&[], Vec::as_slice)
    }

    fn text(&self, cell: &serde_json::Number) -> Result<Value, String> {
        cell.as_u64()
            .and_then(|index| self.texts.get(usize::try_from(index).ok()?))
            .map(|text| Value::String(text.clone()))
            .ok_or_else(|| "a shell cell names no text".to_owned())
    }

    fn value(&self, cell: &Value) -> Result<Value, String> {
        match cell {
            Value::Null => Ok(Value::Null),
            Value::Number(index) => self.text(index),
            Value::Array(items) => items
                .iter()
                .map(|item| self.value(item))
                .collect::<Result<Vec<_>, _>>()
                .map(Value::Array),
            Value::Object(tag) if tag.len() == 1 => match tag.iter().next() {
                Some((key, value @ Value::Number(_))) if key == "n" => Ok(value.clone()),
                Some((key, value @ Value::Bool(_))) if key == "b" => Ok(value.clone()),
                Some((key, Value::Object(map))) if key == "o" => map
                    .iter()
                    .map(|(name, item)| Ok((name.clone(), self.value(item)?)))
                    .collect::<Result<Map<_, _>, String>>()
                    .map(Value::Object),
                _ => Err("a shell cell has an unknown tag".to_owned()),
            },
            _ => Err("a shell cell has an unknown form".to_owned()),
        }
    }

    /// The record object of one row; `head` names the record fields before `data`.
    pub(crate) fn record(
        &self,
        row: &[Value],
        head: &[&str],
        fields: &[String],
    ) -> Result<Map<String, Value>, String> {
        if row.len() != head.len() + fields.len() {
            return Err("a shell row does not match its fields".to_owned());
        }
        let mut item = Map::new();
        for (key, cell) in head.iter().zip(row) {
            item.insert((*key).to_owned(), self.value(cell)?);
        }
        let mut data = Map::new();
        for (key, cell) in fields.iter().zip(&row[head.len()..]) {
            if !missing(cell) {
                data.insert(key.clone(), self.value(cell)?);
            }
        }
        item.insert("data".to_owned(), Value::Object(data));
        Ok(item)
    }
}

fn missing(cell: &Value) -> bool {
    matches!(cell, Value::Object(tag) if tag.len() == 1 && tag.get("m") == Some(&Value::Bool(true)))
}

#[cfg(test)]
#[path = "shell_tests.rs"]
pub(crate) mod tests;
