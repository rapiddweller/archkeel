// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The collection request that the host writes and a native collector reads (3.0.0, 8.0.0, 9.0.0,
//! 10.0.0).
//!
//! The types are closed: an unknown field is a decode error. The JSON schema of the request is
//! generated from them (`schema::request_schema`). A rule that a type cannot hold, such as the
//! scope roots that must not overlap, is in `request_rules`.

use schemars::JsonSchema;
use serde::{Deserialize, Deserializer, Serialize};

use crate::envelope::Dirty;
use crate::protocol::Version;
use crate::pyminor::PythonVersion;

/// One collection request. `R` is the settings of the language: the whole `Resolver` as the wire
/// has it, or the settings of one language after the collector has chosen it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Request<R = Resolver> {
    #[serde(deserialize_with = "version")]
    pub protocol_version: Version,
    pub snapshot: Snapshot,
    pub scope: Scope,
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
    #[serde(rename = "typescript")]
    TypeScript(TypeScriptSettings),
    #[serde(rename = "rust")]
    Rust(RustSettings),
    #[serde(rename = "python")]
    Python(PythonSettings),
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
    pub phase: PythonPhase,
    pub interpreter: Interpreter,
}

closed! {
    /// The part of the Python collection that the request asks for. Slice 1 has the import survey.
    pub enum PythonPhase {
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
        self.resolver.check()
    }
}
