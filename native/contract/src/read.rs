// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The field readers of the Python grammar (`_contract_fields`, `_nonempty`, `_contract_strings`
//! and the others). Python `item.get(key)` reads an absent key and `null` the same; `has` tells
//! them apart, as `_has_field` does.

use crate::error::{invalid, Parsed};
use crate::json::{field, has, keys, Json, Object};
use crate::model::{DecidedBy, ItemId, RuleHead};
use crate::names::has_text;
use crate::words::value_of;

/// The value of a JSON variant, or the error "`label` must be `what`".
fn shaped<T>(value: Option<T>, label: &str, what: &str) -> Parsed<T> {
    value.ok_or_else(|| invalid(format!("{label} must be {what}")))
}

/// `_object`.
pub(crate) fn object<'a>(raw: &'a Json, label: &str) -> Parsed<&'a Object> {
    let found = match raw {
        Json::Object(object) => Some(object),
        _ => None,
    };
    shaped(found, label, "an object")
}

/// `_contract_fields`: each required key is present, and no key is outside both lists.
pub(crate) fn fields<'a>(
    raw: &'a Json,
    required: &[&str],
    optional: &[&str],
    label: &str,
) -> Parsed<&'a Object> {
    let item = object(raw, label)?;
    let complete = required.iter().all(|key| has(item, key));
    let known = keys(item).all(|key| required.contains(&key) || optional.contains(&key));
    if complete && known {
        Ok(item)
    } else {
        Err(invalid(format!("{label} fields mismatch")))
    }
}

/// The value of a key that `fields` has proved present.
pub(crate) fn present<'a>(item: &'a Object, key: &str, label: &str) -> Parsed<&'a Json> {
    field(item, key).ok_or_else(|| invalid(format!("{label}.{key} is missing")))
}

/// Python `item.get(key)`: `None` for an absent key and for `null`.
pub(crate) fn given<'a>(item: &'a Object, key: &str) -> Option<&'a Json> {
    field(item, key).filter(|value| !matches!(value, Json::Null))
}

/// `_string`.
pub(crate) fn text<'a>(raw: &'a Json, label: &str) -> Parsed<&'a str> {
    let found = match raw {
        Json::Text(value) => Some(value.as_str()),
        _ => None,
    };
    shaped(found, label, "a string")
}

/// `_nonempty`: a string with a character that is not white space.
pub(crate) fn nonempty(raw: &Json, label: &str) -> Parsed<String> {
    let value = text(raw, label)?;
    if has_text(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid(format!("{label} must not be empty")))
    }
}

/// `_nonempty` of `item.get(key)` when the value is given.
pub(crate) fn optional_nonempty(item: &Object, key: &str, label: &str) -> Parsed<Option<String>> {
    given(item, key)
        .map(|value| nonempty(value, &format!("{label}.{key}")))
        .transpose()
}

/// `_nonempty` of a key that `fields` has proved present.
pub(crate) fn nonempty_field(item: &Object, key: &str, label: &str) -> Parsed<String> {
    nonempty(present(item, key, label)?, &format!("{label}.{key}"))
}

/// `_strings`: an array of strings.
fn strings(raw: &Json, label: &str) -> Parsed<Vec<String>> {
    let items = match raw {
        Json::Array(items) => items,
        _ => return Err(invalid(format!("{label} must be a string array"))),
    };
    items
        .iter()
        .map(|item| match item {
            Json::Text(value) => Ok(value.clone()),
            _ => Err(invalid(format!("{label} must be a string array"))),
        })
        .collect()
}

/// Whether an item equals an item before it.
pub(crate) fn repeats<T: PartialEq>(items: &[T]) -> bool {
    items
        .iter()
        .enumerate()
        .any(|(index, item)| items.iter().take(index).any(|seen| seen == item))
}

/// `_contract_strings`: unique strings that are not empty, and at least one when `required`.
pub(crate) fn contract_strings(raw: &Json, label: &str, required: bool) -> Parsed<Vec<String>> {
    let values = strings(raw, label)?;
    if required && values.is_empty() {
        return Err(invalid(format!("{label} must not be empty")));
    }
    if repeats(&values) || values.iter().any(|value| !has_text(value)) {
        return Err(invalid(format!(
            "{label} must contain unique non-empty strings"
        )));
    }
    Ok(values)
}

/// `_contract_strings` of a key that `fields` has proved present.
pub(crate) fn strings_field(
    item: &Object,
    key: &str,
    label: &str,
    required: bool,
) -> Parsed<Vec<String>> {
    contract_strings(
        present(item, key, label)?,
        &format!("{label}.{key}"),
        required,
    )
}

/// `_contract_strings(item.get(key, []))`: an absent key is empty, `null` is an error.
pub(crate) fn listed_strings(item: &Object, key: &str, label: &str) -> Parsed<Vec<String>> {
    match field(item, key) {
        Some(value) => contract_strings(value, &format!("{label}.{key}"), false),
        None => Ok(Vec::new()),
    }
}

/// `item.get(key, default)` that must be a Boolean: `null` is an error.
pub(crate) fn flag(item: &Object, key: &str, default: bool, label: &str) -> Parsed<bool> {
    match field(item, key) {
        None => Ok(default),
        Some(Json::Bool(value)) => Ok(*value),
        Some(_) => Err(invalid(format!("{label}.{key} must be a boolean"))),
    }
}

/// An integer of at least 1 that is not a Boolean.
pub(crate) fn positive(raw: &Json, label: &str) -> Parsed<u64> {
    match raw {
        Json::Int(value) if *value >= 1 => u64::try_from(*value)
            .map_err(|_| invalid(format!("{label} must be a positive integer"))),
        _ => Err(invalid(format!("{label} must be a positive integer"))),
    }
}

/// `_decided_by`.
pub(crate) fn decided_by(raw: &Json, label: &str) -> Parsed<DecidedBy> {
    let value = nonempty(raw, label)?;
    value_of(&value).ok_or_else(|| invalid(format!("{label} must be architect or agent")))
}

/// `_contract_record`: the fields with `id` and `provenance`, the id and the provenance.
pub(crate) fn record<'a>(
    raw: &'a Json,
    required: &[&str],
    optional: &[&str],
    label: &str,
) -> Parsed<(&'a Object, ItemId, Vec<String>)> {
    let mut all = required.to_vec();
    all.extend(["id", "provenance"]);
    let item = fields(raw, &all, optional, label)?;
    let provenance = strings_field(item, "provenance", label, true)?;
    let id = nonempty_field(item, "id", label)?;
    Ok((item, ItemId(id), provenance))
}

/// The record of a rule: its fields with `kind`, `rationale` and `decided_by`, and its head.
pub(crate) fn rule_record<'a>(
    raw: &'a Json,
    required: &[&str],
    optional: &[&str],
    label: &str,
) -> Parsed<(&'a Object, RuleHead)> {
    let mut all = required.to_vec();
    all.extend(["kind", "rationale", "decided_by"]);
    let (item, id, provenance) = record(raw, &all, optional, label)?;
    let decided = present(item, "decided_by", label)?;
    let head = RuleHead {
        id,
        rationale: nonempty_field(item, "rationale", label)?,
        provenance,
        decided_by: decided_by(decided, &format!("{label}.decided_by"))?,
    };
    Ok((item, head))
}
