// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply shapes that a collector builds and the snapshot reader fills: the input and its role,
//! the file fact, the evidence, the import target and the provenance, with their JSON writers.

use serde_json::{json, Value};

use crate::identity::{evidence_id, package_of, sha256_hex, stable_id, Part};

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

impl FileFact {
    /// The file fact of a module: the id and the package come from the module identity.
    pub fn of((rel_path, module): (&str, &str), blank: bool, evidence_id: String) -> Self {
        Self {
            id: stable_id("FILE", &[Part::Text(module)]),
            rel_path: rel_path.to_owned(),
            module: module.to_owned(),
            package: package_of(module).to_owned(),
            blank,
            evidence_id,
        }
    }
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

impl Evidence {
    /// The evidence of one source location, with the text of its first line.
    pub fn at(file: &str, line: i64, end_line: i64, column: i64, excerpt: &str) -> Self {
        Self {
            id: evidence_id(file, line, end_line, column),
            file: file.to_owned(),
            line,
            end_line,
            column,
            excerpt: excerpt.to_owned(),
        }
    }
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

impl Target {
    /// The id of the import record that this target belongs to.
    pub fn import_id(&self) -> &str {
        match self {
            Target::Local { import_id, .. }
            | Target::External { import_id, .. }
            | Target::Builtin { import_id, .. }
            | Target::Unresolved { import_id, .. } => import_id,
        }
    }

    /// The same target for another import record.
    pub fn with_import_id(&self, id: &str) -> Self {
        let mut copy = self.clone();
        match &mut copy {
            Target::Local { import_id, .. }
            | Target::External { import_id, .. }
            | Target::Builtin { import_id, .. }
            | Target::Unresolved { import_id, .. } => *import_id = id.to_owned(),
        }
        copy
    }
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

impl Provenance {
    /// The provenance of a native collector that is written in Rust. The build script gives the
    /// version, the digest and the compiler; `rust_version` is the minimum of the crate.
    pub fn native(
        profile: &'static str,
        (adapter_version, code_digest): (&str, &str),
        (runtime_version, rust_version): (&str, &str),
    ) -> Self {
        Self {
            profile,
            adapter_version: adapter_version.to_owned(),
            code_digest: code_digest.to_owned(),
            runtime_name: "rust",
            runtime_version: runtime_version.to_owned(),
            runtime_required: format!(">={rust_version}"),
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

pub fn target_value(target: &Target) -> Value {
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

pub fn file_value(file: &FileFact) -> Value {
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

pub fn evidence_value(evidence: &Evidence) -> Value {
    json!({
        "id": evidence.id,
        "file": evidence.file,
        "line": evidence.line,
        "end_line": evidence.end_line,
        "column": evidence.column,
        "excerpt": evidence.excerpt,
    })
}
