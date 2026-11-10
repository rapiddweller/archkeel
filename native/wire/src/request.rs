// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Strict decoding of a TypeScript collection request, as `facts_codec.decode_request` does it.

use serde_json::{Map, Value};

use crate::identity::is_identifier;
use crate::protocol::Version;

/// One TypeScript collection request.
#[derive(Clone, Debug, PartialEq)]
pub struct Request {
    pub version: Version,
    /// The absolute snapshot root.
    pub root: String,
    pub git_head: String,
    /// `true`, `false` or `"unknown"`, echoed back unchanged.
    pub dirty: Value,
    pub roots: Vec<String>,
    pub namespace: String,
    /// Only a 9.0.0 request can set this.
    pub exclude_test_sources: bool,
    pub tsconfig: String,
    pub bundler: bool,
}

/// The language that a native collector reads: its resolver names it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Language {
    TypeScript,
    Rust,
}

impl Language {
    /// The text of the resolver and the name in the error.
    fn resolver_name(self) -> &'static str {
        match self {
            Language::TypeScript => "typescript",
            Language::Rust => "rust",
        }
    }

    fn label(self) -> &'static str {
        match self {
            Language::TypeScript => "TypeScript",
            Language::Rust => "Rust",
        }
    }
}

/// Decode a TypeScript request. The error text names the first field that is not valid.
pub fn decode(payload: &[u8]) -> Result<Request, String> {
    decode_for(payload, Language::TypeScript)
}

/// Decode a Rust request. Its resolver is `{"language": "rust"}`, so `tsconfig` is empty.
pub fn decode_rust(payload: &[u8]) -> Result<Request, String> {
    decode_for(payload, Language::Rust)
}

fn decode_for(payload: &[u8], wanted: Language) -> Result<Request, String> {
    let raw: Value = serde_json::from_slice(payload)
        .map_err(|error| format!("invalid collection JSON: {error}"))?;
    let raw = object(
        &raw,
        &["protocol_version", "snapshot", "scope", "resolver"],
        "request",
    )?;
    let version = raw["protocol_version"]
        .as_str()
        .and_then(Version::parse)
        .ok_or("unsupported collection protocol version")?;
    let snapshot = object(&raw["snapshot"], &["root", "git_head", "dirty"], "snapshot")?;
    let root = string(&snapshot["root"], "snapshot.root")?;
    if !is_absolute(&root) {
        return Err("snapshot.root must be an absolute path".to_owned());
    }
    let dirty = snapshot["dirty"].clone();
    if !(dirty.is_boolean() || dirty.as_str() == Some("unknown")) {
        return Err("snapshot.dirty must be a boolean or unknown".to_owned());
    }
    let scope_fields: &[&str] = if version.has_test_scope() {
        &["roots", "namespace", "exclude_test_sources"]
    } else {
        &["roots", "namespace"]
    };
    let scope = object(&raw["scope"], scope_fields, "scope")?;
    let roots = roots(&scope["roots"])?;
    let namespace = string(&scope["namespace"], "scope.namespace")?;
    if !namespace.split('.').all(is_identifier) {
        return Err("scope.namespace must be a dotted namespace".to_owned());
    }
    let exclude_test_sources = match scope.get("exclude_test_sources") {
        Some(value) => value
            .as_bool()
            .ok_or("scope.exclude_test_sources must be a boolean")?,
        None => false,
    };
    let (tsconfig, bundler) = resolver(&raw["resolver"], wanted)?;
    Ok(Request {
        version,
        root,
        git_head: string(&snapshot["git_head"], "snapshot.git_head")?,
        dirty,
        roots,
        namespace,
        exclude_test_sources,
        tsconfig,
        bundler,
    })
}

fn resolver(value: &Value, wanted: Language) -> Result<(String, bool), String> {
    let fields = value.as_object().ok_or("resolver fields mismatch")?;
    let language = string(
        fields.get("language").unwrap_or(&Value::Null),
        "resolver.language",
    )?;
    if language != wanted.resolver_name() {
        let label = wanted.label();
        return Err(
            if matches!(language.as_str(), "python" | "dart" | "typescript" | "rust") {
                format!("{label} collector requires the {label} resolver")
            } else {
                "unsupported collection language".to_owned()
            },
        );
    }
    if wanted == Language::Rust {
        object(value, &["language"], "resolver")?;
        return Ok((String::new(), false));
    }
    // The host writes "bundler" only when true, so false has one canonical form: absent.
    let bundler = fields.contains_key("bundler");
    let expected: &[&str] = if bundler {
        &["language", "tsconfig", "bundler"]
    } else {
        &["language", "tsconfig"]
    };
    let fields = object(value, expected, "resolver")?;
    if bundler && fields["bundler"] != Value::Bool(true) {
        return Err("resolver.bundler must be true when present".to_owned());
    }
    Ok((relative(&fields["tsconfig"], "resolver.tsconfig")?, bundler))
}

fn roots(value: &Value) -> Result<Vec<String>, String> {
    let items = value
        .as_array()
        .filter(|items| !items.is_empty())
        .ok_or("scope.roots must be a nonempty array")?;
    let roots = items
        .iter()
        .map(|item| relative(item, "scope.roots"))
        .collect::<Result<Vec<_>, _>>()?;
    let parts: Vec<Vec<&str>> = roots.iter().map(|root| path_parts(root)).collect();
    for (index, root) in parts.iter().enumerate() {
        if roots[index + 1..].contains(&roots[index]) {
            return Err("scope.roots must not repeat".to_owned());
        }
        for other in &parts[index + 1..] {
            let (short, long) = if root.len() <= other.len() {
                (root, other)
            } else {
                (other, root)
            };
            if short.len() < long.len() && long.starts_with(short) {
                return Err("scope.roots must not overlap".to_owned());
            }
        }
    }
    Ok(roots)
}

fn object<'a>(
    value: &'a Value,
    fields: &[&str],
    label: &str,
) -> Result<&'a Map<String, Value>, String> {
    match value.as_object() {
        Some(map) if map.len() == fields.len() && fields.iter().all(|f| map.contains_key(*f)) => {
            Ok(map)
        }
        _ => Err(format!("{label} fields mismatch")),
    }
}

fn string(value: &Value, label: &str) -> Result<String, String> {
    match value.as_str() {
        Some(text) if !text.is_empty() && !text.contains('\0') => Ok(text.to_owned()),
        _ => Err(format!("{label} must be a nonempty string")),
    }
}

fn relative(value: &Value, label: &str) -> Result<String, String> {
    let path = string(value, label)?;
    if path.starts_with('/')
        || path.split('/').any(|part| part == "..")
        || path.contains('\\')
        || path.contains(':')
    {
        return Err(format!("{label} must stay inside the snapshot"));
    }
    Ok(path)
}

// The parts PurePosixPath keeps: no empty part and no "." part.
fn path_parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect()
}

fn is_absolute(root: &str) -> bool {
    let bytes = root.as_bytes();
    let posix = root.starts_with('/') && !root.contains('\\');
    let drive = bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'/' | b'\\');
    let unc = root.starts_with("\\\\") || root.starts_with("//");
    let windows = (drive || unc) && !(root.contains('/') && root.contains('\\'));
    posix || windows
}

#[cfg(test)]
#[path = "request_tests.rs"]
mod tests;
