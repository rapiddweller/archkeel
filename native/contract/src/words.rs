// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The spelling of each closed value. Each closed enum derives its spelling with serde, so the
//! parser and the canonical writer read the same words.

use serde::de::value::{Error, StrDeserializer};
use serde::de::{DeserializeOwned, IntoDeserializer};
use serde::Serialize;

/// The value of a spelling, or `None` for a word outside the enum.
pub(crate) fn value_of<T: DeserializeOwned>(text: &str) -> Option<T> {
    let words: StrDeserializer<'_, Error> = text.into_deserializer();
    T::deserialize(words).ok()
}

/// The spelling of a value.
pub(crate) fn spelling<T: Serialize>(value: &T) -> String {
    match serde_json::to_value(value) {
        Ok(serde_json::Value::String(word)) => word,
        _ => String::new(),
    }
}
