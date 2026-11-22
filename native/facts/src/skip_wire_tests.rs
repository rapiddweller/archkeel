// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `skip` and `absent` marks of `facts_data!` keep the wire keys that the old `omitted` gave.

use crate::nullable::Nullable;
use serde_json::{json, Value};

facts_data! {
    /// A record with one `Option` field and one `Nullable` field.
    pub struct Sample {
        /// An optional field.
        [read skip] option: Option<String>,
        /// A field that can be absent, null or a value.
        [read absent] nullable: Nullable<String>,
        /// A renamed optional field.
        [read skip "type"] kind: Option<bool>,
    }
}

fn sample(option: Option<&str>, nullable: Nullable<String>, kind: Option<bool>) -> Value {
    let data = Sample {
        option: option.map(str::to_owned),
        nullable,
        kind,
    };
    serde_json::to_value(data).unwrap()
}

#[test]
fn none_and_absent_write_no_key() {
    assert_eq!(sample(None, Nullable::Absent, None), json!({}));
}

#[test]
fn null_and_values_keep_their_key() {
    let value = sample(Some("a"), Nullable::Null, Some(false));
    assert_eq!(
        value,
        json!({"option": "a", "nullable": null, "type": false})
    );
    let value = sample(None, Nullable::Value("b".to_owned()), None);
    assert_eq!(value, json!({"nullable": "b"}));
}

#[test]
fn the_wire_text_decodes_to_the_same_values() {
    let text = r#"{"nullable":null,"type":true}"#;
    let data: Sample = serde_json::from_str(text).unwrap();
    assert_eq!(data.option, None);
    assert_eq!(data.nullable, Nullable::Null);
    assert_eq!(data.kind, Some(true));
    assert_eq!(serde_json::to_string(&data).unwrap(), text);
    let empty: Sample = serde_json::from_str("{}").unwrap();
    assert_eq!(empty.nullable, Nullable::Absent);
}
