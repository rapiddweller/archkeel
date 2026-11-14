// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The envelope of a protocol 8 or 9 reply: every part of `facts` outside the sections (AD-346).
//!
//! Each object is closed: an unknown key is a decode error, as in the Python decoder
//! (`facts_codec._source_facts`). The parts that only the Python collector fills (`state`,
//! `type_shapes`, `uncertain_reexports`, `candidate_evidence`, `provider_bindings` and
//! `provider_sources`) are `NoEntries`: a reply with an entry in one of them is a decode error,
//! because no reader of these types exists yet. A value is never dropped without a check.

use std::fmt;

use serde::de::{self, SeqAccess, Visitor};
use serde::ser::SerializeSeq;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

use serde_json::Value;

use crate::identity::sha256_hex;
use crate::ids::{EvidenceId, FactId, ModuleName, PackageName};
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

closed! {
    /// The protocol versions of a compressed reply.
    pub enum ProtocolVersion {
        V8 = "8.0.0",
        V9 = "9.0.0",
        V10 = "10.0.0",
    }
}

closed! {
    /// The source profile of a reply: the language analyzer that wrote it.
    pub enum Profile {
        Python = "archkeel-python-analyzer",
        Dart = "archkeel-dart-analyzer",
        TypeScript = "archkeel-typescript-imports",
        Rust = "archkeel-rust-imports",
    }
}

/// How the modules of a profile lie in the scan roots (`ir/profiles.py`
/// `project_import_closure` and `source_suffix`, `ir/coverage.py` `_package_paths`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layout {
    /// The collector proves the import closure of the project, and the directory of a package
    /// is the parent directory of a file of a direct module (the parent rule).
    ProjectFiles,
    /// The reference engine maps the files of the profile by another rule, or proves no closure.
    Other,
}

/// What the host does with a gap between two modules that the contract allows
/// (`check/pair_gaps.py:66` `drop_allowed_pair_gaps`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PairGapDrop {
    /// The host drops such a gap before the evaluation.
    Allowed,
    /// The host keeps every pair gap.
    Never,
}

/// How the rules read the target of an import (`evaluate.py` `evaluate_source`, AD-372, AD-450).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TargetMarks {
    /// An external package target matches a dependency by its package, and a builtin target is
    /// no dependency.
    Typed,
    /// Each resolved target matches a dependency by the scope of its target module, as the
    /// reference engine reads a Python import.
    ByModule,
}

impl Profile {
    /// How the rules read the import targets of this profile.
    pub fn target_marks(self) -> TargetMarks {
        match self {
            Profile::TypeScript | Profile::Rust => TargetMarks::Typed,
            Profile::Python | Profile::Dart => TargetMarks::ByModule,
        }
    }

    /// What the host does with an allowed pair gap of this profile.
    pub fn pair_gap_drop(self) -> PairGapDrop {
        match self {
            Profile::Rust => PairGapDrop::Allowed,
            Profile::TypeScript | Profile::Python | Profile::Dart => PairGapDrop::Never,
        }
    }

    /// The language name that a UML target entity gives for a fact of this profile (AD-494).
    pub fn language(self) -> &'static str {
        match self {
            Profile::Python => "python",
            Profile::Dart => "dart",
            Profile::TypeScript => "typescript",
            Profile::Rust => "rust",
        }
    }

    /// How the modules of this profile lie in the scan roots. A Python module that is not its
    /// path below a scan root is a gap of the survey, so the parent rule holds (AD-450). A Dart
    /// module is the namespace and the path below its scan root (AD-468).
    pub fn layout(self) -> Layout {
        match self {
            Profile::TypeScript | Profile::Rust | Profile::Python | Profile::Dart => {
                Layout::ProjectFiles
            }
        }
    }
}

closed! {
    /// The name of a source section.
    pub enum SectionName {
        Symbols = "symbols",
        Imports = "imports",
        Calls = "calls",
        References = "references",
        Bindings = "bindings",
        TypingSignals = "typing_signals",
        Constructs = "constructs",
        Unknowns = "unknowns",
    }
}

closed! {
    /// The role of a digested input.
    pub enum Role {
        Selected = "selected",
        Resolution = "resolution",
    }
}

closed! {
    /// How completely the collector examines one construct kind.
    pub enum ConstructSupport {
        Supported = "supported",
        Partial = "partial",
        Unsupported = "unsupported",
        Decided = "decided",
    }
}

impl Profile {
    /// Whether the collector of this profile emits nominal construct selectors.
    pub fn construct_selectors(self) -> bool {
        matches!(self, Self::Python)
    }
}

