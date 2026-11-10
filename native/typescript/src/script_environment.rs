// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `archkeel` object of a TSConfig: the host that a script runs in and the vendored libraries
//! that it may use (`config._script_environment`).

use serde_json::{Map, Value};

use archkeel_snapshot::paths::{is_outside, join};

/// A vendored library: its source and the file that says where it came from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScriptProvider {
    pub source: String,
    pub provenance: String,
}

/// The script environment that a project declares.
#[derive(Clone, Debug, Default)]
pub struct ScriptEnvironment {
    /// An explicit classic browser has neither CommonJS nor AMD loader globals.
    pub classic_browser: bool,
    pub providers: Vec<ScriptProvider>,
}

/// A path that names one file inside the snapshot, in its normal form.
fn is_snapshot_path(path: &Value) -> bool {
    let Some(path) = path.as_str() else {
        return false;
    };
    !path.is_empty()
        && path != "."
        && !path.starts_with('/')
        && !path.contains('\\')
        && join(".", path) == path
        && !is_outside(path)
}

/// `config._script_environment`.
pub fn read(raw: Option<&Map<String, Value>>, problems: &mut Vec<String>) -> ScriptEnvironment {
    let Some(found) = raw
        .and_then(|raw| raw.get("archkeel"))
        .filter(|v| !v.is_null())
    else {
        return ScriptEnvironment::default();
    };
    let object = found.as_object().filter(|o| {
        o.keys()
            .all(|k| matches!(k.as_str(), "scriptHost" | "scriptProviders"))
    });
    let Some(object) = object else {
        problems.push("Archkeel script environment is not a closed object".to_owned());
        return ScriptEnvironment::default();
    };
    let mut environment = ScriptEnvironment::default();
    if let Some(host) = object.get("scriptHost").filter(|v| !v.is_null()) {
        if host.as_str() == Some("classic-browser") {
            environment.classic_browser = true;
        } else {
            problems.push("Archkeel script host is not supported".to_owned());
        }
    }
    let entries = object
        .get("scriptProviders")
        .unwrap_or(&Value::Array(Vec::new()))
        .clone();
    let Some(entries) = entries.as_array() else {
        problems.push("Archkeel script providers must be a list".to_owned());
        return environment;
    };
    for entry in entries {
        let fields = entry
            .as_object()
            .filter(|o| o.len() == 2 && o.contains_key("source") && o.contains_key("provenance"));
        let valid = fields.is_some_and(|o| o.values().all(is_snapshot_path));
        let (true, Some(fields)) = (valid, fields) else {
            problems.push("Archkeel script provider needs two snapshot-relative paths".to_owned());
            continue;
        };
        let text = |key: &str| {
            fields
                .get(key)
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned()
        };
        let provider = ScriptProvider {
            source: text("source"),
            provenance: text("provenance"),
        };
        if environment.providers.contains(&provider) {
            problems.push("Archkeel script provider is declared more than once".to_owned());
        }
        environment.providers.push(provider);
    }
    environment
}

#[cfg(test)]
#[path = "script_environment_tests.rs"]
mod tests;
