// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `package.json` files as the resolver reads them, and the `exports` field of a package.
//!
//! Each read goes through the snapshot, so each manifest becomes a digested input.

use serde_json::{Map, Value};

use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;

/// A value that the resolver does not observe, with its reason.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Unknown {
    pub reason: String,
    /// The reason concerns package metadata inside a dependency, which a bundler decides itself.
    pub package_internal: bool,
}

impl Unknown {
    pub fn new(reason: impl Into<String>) -> Self {
        Self {
            reason: reason.into(),
            package_internal: false,
        }
    }

    pub fn internal(reason: impl Into<String>) -> Self {
        Self {
            reason: reason.into(),
            package_internal: true,
        }
    }
}

/// A lookup result: a hit, a reason it is not known, or no hit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Lookup<T> {
    Hit(T),
    Unknown(Unknown),
    Missing,
}

impl<T> Lookup<T> {
    /// `Some` for a hit or an unknown; the search stops there.
    pub fn stops(self) -> Option<Lookup<T>> {
        match self {
            Lookup::Missing => None,
            other => Some(other),
        }
    }
}

pub type Json = Map<String, Value>;

/// `config.decode`: the text of a JSON file without its byte order marks.
pub fn decode(raw: &[u8]) -> String {
    String::from_utf8_lossy(raw)
        .trim_start_matches('\u{feff}')
        .to_owned()
}

/// `Resolver._manifest`: the `package.json` of a directory.
pub fn read(snapshot: &mut Snapshot, directory: &str) -> (Option<String>, Lookup<Json>) {
    let path = join(directory, "package.json");
    let Some(raw) = snapshot.read(&path) else {
        return (None, Lookup::Missing);
    };
    let found = match serde_json::from_str::<Value>(&decode(&raw)) {
        Ok(Value::Object(map)) => Lookup::Hit(map),
        Ok(_) => Lookup::Unknown(Unknown::new(format!(
            "Package metadata is not an object: {path}"
        ))),
        Err(_) => Lookup::Unknown(Unknown::new(format!(
            "Package metadata is not valid JSON: {path}"
        ))),
    };
    (Some(path), found)
}

/// Whether `exports` is truthy in JavaScript, where an empty object still counts.
pub fn declares_exports(manifest: &Json) -> bool {
    match manifest.get("exports") {
        None | Some(Value::Null | Value::Bool(false)) => false,
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
        Some(_) => true,
    }
}

/// `_package_type`: whether the manifest says `"type": "module"`.
pub fn is_module(manifest: &Json) -> bool {
    manifest.get("type").and_then(Value::as_str) == Some("module")
}

/// What `exports` selects for a condition set: a path, a reason, or nothing.
pub enum Condition {
    Target(String),
    Unknown(Unknown),
    Nothing,
}

/// `Resolver._export_condition`: the first target that an active condition names.
pub fn condition(value: &Value, esm: bool) -> Condition {
    let object = match value {
        Value::String(text) => return Condition::Target(text.clone()),
        Value::Object(object) => object,
        _ => {
            return Condition::Unknown(Unknown::new("Package exports conditions are not observed"))
        }
    };
    let active = if esm { "import" } else { "require" };
    for (name, target) in object {
        match name.as_str() {
            "types" | "default" => {}
            name if name == active => {}
            "import" | "require" => continue,
            other => {
                return Condition::Unknown(Unknown::internal(format!(
                    "Package exports condition is not observed: {other}"
                )))
            }
        }
        if !(target.is_object() || target.is_string()) {
            return Condition::Unknown(Unknown::new("Package exports conditions are not observed"));
        }
        match condition(target, esm) {
            Condition::Nothing => {}
            selected => return selected,
        }
    }
    Condition::Nothing
}

/// The `exports` entry for `key`, or why none can be chosen: `Ok(None)` names no entry.
pub fn selected<'a>(
    exports: &'a Value,
    name: &str,
    rest: &str,
    key: &str,
) -> Result<Option<&'a Value>, Unknown> {
    match exports {
        Value::String(_) => Ok(rest.is_empty().then_some(exports)),
        Value::Object(map) => {
            let subpaths: Vec<bool> = map.keys().map(|item| item.starts_with('.')).collect();
            if subpaths.iter().any(|dotted| *dotted) && !subpaths.iter().all(|dotted| *dotted) {
                return Err(Unknown::new(format!(
                    "Package exports map shape is not observed: {name}"
                )));
            }
            if !map.is_empty() && subpaths.iter().all(|dotted| *dotted) {
                // JSON `null` is `None` in Python: it names no entry.
                let found = map.get(key).filter(|value| !value.is_null());
                if found.is_none() && !rest.is_empty() && map.keys().any(|item| item.contains('*'))
                {
                    return Err(Unknown::new(format!(
                        "Package exports patterns are not observed: {name}/{rest}"
                    )));
                }
                Ok(found)
            } else {
                Ok(rest.is_empty().then_some(exports))
            }
        }
        _ => Err(Unknown::new(format!(
            "Package exports shape is not observed: {name}"
        ))),
    }
}

/// `\./[^/%?#\\]+(?:/[^/%?#\\]+)*\Z` without a `.`, `..` or `node_modules` segment.
pub fn plain_target(target: &str) -> bool {
    let Some(rest) = target.strip_prefix("./") else {
        return false;
    };
    rest.split('/').all(|segment| {
        !segment.is_empty()
            && !segment.contains(['%', '?', '#', '\\'])
            && !matches!(segment, "." | ".." | "node_modules")
    })
}

#[cfg(test)]
#[path = "manifest_tests.rs"]
mod tests;
