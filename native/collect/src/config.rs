// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `[scan]` table of the repository configuration, read as `cli/config.py::parse_config`
//! reads it (AD-406). The core reads the file itself; the shell gives only its location.
//!
//! Each check of the Python parser that decides a field of the collection request is here, with
//! the same result. A configuration that the Python parser refuses is refused here too, by name.
//! A configuration that the in-process path cannot run yet (another profile, a configured
//! collector) is an `Unsupported` part, so the shell keeps its stage 1 path for it.

use archkeel_facts::envelope::Profile;
use toml::{Table, Value};

/// The fields that `[scan]` must have and may have (`_REQUIRED_SCAN`, `_OPTIONAL_SCAN`).
const REQUIRED: [&str; 3] = ["roots", "namespace", "contract"];
const OPTIONAL: [&str; 7] = [
    "language",
    "tsconfig",
    "collector_argv",
    "collector_output_limit_bytes",
    "collector_timeout_seconds",
    "bundler",
    "exclude_test_sources",
];
/// The characters that `_path` refuses: NUL, backslash, colon and the glob tokens.
const UNSAFE: [char; 10] = ['\0', '\\', ':', '*', '?', '[', ']', '{', '}', '!'];
/// `threading.TIMEOUT_MAX` on the 64-bit platforms of the wheel.
const TIMEOUT_MAX: i64 = 9_223_372_036;
/// `facts_codec.MAX_RESPONSE_LIMIT_BYTES`.
const MAX_RESPONSE_LIMIT_BYTES: i64 = 1 << 32;

/// Why the configuration gives no collection request.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Refused {
    /// The Python parser refuses it too.
    Invalid(String),
    /// Valid, but the in-process path does not run it yet: the part and why.
    Unsupported(&'static str, String),
}

/// The settings of a linked scan, as `ScanConfig` holds them.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct Config {
    pub profile: Profile,
    pub roots: Vec<String>,
    pub namespace: String,
    pub contract: String,
    pub tsconfig: String,
    pub bundler: bool,
    pub exclude_test_sources: bool,
}

fn invalid(text: &str) -> Refused {
    Refused::Invalid(text.to_owned())
}

/// Parse and check the configuration bytes. `name` is the file in the messages.
pub(crate) fn parse(payload: &[u8], name: &str) -> Result<Config, Refused> {
    let text = std::str::from_utf8(payload)
        .map_err(|error| Refused::Invalid(format!("invalid {name}: {error}")))?;
    let raw = text
        .parse::<Table>()
        .map_err(|error| Refused::Invalid(format!("invalid {name}: {error}")))?;
    let scan = match (raw.len(), raw.get("scan")) {
        (1, Some(Value::Table(scan))) => scan,
        _ => return Err(invalid("configuration must contain only [scan]")),
    };
    let known = |key: &String| REQUIRED.contains(&key.as_str()) || OPTIONAL.contains(&key.as_str());
    if !REQUIRED.iter().all(|key| scan.contains_key(*key)) || !scan.keys().all(known) {
        return Err(invalid(
            "[scan] requires roots, namespace, and contract; language, tsconfig, \
             collector_argv, collector_output_limit_bytes, collector_timeout_seconds, \
             bundler and exclude_test_sources are optional",
        ));
    }
    let language = language(scan)?;
    let tsconfig = match scan.get("tsconfig") {
        None => "tsconfig.json".to_owned(),
        Some(_) if language != "typescript" => {
            return Err(invalid(
                "scan.tsconfig is only valid when scan.language is typescript",
            ))
        }
        Some(value) => safe_path(value, "scan.tsconfig", false)?,
    };
    let bundler = flag(scan, "bundler", "scan.bundler must be a boolean")?;
    if scan.contains_key("bundler") && language != "typescript" {
        return Err(invalid(
            "scan.bundler is only valid when scan.language is typescript",
        ));
    }
    collector_limits(scan)?;
    let roots = roots(scan)?;
    let namespace = namespace(scan)?;
    let contract = posix(&safe_path(
        scan.get("contract").unwrap_or(&Value::Boolean(false)),
        "scan.contract",
        false,
    )?);
    let exclude_test_sources = flag(
        scan,
        "exclude_test_sources",
        "scan.exclude_test_sources must be a boolean",
    )?;
    let profile = match language {
        "typescript" => Profile::TypeScript,
        "rust" => Profile::Rust,
        _ => {
            // AD-406: each other profile stays on stage 1 by name.
            return Err(Refused::Unsupported(
                "profile",
                format!("the profile {language} has no collector in the core process yet"),
            ));
        }
    };
    if let Some(argv) = scan.get("collector_argv") {
        let first = match argv {
            Value::Array(items) => items.first().and_then(Value::as_str).unwrap_or_default(),
            _ => "",
        };
        return Err(Refused::Unsupported(
            "collector",
            format!("the run uses the configured collector {first}; the core runs only its own"),
        ));
    }
    Ok(Config {
        profile,
        roots,
        namespace,
        contract,
        tsconfig,
        bundler,
        exclude_test_sources,
    })
}

