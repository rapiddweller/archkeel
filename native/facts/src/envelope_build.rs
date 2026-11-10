// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The constructors of the envelope types that a collector calls. The Python-shaped fields that
//! the native collectors never set are written empty.

use serde_json::Value;

use super::{
    Adapter, Capabilities, ConstructCapability, ConstructSupport, Coverage, Dirty, Evidence,
    FileFact, Input, Profile, RequirementState, Runtime, SectionName, Source,
};
use crate::identity::{evidence_id, package_of, sha256_hex, stable_id, Part};
use crate::ids::{EvidenceId, FactId, ModuleName, PackageName};
use crate::record::Record;
use crate::sections::GapFact;

/// The producer of a collector reply: its profile, its adapter and its runtime.
#[derive(Clone, Debug, PartialEq)]
pub struct Provenance {
    pub profile: Profile,
    pub adapter: Adapter,
    pub runtime: Runtime,
}

impl Provenance {
    /// The provenance of a native collector that is written in Rust. The build script gives the
    /// version, the digest and the compiler; `rust_version` is the minimum of the crate.
    pub fn native(
        profile: Profile,
        (adapter_version, code_digest): (&str, &str),
        (runtime_version, rust_version): (&str, &str),
    ) -> Self {
        Self {
            profile,
            adapter: Adapter {
                code_digest: code_digest.to_owned(),
                name: profile.as_str().to_owned(),
                version: adapter_version.to_owned(),
            },
            runtime: Runtime {
                name: "rust".to_owned(),
                required: Some(format!(">={rust_version}")),
                requirement_state: RequirementState::Declared,
                version: runtime_version.to_owned(),
            },
        }
    }
}

impl FileFact {
    /// The file fact of a module: the id and the package come from the module identity.
    pub fn of((rel_path, module): (&str, &str), blank: bool, evidence_id: String) -> Self {
        Self {
            id: FactId::new(stable_id("FILE", &[Part::Text(module)])),
            rel_path: rel_path.to_owned(),
            module: ModuleName::new(module),
            package: PackageName::new(package_of(module)),
            all_exports: Vec::new(),
            all_literal: false,
            compatibility_logic_free: false,
            stable_bindings: Vec::new(),
            blank,
            evidence_id: EvidenceId::new(evidence_id),
        }
    }
}

impl Evidence {
    /// The evidence of one source location, with the text of its first line.
    pub fn at(file: &str, line: i64, end_line: i64, column: i64, excerpt: &str) -> Self {
        Self {
            id: EvidenceId::new(evidence_id(file, line, end_line, column)),
            file: file.to_owned(),
            line,
            end_line,
            column,
            excerpt: excerpt.to_owned(),
        }
    }
}

impl Source {
    /// The source of a request. `dirty` is the Boolean or the text `unknown` of the request.
    pub fn of(
        (git_head, dirty): (&str, &Value),
        scope: &[String],
        inputs: &[Input],
    ) -> Result<Self, String> {
        let dirty = Dirty::deserialize_value(dirty)?;
        Ok(Self {
            dirty,
            git_head: git_head.to_owned(),
            scope: scope.to_vec(),
            source_digest: source_digest(inputs),
        })
    }
}

impl Dirty {
    fn deserialize_value(value: &Value) -> Result<Self, String> {
        serde_json::from_value(value.clone())
            .map_err(|_| "dirty must be a boolean or unknown".to_owned())
    }
}

impl Capabilities {
    /// The capabilities of a collector that names its sections and constructs by their texts.
    pub fn of(
        sections: &[&str],
        features: &[&str],
        constructs: &[(&str, &str)],
    ) -> Result<Self, String> {
        let sections = sections
            .iter()
            .map(|name| SectionName::parse(name).ok_or_else(|| format!("unknown section {name}")))
            .collect::<Result<_, _>>()?;
        let constructs = constructs
            .iter()
            .map(|(name, status)| {
                let status = parse_support(status)
                    .ok_or_else(|| format!("unknown construct status {status}"))?;
                Ok(ConstructCapability {
                    name: (*name).to_owned(),
                    status,
                })
            })
            .collect::<Result<_, String>>()?;
        Ok(Self {
            constructs,
            resolution_features: features.iter().map(|text| (*text).to_owned()).collect(),
            sections,
        })
    }
}

fn parse_support(text: &str) -> Option<ConstructSupport> {
    ConstructSupport::ALL
        .iter()
        .copied()
        .find(|support| support.as_str() == text)
}

impl Coverage {
    /// The coverage of a collection. It covers the full scope when there is no gap.
    pub fn of(
        (files_read, files_parsed): (usize, usize),
        selected_files: Vec<String>,
        gaps: Vec<Record<GapFact>>,
    ) -> Self {
        Self {
            files_parsed: files_parsed as u64,
            files_read: files_read as u64,
            full_scope: gaps.is_empty(),
            gaps,
            selected_files,
        }
    }
}

/// `collect.py`: SHA-256 of the compact JSON input listing, in the given order.
pub fn source_digest(inputs: &[Input]) -> String {
    let rows: Vec<String> = inputs
        .iter()
        .map(|input| {
            format!(
                "{{\"path\":{},\"digest\":{},\"role\":{}}}",
                Value::from(input.path.as_str()),
                Value::from(input.digest.as_str()),
                Value::from(input.role.as_str()),
            )
        })
        .collect();
    sha256_hex(format!("[{}]", rows.join(",")).as_bytes())
}
