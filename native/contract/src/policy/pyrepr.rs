// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python `repr` texts that the messages of a widening hold, so that each message is equal to
//! the message of `ir/widening*.py`.

use serde_json::Value;

use crate::policy::reference::python_repr;

/// A text value of the contract model.
pub(crate) trait AsText {
    fn text(&self) -> &str;
}

impl AsText for String {
    fn text(&self) -> &str {
        self
    }
}

impl AsText for crate::model::Selector {
    fn text(&self) -> &str {
        &self.0
    }
}

impl AsText for crate::model::ComponentLabel {
    fn text(&self) -> &str {
        &self.0
    }
}

/// The texts of a list of text values.
pub(crate) fn texts<T: AsText>(items: &[T]) -> Vec<&str> {
    items.iter().map(AsText::text).collect()
}

/// The word of a closed enum: its serde spelling.
pub(crate) fn word<T: serde::Serialize>(value: &T) -> String {
    crate::words::spelling(value)
}

/// Python `repr(list_of_texts)`.
pub(crate) fn list<'a>(items: impl IntoIterator<Item = &'a str>) -> String {
    let texts: Vec<String> = items.into_iter().map(python_repr).collect();
    format!("[{}]", texts.join(", "))
}

/// Python `repr(tuple_of_texts)`: `()`, `('a',)` or `('a', 'b')`.
fn tuple(texts: &[String]) -> String {
    match texts {
        [] => "()".to_owned(),
        [one] => format!("({one},)"),
        many => format!("({})", many.join(", ")),
    }
}

/// Python `repr` of a member of a `StrEnum` inside a container: `<Class.NAME: 'value'>`.
fn member(class: &str, value: &str) -> String {
    format!("<{class}.{}: {}>", value.to_uppercase(), python_repr(value))
}

/// The Python class of the enum members of a field, where a field holds members in a container.
fn member_class(field: &str) -> Option<&'static str> {
    match field {
        "roles" => Some("SourceOwnershipRole"),
        "class_kinds" => Some("SymbolClassKind"),
        "constructs" => Some("ForbiddenConstructKind"),
        "role" => Some("ConstructSelectorRole"),
        _ => None,
    }
}

/// The fields of a nested record in the order of its Python dataclass. A field that the
/// canonical value leaves out is `None` in Python.
fn record_fields(field: &str) -> Option<&'static [&'static str]> {
    match field {
        "selector" => Some(&["receiver", "member", "role", "literal"]),
        _ => None,
    }
}

/// Python `repr` of one value of `dataclasses.asdict`, from the canonical value of the field.
/// A text at the top level is a text, also for a `StrEnum`. `None` is an absent value.
pub(crate) fn value(field: &str, item: Option<&Value>) -> String {
    match item {
        None | Some(Value::Null) => "None".to_owned(),
        Some(Value::String(text)) => python_repr(text),
        Some(other) => nested(field, other),
    }
}

fn nested(field: &str, item: &Value) -> String {
    match item {
        Value::Null => "None".to_owned(),
        Value::Bool(flag) => if *flag { "True" } else { "False" }.to_owned(),
        Value::Number(number) => number.to_string(),
        Value::String(text) => match member_class(field) {
            Some(class) => member(class, text),
            None => python_repr(text),
        },
        Value::Array(items) => {
            let texts: Vec<String> = items.iter().map(|entry| nested(field, entry)).collect();
            tuple(&texts)
        }
        Value::Object(entries) => {
            let order: Vec<&str> = match record_fields(field) {
                Some(names) => names.to_vec(),
                None => entries.keys().map(String::as_str).collect(),
            };
            let texts: Vec<String> = order
                .iter()
                .map(|key| {
                    let inner = entries.get(*key).unwrap_or(&Value::Null);
                    format!("{}: {}", python_repr(key), nested(key, inner))
                })
                .collect();
            format!("{{{}}}", texts.join(", "))
        }
    }
}
