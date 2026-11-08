// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compressed reply of protocols 8.0.0 and 9.0.0: zlib level 1 over the plain JSON facts.

use std::io::Write;

use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Map, Value};

use crate::identity::sha256_hex;
use crate::protocol::Version;

/// The role of a digested input: a selected source file or a file that only decides resolution.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Selected,
    Resolution,
}

impl Role {
    pub fn as_str(self) -> &'static str {
        match self {
            Role::Selected => "selected",
            Role::Resolution => "resolution",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Input {
    pub path: String,
    pub digest: String,
    pub role: Role,
}

/// One observed module. The Python-shaped fields that TypeScript never sets are written empty.
#[derive(Clone, Debug, PartialEq)]
pub struct FileFact {
    pub id: String,
    pub rel_path: String,
    pub module: String,
    pub package: String,
    pub blank: bool,
    pub evidence_id: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Evidence {
    pub id: String,
    pub file: String,
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub excerpt: String,
}

/// One source record. `subjects` and `evidence_ids` must be sorted, as `classified` sorts them.
#[derive(Clone, Debug, PartialEq)]
pub struct Record {
    pub id: String,
    pub evidence_class: &'static str,
    pub area: &'static str,
    pub kind: &'static str,
    pub title: String,
    pub subjects: Vec<String>,
    pub evidence_ids: Vec<String>,
    pub data: Map<String, Value>,
}

/// What an import resolves to (`facts.ImportTarget`).
#[derive(Clone, Debug, PartialEq)]
pub enum Target {
    Local {
        import_id: String,
        module: String,
        file: String,
        runtime_file: Option<String>,
        declaration_file: Option<String>,
    },
    External {
        import_id: String,
        package: String,
    },
    Builtin {
        import_id: String,
        name: String,
    },
    Unresolved {
        import_id: String,
        specifier: String,
        reason: String,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct Provenance {
    pub profile: &'static str,
    pub adapter_version: String,
    pub code_digest: String,
    pub runtime_name: &'static str,
    pub runtime_version: String,
    pub runtime_required: String,
}

/// The facts of one collection, in the order the reply writes them.
#[derive(Clone, Debug, PartialEq)]
pub struct Facts {
    pub provenance: Provenance,
    pub git_head: String,
    pub dirty: Value,
    pub scope: Vec<String>,
    pub sections: Vec<(&'static str, Vec<Record>)>,
    pub features: Vec<&'static str>,
    pub inputs: Vec<Input>,
    pub files: Vec<FileFact>,
    /// The resolved target of each import record, in the order of the walk.
    pub imports: Vec<Target>,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    /// Coverage gaps. The collection is complete only when there is none.
    pub gaps: Vec<Record>,
    pub evidence: Vec<Evidence>,
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

/// Encode the reply for `version`; 8.0.0 and 9.0.0 share one compressed shape.
pub fn encode(version: Version, facts: &Facts) -> Result<Vec<u8>, String> {
    if version == Version::V3 {
        return Err("a native collector writes only the compressed reply".to_owned());
    }
    let reply = json!({
        "protocol_version": version.as_str(),
        "provider_sources": [],
        "facts": facts_value(facts),
    });
    let plain = serde_json::to_vec(&reply).map_err(|error| error.to_string())?;
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::new(1));
    encoder
        .write_all(&plain)
        .and_then(|()| encoder.finish())
        .map_err(|error| format!("cannot compress the reply: {error}"))
}

fn facts_value(facts: &Facts) -> Value {
    let provenance = &facts.provenance;
    json!({
        "profile": provenance.profile,
        "adapter": {
            "name": provenance.profile,
            "version": provenance.adapter_version,
            "code_digest": provenance.code_digest,
        },
        "runtime": {
            "name": provenance.runtime_name,
            "version": provenance.runtime_version,
            "required": provenance.runtime_required,
            "requirement_state": "declared",
        },
        "source": {
            "git_head": facts.git_head,
            "dirty": facts.dirty,
            "source_digest": source_digest(&facts.inputs),
            "scope": facts.scope,
        },
        "capabilities": {
            "sections": facts.sections.iter().map(|(name, _)| *name).collect::<Vec<_>>(),
            "resolution_features": facts.features,
            "constructs": [],
        },
        "inputs": facts.inputs.iter().map(|input| json!({
            "path": input.path, "digest": input.digest, "role": input.role.as_str(),
        })).collect::<Vec<_>>(),
        "files": facts.files.iter().map(file_value).collect::<Vec<_>>(),
        "imports": facts.imports.iter().map(target_value).collect::<Vec<_>>(),
        "sections": facts.sections.iter().map(|(name, records)| json!({
            "name": name, "records": records.iter().map(record_value).collect::<Vec<_>>(),
        })).collect::<Vec<_>>(),
        "coverage": {
            "selected_files": facts.selected_files,
            "files_read": facts.files_read,
            "files_parsed": facts.files.len(),
            "full_scope": facts.gaps.is_empty(),
            "gaps": facts.gaps.iter().map(record_value).collect::<Vec<_>>(),
        },
        "evidence": facts.evidence.iter().map(evidence_value).collect::<Vec<_>>(),
        "uncertain_reexports": [],
        "type_shapes": [],
        "state": {"classes": [], "functions": []},
        "candidate_evidence": [],
        "provider_bindings": [],
    })
}

fn target_value(target: &Target) -> Value {
    match target {
        Target::Local {
            import_id,
            module,
            file,
            runtime_file,
            declaration_file,
        } => json!({
            "kind": "local", "import_id": import_id, "module": module, "file": file,
            "runtime_file": runtime_file, "declaration_file": declaration_file,
        }),
        Target::External { import_id, package } => {
            json!({"kind": "external", "import_id": import_id, "package": package})
        }
        Target::Builtin { import_id, name } => {
            json!({"kind": "builtin", "import_id": import_id, "name": name})
        }
        Target::Unresolved {
            import_id,
            specifier,
            reason,
        } => json!({
            "kind": "unresolved", "import_id": import_id, "specifier": specifier, "reason": reason,
        }),
    }
}

fn file_value(file: &FileFact) -> Value {
    json!({
        "id": file.id,
        "rel_path": file.rel_path,
        "module": file.module,
        "package": file.package,
        "all_exports": [],
        "all_literal": false,
        "compatibility_logic_free": false,
        "stable_bindings": [],
        "blank": file.blank,
        "evidence_id": file.evidence_id,
    })
}

fn record_value(record: &Record) -> Value {
    json!({
        "id": record.id,
        "evidence_class": record.evidence_class,
        "area": record.area,
        "kind": record.kind,
        "title": record.title,
        "subjects": record.subjects,
        "evidence_ids": record.evidence_ids,
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": record.data,
    })
}

fn evidence_value(evidence: &Evidence) -> Value {
    json!({
        "id": evidence.id,
        "file": evidence.file,
        "line": evidence.line,
        "end_line": evidence.end_line,
        "column": evidence.column,
        "excerpt": evidence.excerpt,
    })
}

#[cfg(test)]
#[path = "reply_tests.rs"]
mod tests;
