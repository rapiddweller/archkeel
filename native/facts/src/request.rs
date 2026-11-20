// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The collection request that the host writes and a native collector reads (3.0.0, 8.0.0, 9.0.0,
//! 10.0.0).
//!
//! The types are closed: an unknown field is a decode error. The JSON schema of the request is
//! generated from them (`schema::request_schema`). A rule that a type cannot hold, such as the
//! scope roots that must not overlap, is checked below, in the file of the types it checks.

use schemars::JsonSchema;
use serde::{Deserialize, Deserializer, Serialize};

use crate::envelope::Dirty;
use crate::identity::{inside, is_identifier};
use crate::protocol::Version;
use crate::pyminor::PythonVersion;

/// One collection request. `R` is the settings of the language: the whole `Resolver` as the wire
/// has it, or the settings of one language after the collector has chosen it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Request<R = Resolver> {
    /// The protocol version that the reply must use.
    #[serde(deserialize_with = "version")]
    pub protocol_version: Version,
    /// The tree that the collector reads.
    pub snapshot: Snapshot,
    /// The files that the collector reads.
    pub scope: Scope,
    /// The resolver settings of the language.
    pub resolver: R,
}

/// A request for the TypeScript collector.
pub type TypeScriptRequest = Request<TypeScriptSettings>;
/// A request for the Rust collector.
pub type RustRequest = Request<RustSettings>;
/// A request for the Python collector (10.0.0).
pub type PythonRequest = Request<PythonSettings>;
/// A request for the Dart collector (3.0.0, 8.0.0 or 9.0.0).
pub type DartRequest = Request<DartSettings>;

/// The snapshot to read.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    /// The absolute snapshot root.
    pub root: String,
    /// The commit that the tree is at.
    pub git_head: String,
    /// `true`, `false` or `"unknown"`, echoed back in the reply.
    #[serde(deserialize_with = "dirty")]
    pub dirty: Dirty,
}

/// The part of the snapshot to read.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Scope {
    /// Nonempty relative paths that stay inside the snapshot and neither repeat nor overlap.
    pub roots: Vec<String>,
    /// A dotted namespace.
    pub namespace: String,
    /// Present exactly in a 9.0.0 request (AD-313).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    #[schemars(with = "bool")]
    pub exclude_test_sources: Option<bool>,
}

/// The settings of one language. The tag is the language that the collector reads.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "language", deny_unknown_fields)]
pub enum Resolver {
    /// The settings of the TypeScript resolver.
    #[serde(rename = "typescript")]
    TypeScript(TypeScriptSettings),
    /// The settings of the Rust resolver.
    #[serde(rename = "rust")]
    Rust(RustSettings),
    /// The settings of the Python resolver.
    #[serde(rename = "python")]
    Python(PythonSettings),
    /// The settings of the Dart resolver.
    #[serde(rename = "dart")]
    Dart(DartSettings),
}

/// The settings of the TypeScript collector.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TypeScriptSettings {
    /// A relative path that stays inside the snapshot.
    pub tsconfig: String,
    /// The host writes `bundler` only when it is true, so false has one form: absent.
    #[serde(
        default,
        skip_serializing_if = "is_false",
        deserialize_with = "only_true"
    )]
    #[schemars(schema_with = "always_true")]
    pub bundler: bool,
}

/// The Rust collector has no settings: its resolver is `{"language": "rust"}`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RustSettings {}

/// The Dart collector has no settings: its resolver is `{"language": "dart"}`, as
/// `ir/protocol.DartSettings` writes it. Protocol 10.0.0 stays Python only (AD-334, AD-368).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DartSettings {}

/// The settings of the Python collector (AD-334). Only protocol 10.0.0 carries them.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PythonSettings {
    /// The phase of the Python collection.
    pub phase: PythonPhase,
    /// Conflicting build metadata leaves the runtime import roots unknown.
    #[serde(
        default,
        skip_serializing_if = "is_false",
        deserialize_with = "only_true"
    )]
    #[schemars(schema_with = "always_true")]
    pub import_roots_ambiguous: bool,
    /// The configured target version, when the scan names one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub python: Option<String>,
    /// A legacy interpreter description from an older caller.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub interpreter: Option<Interpreter>,
}

