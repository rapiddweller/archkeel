// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The JSON tree that the grammar reads, with the key order of the text.
//!
//! The grammar must tell an absent key from a key with `null`, and an integer from a float, as
//! Python `json.loads` does. The tree keeps each key of an object, so a repeated key is found and
//! refused before the grammar runs.

use std::fmt;

use serde::de::{Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};

use crate::error::{invalid, ErrorKind, ParseError, Parsed};

/// One JSON value. A number without a fraction and an exponent is an integer, as in Python.
#[derive(Debug)]
pub(crate) enum Json {
    Null,
    Bool(bool),
    Int(i128),
    Float,
    Text(String),
    Array(Vec<Json>),
    Object(Object),
}

/// The keys and values of one JSON object, in the order of the text.
#[derive(Debug)]
pub(crate) struct Object(Vec<(String, Json)>);

/// The value of `key`, or `None` when the key is absent.
pub(crate) fn field<'a>(object: &'a Object, key: &str) -> Option<&'a Json> {
    object
        .0
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}

/// Whether the object holds `key`, also with the value `null`.
pub(crate) fn has(object: &Object, key: &str) -> bool {
    field(object, key).is_some()
}

/// The keys of the object.
pub(crate) fn keys(object: &Object) -> impl Iterator<Item = &str> {
    object.0.iter().map(|(name, _)| name.as_str())
}

/// The entries of an object, without a repeated linear lookup by key.
pub(crate) fn entries(object: &Object) -> impl Iterator<Item = (&str, &Json)> {
    object.0.iter().map(|(name, value)| (name.as_str(), value))
}

/// Read contract bytes. Invalid UTF-8, invalid JSON and a repeated key are errors.
pub(crate) fn read(bytes: &[u8]) -> Parsed<Json> {
    let value: Json =
        serde_json::from_slice(bytes).map_err(|error| invalid(format!("invalid JSON: {error}")))?;
    match first_repeated_key(&value) {
        Some(key) => Err(ParseError {
            kind: ErrorKind::DuplicateKey,
            message: format!("invalid JSON: the key {key:?} repeats in one object"),
        }),
        None => Ok(value),
    }
}

fn first_repeated_key(value: &Json) -> Option<&str> {
    match value {
        Json::Array(items) => items.iter().find_map(first_repeated_key),
        Json::Object(Object(entries)) => {
            // A set, not a scan of the earlier keys: an object with a million keys is read in
            // O(n log n), not O(n^2) (AD-375). The first key that repeats is the same.
            let mut seen = std::collections::BTreeSet::new();
            let repeated = entries
                .iter()
                .find_map(|(name, _)| (!seen.insert(name.as_str())).then_some(name.as_str()));
            repeated.or_else(|| {
                entries
                    .iter()
                    .find_map(|(_, child)| first_repeated_key(child))
            })
        }
        _ => None,
    }
}

struct JsonVisitor;

impl<'de> Visitor<'de> for JsonVisitor {
    type Value = Json;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_unit<E>(self) -> Result<Json, E> {
        Ok(Json::Null)
    }

    fn visit_bool<E>(self, value: bool) -> Result<Json, E> {
        Ok(Json::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Json, E> {
        Ok(Json::Int(i128::from(value)))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Json, E> {
        Ok(Json::Int(i128::from(value)))
    }

    fn visit_f64<E>(self, _value: f64) -> Result<Json, E> {
        Ok(Json::Float)
    }

    fn visit_str<E>(self, value: &str) -> Result<Json, E> {
        Ok(Json::Text(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> Result<Json, E> {
        Ok(Json::Text(value))
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut access: A) -> Result<Json, A::Error> {
        let mut items = Vec::new();
        while let Some(item) = access.next_element()? {
            items.push(item);
        }
        Ok(Json::Array(items))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Json, A::Error> {
        let mut entries = Vec::new();
        while let Some(entry) = access.next_entry::<String, Json>()? {
            entries.push(entry);
        }
        Ok(Json::Object(Object(entries)))
    }
}

impl<'de> Deserialize<'de> for Json {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Json, D::Error> {
        deserializer.deserialize_any(JsonVisitor)
    }
}