closed! {
    /// The state of the runtime requirement of the collector.
    pub enum RequirementState {
        Declared = "declared",
        MetadataMissing = "metadata_missing",
        MetadataInvalid = "metadata_invalid",
        RequirementMissing = "requirement_missing",
        RequirementInvalid = "requirement_invalid",
    }
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
    pub struct Reply {
        pub protocol_version: ProtocolVersion,
        pub provider_sources: NoEntries,
        pub facts: Facts,
    }
}

object! {
    pub struct Facts {
        pub profile: Profile,
        /// The linked collector's scope statements. Wire replies carry no live authority.
        #[serde(skip)]
        pub profile_limits: Option<ProfileLimits>,
        /// The linked collector's files that belong to another module (AD-468). Wire replies
        /// carry none.
        #[serde(skip)]
        pub owned_files: Vec<OwnedFile>,
        pub adapter: Adapter,
        pub runtime: Runtime,
        pub source: Source,
        pub capabilities: Capabilities,
        pub inputs: Vec<Input>,
        pub files: Vec<FileFact>,
        pub imports: Vec<Target>,
        pub sections: Vec<Section>,
        pub coverage: Coverage,
        pub evidence: Vec<Evidence>,
        pub uncertain_reexports: NoEntries,
        pub type_shapes: NoEntries,
        pub state: State,
        pub candidate_evidence: NoEntries,
        pub provider_bindings: NoEntries,
    }
}

/// A selected file that has no module of its own: its facts belong to the module `owner`.
/// `module` is the module that its path would name. The model checks that one component claims
/// both names; else no rule can rely on the owner (AD-468).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OwnedFile {
    pub rel_path: String,
    pub module: ModuleName,
    pub owner: ModuleName,
}

/// Whether a documented profile limit applies to this collection.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LimitSupport {
    Supported,
    Unsupported,
}

/// The profile differences that the linked collector can state for its own reply.
/// These statements never replace coverage gaps or a rule's scope proof.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProfileLimits {
    pub dependency_symbols: LimitSupport,
    pub interface_boundary: LimitSupport,
}

// The keys of the objects below are in sorted order, as the Python reply has them (`sort_keys`).
// The serde form writes them in the order of the declaration, so the compressed reply of a native
// collector writes these types as they are. The order of `Facts` does not matter: the stream
// writes its keys one by one.
object! {
    pub struct Adapter {
        pub code_digest: String,
        pub name: String,
        pub version: String,
    }
}

object! {
    pub struct Runtime {
        pub name: String,
        pub required: Option<String>,
        pub requirement_state: RequirementState,
        pub version: String,
    }
}

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
    Known(bool),
    Unknown(UnknownDirty),
}

closed! {
    pub enum UnknownDirty {
        Unknown = "unknown",
    }
}

object! {
    pub struct Source {
        pub dirty: Dirty,
        pub git_head: String,
        pub scope: Vec<String>,
        pub source_digest: String,
    }
}

object! {
    pub struct Capabilities {
        pub constructs: Vec<ConstructCapability>,
        pub resolution_features: Vec<String>,
        pub sections: Vec<SectionName>,
    }
}

object! {
    pub struct ConstructCapability {
        pub name: String,
        pub status: ConstructSupport,
    }
}

object! {
    pub struct Input {
        pub digest: String,
        pub path: String,
        pub role: Role,
    }
}

object! {
    pub struct FileFact {
        pub id: FactId,
        pub rel_path: String,
        pub module: ModuleName,
        pub package: PackageName,
        pub all_exports: Vec<String>,
        pub all_literal: bool,
        pub compatibility_logic_free: bool,
        pub stable_bindings: Vec<String>,
        pub blank: bool,
        pub evidence_id: EvidenceId,
    }
}

/// The typed resolution of one import. `import_id` is the id of its import record.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Target {
    Local {
        import_id: FactId,
        module: ModuleName,
        file: String,
        runtime_file: Option<String>,
        declaration_file: Option<String>,
    },
    External {
        import_id: FactId,
        package: PackageName,
    },
    Builtin {
        import_id: FactId,
        name: String,
    },
    Unresolved {
        import_id: FactId,
        specifier: String,
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

object! {
    pub struct Coverage {
        pub files_parsed: u64,
        pub files_read: u64,
        pub full_scope: bool,
        pub gaps: Vec<Record<GapFact>>,
        pub selected_files: Vec<String>,
    }
}

object! {
    pub struct Evidence {
        pub id: EvidenceId,
        pub file: String,
        pub line: i64,
        pub end_line: i64,
        pub column: i64,
        pub excerpt: String,
    }
}

/// The state facts of the Python collector. Only an empty state is read yet.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct State {
    pub classes: NoEntries,
    pub functions: NoEntries,
}

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

// The constructors of the envelope types; a child module that uses this one, never the reverse.
#[path = "envelope_build.rs"]
mod build;

#[cfg(test)]
#[path = "envelope_tests.rs"]
mod tests;
