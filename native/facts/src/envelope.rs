// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The envelope of a protocol 11 reply: every part of `facts` outside the sections (AD-346).
//!
//! Each object is closed: an unknown key is a decode error, as in the Python decoder
//! (`facts_codec._source_facts`). The parts that only the Python collector fills (`state`,
//! `type_shapes`, `uncertain_reexports`, `candidate_evidence`, `provider_bindings` and
//! `provider_sources`) are `NoEntries`: a reply with an entry in one of them is a decode error,
//! because no reader of these types exists yet. A value is never dropped without a check.

pub use crate::envelope_vocab::{
    ConstructSupport, Profile, ProtocolVersion, RequirementState, Role, SectionName,
};

use std::fmt;

use serde::de::{self, SeqAccess, Visitor};
use serde::ser::SerializeSeq;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::Value;

use crate::identity::sha256_hex;
use crate::ids::{EvidenceId, FactId, ModuleName, PackageName};
use crate::measures::FileMeasures;
use crate::record::Record;
use crate::sections::{GapFact, Section};

/// A closed object of the envelope: an unknown key is a decode error.
macro_rules! object {
    ($(#[$doc:meta])* pub struct $name:ident { $($(#[$attr:meta])* pub $field:ident: $ty:ty,)* }) => {
        $(#[$doc])*
        #[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name {
            $($(#[$attr])* pub $field: $ty,)*
        }
    };
}

/// A list that must be empty. Its field is a part of the reply that no reader types yet.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct NoEntries;

impl Serialize for NoEntries {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_seq(Some(0))?.end()
    }
}

impl<'de> Deserialize<'de> for NoEntries {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Empty;
        impl<'de> Visitor<'de> for Empty {
            type Value = NoEntries;
            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("an empty list")
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<NoEntries, A::Error> {
                match seq.next_element::<de::IgnoredAny>()? {
                    None => Ok(NoEntries),
                    Some(_) => Err(de::Error::custom("the store does not read this part yet")),
                }
            }
        }
        deserializer.deserialize_seq(Empty)
    }
}

object! {
    /// One reply of a collector.
    pub struct Reply {
        /// The protocol version of the reply.
        pub protocol_version: ProtocolVersion,
        /// Reserved; always empty.
        pub provider_sources: NoEntries,
        /// The facts of the reply.
        pub facts: Facts,
    }
}

object! {
    /// The facts of a reply.
    pub struct Facts {
        /// The profile of the analyzer.
        pub profile: Profile,
        /// The checks beyond the store's minimum, from the table of the collector (AD-688).
        pub validation: Validation,
        /// The linked collector's scope statements. Wire replies carry no live authority.
        #[serde(skip)]
        pub profile_limits: Option<ProfileLimits>,
        /// The linked collector's one stated assumption of its proofs, shown with the verdict
        /// (AD-540). It is no proof and replaces no gap. Wire replies carry none.
        #[serde(skip)]
        pub scope_premise: Option<&'static str>,
        /// The linked collector's files that belong to another module (AD-468). Wire replies
        /// carry none.
        #[serde(skip)]
        pub owned_files: Vec<OwnedFile>,
        /// The adapter that wrote the reply.
        pub adapter: Adapter,
        /// The runtime that ran the adapter.
        pub runtime: Runtime,
        /// The source that the reply covers.
        pub source: Source,
        /// What the collector reads.
        pub capabilities: Capabilities,
        /// The inputs that the scan digests.
        pub inputs: Vec<Input>,
        /// The facts of the files.
        pub files: Vec<FileFact>,
        /// The resolved targets of the imports.
        pub imports: Vec<Target>,
        /// The sections with their records.
        pub sections: Vec<Section>,
        /// How much of the scope the collection read.
        pub coverage: Coverage,
        /// The evidence records that the facts cite.
        pub evidence: Vec<Evidence>,
        /// Reserved; always empty.
        pub uncertain_reexports: NoEntries,
        /// Reserved; always empty.
        pub type_shapes: NoEntries,
        /// Reserved state of the Python collector.
        pub state: State,
        /// Reserved; always empty.
        pub candidate_evidence: NoEntries,
        /// Reserved; always empty.
        pub provider_bindings: NoEntries,
    }
}

/// A selected file that has no module of its own: its facts belong to the module `owner`.
/// `module` is the module that its path would name. The model checks that one component claims
/// both names; else no rule can rely on the owner (AD-468).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OwnedFile {
    /// The path of the file, relative to the root.
    pub rel_path: String,
    /// The module that holds it.
    pub module: ModuleName,
    /// The module that owns the facts of the file.
    pub owner: ModuleName,
}

