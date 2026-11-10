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
    }
}

closed! {
    /// The source profile of a reply: the language analyzer that wrote it.
    pub enum Profile {
        Python = "archkeel-python-analyzer",
        Dart = "archkeel-dart-analyzer",
        TypeScript = "archkeel-typescript-imports",
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

object! {
    pub struct Adapter {
        pub name: String,
        pub version: String,
        pub code_digest: String,
    }
}

object! {
    pub struct Runtime {
        pub name: String,
        pub version: String,
        pub required: Option<String>,
        pub requirement_state: RequirementState,
    }
}

/// `dirty` is a Boolean, or the text `unknown` when the host could not read the work tree.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
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
        pub git_head: String,
        pub dirty: Dirty,
        pub source_digest: String,
        pub scope: Vec<String>,
    }
}

object! {
    pub struct Capabilities {
        pub sections: Vec<SectionName>,
        pub resolution_features: Vec<String>,
        pub constructs: Vec<ConstructCapability>,
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
        pub path: String,
        pub digest: String,
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
        pub selected_files: Vec<String>,
        pub files_read: u64,
        pub files_parsed: u64,
        pub full_scope: bool,
        pub gaps: Vec<Record<GapFact>>,
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

#[cfg(test)]
#[path = "envelope_tests.rs"]
mod tests;
