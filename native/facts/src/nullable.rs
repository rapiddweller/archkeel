// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Two value shapes of protocol 9 that `Option` cannot hold.

use std::borrow::Cow;

use schemars::{JsonSchema, Schema, SchemaGenerator};
use serde::{Deserialize, Deserializer, Serialize, Serializer};

/// A field that one producer omits and another writes as `null`. The wire keeps the difference:
/// `Absent` writes no key (with `skip_serializing_if = "Nullable::is_absent"`), `Null` writes `null`.
#[derive(Clone, Debug, Default, PartialEq)]
pub enum Nullable<T> {
    #[default]
    Absent,
    Null,
    Value(T),
}

impl<T> Nullable<T> {
    pub fn is_absent(&self) -> bool {
        matches!(self, Nullable::Absent)
    }

    pub fn value(&self) -> Option<&T> {
        match self {
            Nullable::Value(value) => Some(value),
            Nullable::Absent | Nullable::Null => None,
        }
    }
}

impl<T: Serialize> Serialize for Nullable<T> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match self {
            Nullable::Value(value) => value.serialize(serializer),
            Nullable::Absent | Nullable::Null => serializer.serialize_none(),
        }
    }
}

/// A key that is present gives `Null` or `Value`; `#[serde(default)]` gives `Absent`.
impl<'de, T: Deserialize<'de>> Deserialize<'de> for Nullable<T> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(match Option::<T>::deserialize(deserializer)? {
            Some(value) => Nullable::Value(value),
            None => Nullable::Null,
        })
    }
}

impl<T: JsonSchema> JsonSchema for Nullable<T> {
    fn inline_schema() -> bool {
        true
    }

    fn schema_name() -> Cow<'static, str> {
        Option::<T>::schema_name()
    }

    fn json_schema(generator: &mut SchemaGenerator) -> Schema {
        Option::<T>::json_schema(generator)
    }
}

/// A written constant: a Python or Dart literal of one of the JSON scalar types.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(untagged)]
pub enum Literal {
    Bool(bool),
    Integer(i64),
    Float(f64),
    Text(String),
}