/// `_language_settings`: absent means Python (AD-97).
fn language(scan: &Table) -> Result<&str, Refused> {
    match scan.get("language") {
        None => Ok("python"),
        Some(Value::String(text))
            if matches!(text.as_str(), "python" | "dart" | "typescript" | "rust") =>
        {
            Ok(text.as_str())
        }
        Some(_) => Err(invalid(
            "scan.language must be \"python\", \"dart\", \"typescript\", or \"rust\"",
        )),
    }
}

/// A Boolean field: absent is false, and a value that is not a Boolean is refused.
fn flag(scan: &Table, key: &str, message: &str) -> Result<bool, Refused> {
    match scan.get(key) {
        None => Ok(false),
        Some(Value::Boolean(value)) => Ok(*value),
        Some(_) => Err(invalid(message)),
    }
}

/// `_collector_settings` and `_collector_timeout`: the limits of a subprocess collector. They do
/// not change the request, so the core only checks them as the Python parser does.
fn collector_limits(scan: &Table) -> Result<(), Refused> {
    if let Some(value) = scan.get("collector_output_limit_bytes") {
        match value {
            Value::Integer(limit) if (1..=MAX_RESPONSE_LIMIT_BYTES).contains(limit) => {}
            _ => {
                return Err(Refused::Invalid(format!(
                    "scan.collector_output_limit_bytes must be a positive integer no greater \
                     than {MAX_RESPONSE_LIMIT_BYTES} bytes"
                )))
            }
        }
    }
    if let Some(value) = scan.get("collector_timeout_seconds") {
        match value {
            Value::Integer(seconds) if (1..=TIMEOUT_MAX).contains(seconds) => {}
            _ => {
                return Err(Refused::Invalid(format!(
                    "scan.collector_timeout_seconds must be a positive integer no larger than \
                     {TIMEOUT_MAX}"
                )))
            }
        }
    }
    Ok(())
}

/// `_source_scope`: the roots, in their canonical POSIX form, without a repeat or an overlap.
fn roots(scan: &Table) -> Result<Vec<String>, Refused> {
    let items = match scan.get("roots") {
        Some(Value::Array(items)) if !items.is_empty() => items,
        _ => return Err(invalid("scan.roots must be a non-empty list")),
    };
    let mut roots: Vec<String> = Vec::with_capacity(items.len());
    for item in items {
        roots.push(posix(&safe_path(item, "scan.roots item", true)?));
    }
    for (at, current) in roots.iter().enumerate() {
        for other in roots.iter().skip(at.saturating_add(1)) {
            if current == other {
                return Err(invalid("scan.roots must not contain duplicates"));
            }
            if is_parent(current, other) || is_parent(other, current) {
                return Err(invalid("scan.roots must not overlap"));
            }
        }
    }
    Ok(roots)
}

/// `PurePosixPath(parent) in PurePosixPath(child).parents` for two canonical relative paths.
fn is_parent(parent: &str, child: &str) -> bool {
    parent == "." && child != "."
        || child
            .strip_prefix(parent)
            .is_some_and(|rest| rest.starts_with('/'))
}

/// `_NAMESPACE`: an ASCII dotted namespace.
fn namespace(scan: &Table) -> Result<String, Refused> {
    let message = "scan.namespace must be an ASCII dotted namespace";
    let Some(Value::String(text)) = scan.get("namespace") else {
        return Err(invalid(message));
    };
    let part = |part: &str| {
        let mut characters = part.chars();
        characters
            .next()
            .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
            && characters.all(|next| next.is_ascii_alphanumeric() || next == '_')
    };
    if text.split('.').all(part) {
        Ok(text.clone())
    } else {
        Err(invalid(message))
    }
}

/// `_path`: a non-empty safe POSIX relative path. `allow_dot` admits `.`.
fn safe_path(value: &Value, field: &str, allow_dot: bool) -> Result<String, Refused> {
    let text = match value {
        Value::String(text) if !text.is_empty() => text,
        _ => {
            return Err(Refused::Invalid(format!(
                "{field} must be a non-empty string"
            )))
        }
    };
    let unsafe_text = text.contains(UNSAFE)
        || text.starts_with('/')
        || text.split('/').any(|part| part == "..")
        || (!allow_dot && text == ".");
    if unsafe_text {
        return Err(Refused::Invalid(format!(
            "{field} must be a safe POSIX relative path"
        )));
    }
    Ok(text.clone())
}

/// `PurePosixPath(value).as_posix()` of a relative path: no empty part, no `.` part, and `.`
/// for a path that has no other part.
pub(crate) fn posix(value: &str) -> String {
    let parts: Vec<&str> = value
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    }
}

#[cfg(test)]
#[path = "config_tests.rs"]
mod tests;