closed! {
    /// The part of the Python collection that the request asks for. Slice 1 has the import survey.
    pub enum PythonPhase {
        /// The import survey.
        Imports = "imports",
    }
}

/// What the host interpreter is, as one isolated child (`python -I`) sees it. The host builds it
/// in one function (`analyzer/interpreter.py`); the collector reads it and never runs Python.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Interpreter {
    /// `platform.python_version()`, for example `3.11.12`: the version that the facts claim.
    #[schemars(with = "String")]
    pub version: PythonVersion,
    /// `sys.stdlib_module_names`, sorted.
    pub stdlib_module_names: Vec<String>,
    /// `sys.builtin_module_names`, sorted. The set depends on the build, not on the version.
    pub builtin_module_names: Vec<String>,
}

fn version<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Version, D::Error> {
    Version::deserialize(deserializer).map_err(|_| {
        let known: Vec<&str> = Version::ALL
            .iter()
            .map(|version| version.as_str())
            .collect();
        serde::de::Error::custom(format!(
            "unsupported collection protocol version, expected one of {}",
            known.join(", ")
        ))
    })
}

fn dirty<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Dirty, D::Error> {
    Dirty::deserialize(deserializer)
        .map_err(|_| serde::de::Error::custom("snapshot.dirty must be a boolean or unknown"))
}

fn always_true(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
    schemars::json_schema!({"const": true})
}

fn is_false(value: &bool) -> bool {
    !value
}

fn only_true<'de, D: Deserializer<'de>>(deserializer: D) -> Result<bool, D::Error> {
    match bool::deserialize(deserializer)? {
        true => Ok(true),
        false => Err(serde::de::Error::custom(
            "resolver.bundler must be true when present",
        )),
    }
}

impl<R> Request<R> {
    /// Whether the collector leaves the test sources out.
    pub fn excludes_test_sources(&self) -> bool {
        self.scope.exclude_test_sources.unwrap_or(false)
    }

    fn with<S>(self, resolver: S) -> Request<S> {
        Request {
            protocol_version: self.protocol_version,
            snapshot: self.snapshot,
            scope: self.scope,
            resolver,
        }
    }
}

impl Request {
    /// The request for the TypeScript collector, or the message when it is for another language.
    pub fn typescript(self) -> Result<TypeScriptRequest, String> {
        match self.resolver.clone() {
            Resolver::TypeScript(settings) => Ok(self.with(settings)),
            _ => Err("TypeScript collector requires the TypeScript resolver".into()),
        }
    }

    /// The request for the Rust collector, or the message when it is for another language.
    pub fn rust(self) -> Result<RustRequest, String> {
        match self.resolver.clone() {
            Resolver::Rust(settings) => Ok(self.with(settings)),
            _ => Err("Rust collector requires the Rust resolver".into()),
        }
    }

    /// The request for the Python collector, or the message when it is for another language.
    pub fn python(self) -> Result<PythonRequest, String> {
        match self.resolver.clone() {
            Resolver::Python(settings) => Ok(self.with(settings)),
            _ => Err("Python collector requires the Python resolver".into()),
        }
    }

    /// The request for the Dart collector, or the message when it is for another language.
    pub fn dart(self) -> Result<DartRequest, String> {
        match self.resolver.clone() {
            Resolver::Dart(settings) => Ok(self.with(settings)),
            _ => Err("Dart collector requires the Dart resolver".into()),
        }
    }

    /// Check the request, settings included.
    pub fn validate(&self) -> Result<(), String> {
        self.check()?;
        let python = matches!(self.resolver, Resolver::Python(_));
        match (python, self.protocol_version.is_python()) {
            (true, false) => return Err("the Python resolver requires protocol 10.0.0".into()),
            (false, true) => return Err("protocol 10.0.0 requires the Python resolver".into()),
            _ => {}
        }
        if let Resolver::Python(settings) = &self.resolver {
            if settings.import_roots_ambiguous && !self.scope.namespace.is_empty() {
                return Err("import_roots_ambiguous needs Python import roots".into());
            }
        }
        self.resolver.check()
    }
}