/// Whether a documented profile limit applies to this collection.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LimitSupport {
    /// The collector supports it.
    Supported,
    /// The collector does not support it.
    Unsupported,
}

/// The profile differences that the linked collector can state for its own reply.
/// These statements never replace coverage gaps or a rule's scope proof.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProfileLimits {
    /// Whether the profile reads the imported names of a dependency.
    pub dependency_symbols: LimitSupport,
    /// Whether the profile reads the types of an interface.
    pub interface_boundary: LimitSupport,
}

// The keys of the objects below are in sorted order, as the Python reply has them (`sort_keys`).
// The serde form writes them in the order of the declaration, so the compressed reply of a native
// collector writes these types as they are. The order of `Facts` does not matter: the stream
// writes its keys one by one.
object! {
    /// The adapter that wrote the reply.
    pub struct Adapter {
        /// The digest of the code of the adapter.
        pub code_digest: String,
        /// The name as written.
        pub name: String,
        /// The version of the adapter.
        pub version: String,
    }
}

/// The runtime that made the reply: its name, version and requirement.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Runtime {
    /// The name as written.
    pub name: String,
    /// The version requirement that the project declares for the runtime.
    pub required: Option<String>,
    /// Whether the requirement is declared and valid.
    pub requirement_state: RequirementState,
    /// The version of the runtime that ran.
    pub version: String,
    /// How the collector selected its target, when this runtime is a target.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_source: Option<TargetSource>,
    /// The collector's display text for the selected target.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_description: Option<String>,
}

mod target_source;
pub use target_source::TargetSource;
pub mod validation;
pub use validation::Validation;

/// The one runtime whose reply the host accepts a dependency scope proof from
/// (`ir/decisions.py` `_native_scope_runtime_valid`).
const SCOPE_PROOF_RUNTIME: &str = "python";

impl Runtime {
    /// True when the host can accept a dependency scope proof of `complete_requires` from a
    /// reply of this runtime (`_native_scope_runtime_valid`, AD-418). The host checks more; a
    /// `false` here is enough to say that it accepts none.
    pub fn carries_scope_proof(&self) -> bool {
        self.name == SCOPE_PROOF_RUNTIME
    }
}

/// `dirty` is a Boolean, or the text `unknown` when the host could not read the work tree.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(untagged)]
pub enum Dirty {
    /// Whether the tree has uncommitted changes.
    Known(bool),
    /// The tool could not tell.
    Unknown(UnknownDirty),
}

closed! {
    /// The value of `dirty` when the tool cannot tell.
    pub enum UnknownDirty {
        /// The tool could not tell whether the tree is dirty.
        Unknown = "unknown",
    }
}

/// The source that the reply covers: commit, dirty state, scope and digest.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    /// Whether the tree has uncommitted changes.
    pub dirty: Dirty,
    /// The commit that the tree is at.
    pub git_head: String,
    /// The scan roots that the reply covers.
    pub scope: Vec<String>,
    /// The digest of the inputs of the reply.
    pub source_digest: String,
}

/// What the collector declares that it can read.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Capabilities {
    /// The construct kinds that the collector reads, with their support.
    pub constructs: Vec<ConstructCapability>,
    /// The resolution features that the collector declares.
    pub resolution_features: Vec<String>,
    /// The sections that the reply holds.
    pub sections: Vec<SectionName>,
}

object! {
    /// The support of one construct kind.
    pub struct ConstructCapability {
        /// The name as written.
        pub name: String,
        /// How completely the collector reads the construct.
        pub status: ConstructSupport,
    }
}

object! {
    /// One input that the scan digests.
    pub struct Input {
        /// The digest of the content.
        pub digest: String,
        /// The path of the input.
        pub path: String,
        /// The role of the input.
        pub role: Role,
    }
}