// The rules of a collection request that a type cannot hold: the messages name the first field
// that is not valid, as `facts_codec.decode_request` does.

impl<R> Request<R> {
    /// Check the snapshot and the scope. The settings of a language check themselves.
    pub fn check(&self) -> Result<(), String> {
        self.snapshot.check()?;
        self.scope.check(self.protocol_version)
    }
}

impl Snapshot {
    fn check(&self) -> Result<(), String> {
        text(&self.root, "snapshot.root")?;
        if !is_absolute(&self.root) {
            return Err("snapshot.root must be an absolute path".to_owned());
        }
        text(&self.git_head, "snapshot.git_head")
    }
}

impl Scope {
    fn check(&self, version: Version) -> Result<(), String> {
        if self.exclude_test_sources.is_some() != version.has_test_scope() {
            return Err("scope fields mismatch".to_owned());
        }
        if !self.namespace.is_empty() || !version.is_python() {
            text(&self.namespace, "scope.namespace")?;
            if !self.namespace.split('.').all(is_identifier) {
                return Err("scope.namespace must be a dotted namespace".to_owned());
            }
        }
        if self.roots.is_empty() {
            return Err("scope.roots must be a nonempty array".to_owned());
        }
        check_roots(&self.roots)?;
        Ok(())
    }
}

fn check_roots(roots: &[String]) -> Result<(), String> {
    for root in roots {
        relative(root, "scope.roots")?;
    }
    let parts: Vec<Vec<&str>> = roots.iter().map(|root| path_parts(root)).collect();
    for (index, root) in parts.iter().enumerate() {
        if roots[index + 1..].contains(&roots[index]) {
            return Err("scope.roots must not repeat".to_owned());
        }
        if parts[index + 1..].iter().any(|other| nested(root, other)) {
            return Err("scope.roots must not overlap".to_owned());
        }
    }
    Ok(())
}

/// Whether one path is a proper prefix of the other.
fn nested(left: &[&str], right: &[&str]) -> bool {
    let (short, long) = if left.len() <= right.len() {
        (left, right)
    } else {
        (right, left)
    };
    short.len() < long.len() && long.starts_with(short)
}

impl Resolver {
    pub(crate) fn check(&self) -> Result<(), String> {
        match self {
            Resolver::TypeScript(settings) => relative(&settings.tsconfig, "resolver.tsconfig"),
            Resolver::Rust(_) | Resolver::Dart(_) => Ok(()),
            Resolver::Python(settings)
                if settings.python.is_some() && settings.interpreter.is_some() =>
            {
                Err(
                    "a Python request cannot name both a target and a legacy interpreter"
                        .to_owned(),
                )
            }
            Resolver::Python(settings) => settings
                .interpreter
                .as_ref()
                .map_or(Ok(()), Interpreter::check),
        }
    }
}

impl Interpreter {
    fn check(&self) -> Result<(), String> {
        module_names(&self.stdlib_module_names, "stdlib_module_names")?;
        module_names(&self.builtin_module_names, "builtin_module_names")
    }
}

fn module_names(names: &[String], field: &str) -> Result<(), String> {
    let label = format!("resolver.interpreter.{field}");
    if !names.iter().all(|name| is_identifier(name)) {
        return Err(format!("{label} must hold module names"));
    }
    if names.windows(2).any(|pair| pair[0] >= pair[1]) {
        return Err(format!("{label} must be sorted and unique"));
    }
    Ok(())
}

fn text(value: &str, label: &str) -> Result<(), String> {
    if value.is_empty() || value.contains('\0') {
        return Err(format!("{label} must be a nonempty string"));
    }
    Ok(())
}

fn relative(path: &str, label: &str) -> Result<(), String> {
    text(path, label)?;
    if !inside(path) {
        return Err(format!("{label} must stay inside the snapshot"));
    }
    Ok(())
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