/// The facts of one source file.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileFact {
    /// The id of the record.
    pub id: FactId,
    /// The path of the file, relative to the root.
    pub rel_path: String,
    /// The module that holds it.
    pub module: ModuleName,
    /// The package that holds the file.
    pub package: PackageName,
    /// The names that `__all__` lists, in order.
    pub all_exports: Vec<String>,
    /// True when `__all__` is a plain list that the collector reads in full.
    pub all_literal: bool,
    /// True when the file has no version or platform branch that changes its imports.
    pub compatibility_logic_free: bool,
    /// The names that one plain statement binds and nothing rebinds.
    pub stable_bindings: Vec<String>,
    /// True when the file has no code.
    pub blank: bool,
    /// A proof that the file has no class declarations; absence is not such a proof.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub class_inventory_empty: Option<bool>,
    /// The evidence record of the file.
    pub evidence_id: EvidenceId,
}

/// The typed resolution of one import. `import_id` is the id of its import record.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Target {
    /// An import of a module that the scan holds.
    Local {
        /// The id of the import record that the target resolves.
        import_id: FactId,
        /// The module that holds it.
        module: ModuleName,
        /// The path of the file of the module.
        file: String,
        /// The file that the module runs from, when it differs from the declaration.
        runtime_file: Option<String>,
        /// The file that declares the types of the module.
        declaration_file: Option<String>,
    },
    /// An import of an installed package.
    External {
        /// The id of the import record that the target resolves.
        import_id: FactId,
        /// The package that the import reaches.
        package: PackageName,
    },
    /// An import of a builtin module.
    Builtin {
        /// The id of the import record that the target resolves.
        import_id: FactId,
        /// The name as written.
        name: String,
    },
    /// An import that no rule resolves.
    Unresolved {
        /// The id of the import record that the target resolves.
        import_id: FactId,
        /// The text of the import as written.
        specifier: String,
        /// Why the collector does not prove it.
        reason: String,
    },
}

impl Target {
    /// The same target for another import record.
    pub fn with_import_id(&self, id: &str) -> Self {
        let mut copy = self.clone();
        match &mut copy {
            Target::Local { import_id, .. }
            | Target::External { import_id, .. }
            | Target::Builtin { import_id, .. }
            | Target::Unresolved { import_id, .. } => *import_id = FactId::new(id),
        }
        copy
    }

    /// The id of the import record that this target belongs to.
    pub fn import_id(&self) -> &FactId {
        match self {
            Target::Local { import_id, .. }
            | Target::External { import_id, .. }
            | Target::Builtin { import_id, .. }
            | Target::Unresolved { import_id, .. } => import_id,
        }
    }
}

/// How much of the scope the collection read, and its gaps.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Coverage {
    /// How many files the collector parsed.
    pub files_parsed: u64,
    /// How many files the collector read.
    pub files_read: u64,
    /// True when the collection covers the whole scope.
    pub full_scope: bool,
    /// The gaps that keep the scope from being complete.
    pub gaps: Vec<Record<GapFact>>,
    /// The per-file counts, when the request asks for them.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub measures: Option<Vec<FileMeasures>>,
    /// The paths of the files that the scan selected.
    pub selected_files: Vec<String>,
}

/// One place in a source file that a fact cites.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Evidence {
    /// The id of the evidence record.
    pub id: EvidenceId,
    /// The path of the file, relative to the root.
    pub file: String,
    /// The line of the place, counted from 1.
    pub line: i64,
    /// The last line of the place.
    pub end_line: i64,
    /// The column of the place.
    pub column: i64,
    /// The text at the place.
    pub excerpt: String,
}

/// The state facts of the Python collector. Only an empty state is read yet.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct State {
    /// Reserved for classes that only the Python collector writes; always empty.
    pub classes: NoEntries,
    /// Reserved for functions that only the Python collector writes; always empty.
    pub functions: NoEntries,
}

/// The producer of a collector reply: its profile, its adapter and its runtime.
#[derive(Clone, Debug, PartialEq)]
pub struct Provenance {
    /// The profile of the analyzer.
    pub profile: Profile,
    /// The adapter that wrote the reply.
    pub adapter: Adapter,
    /// The runtime that ran the adapter.
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
                target_source: None,
                target_description: None,
            },
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

#[path = "envelope_cycle.rs"]
pub mod cycle;

// The constructors of the envelope types; a child module that uses this one, never the reverse.
#[path = "envelope_build.rs"]
mod build;

#[cfg(test)]
#[path = "envelope_tests.rs"]
mod tests;

#[path = "envelope_features.rs"]
mod features;
pub use features::test_features;
