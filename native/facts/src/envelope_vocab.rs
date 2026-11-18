// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed words of the envelope: the protocol versions, the profile and the section names.

closed! {
    /// The protocol versions of a compressed reply.
    pub enum ProtocolVersion {
        /// Protocol 11: the facts carry the validation block (AD-688). The store reads no older
        /// reply; the 8.0.0, 9.0.0 and 10.0.0 replies had no block.
        V11 = "11.0.0",
    }
}

/// The source profile of a reply: the language analyzer that wrote it.
#[derive(
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Hash,
    serde::Serialize,
    serde::Deserialize,
    schemars::JsonSchema,
)]
pub enum Profile {
    /// The Python analyzer.
    #[serde(rename = "archkeel-python-analyzer")]
    Python,
    /// The Dart analyzer.
    #[serde(rename = "archkeel-dart-analyzer")]
    Dart,
    /// The TypeScript import reader.
    #[serde(rename = "archkeel-typescript-imports")]
    TypeScript,
    /// The Rust import reader.
    #[serde(rename = "archkeel-rust-imports")]
    Rust,
}

impl Profile {
    /// Each value, in the order of the declaration.
    pub const ALL: &'static [Self] = &[Self::Python, Self::Dart, Self::TypeScript, Self::Rust];

    /// The JSON text of the value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Python => "archkeel-python-analyzer",
            Self::Dart => "archkeel-dart-analyzer",
            Self::TypeScript => "archkeel-typescript-imports",
            Self::Rust => "archkeel-rust-imports",
        }
    }

    /// The value of a JSON text, or `None` when the vocabulary does not hold it.
    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "archkeel-python-analyzer" => Some(Self::Python),
            "archkeel-dart-analyzer" => Some(Self::Dart),
            "archkeel-typescript-imports" => Some(Self::TypeScript),
            "archkeel-rust-imports" => Some(Self::Rust),
            _ => None,
        }
    }
}

closed! {
    /// The name of a source section.
    pub enum SectionName {
        /// The symbols section.
        Symbols = "symbols",
        /// The imports section.
        Imports = "imports",
        /// The calls section.
        Calls = "calls",
        /// The references section.
        References = "references",
        /// The bindings section.
        Bindings = "bindings",
        /// The typing signals section.
        TypingSignals = "typing_signals",
        /// The constructs section.
        Constructs = "constructs",
        /// The gaps section.
        Unknowns = "unknowns",
    }
}

closed! {
    /// The role of a digested input.
    pub enum Role {
        /// A file that the scan selects.
        Selected = "selected",
        /// A file that only the resolution reads.
        Resolution = "resolution",
    }
}

impl Role {
    /// The role of a read, based on whether the scan selects its file.
    pub fn of_read(selected: bool) -> Self {
        if selected {
            Self::Selected
        } else {
            Self::Resolution
        }
    }
}

closed! {
    /// How completely the collector examines one construct kind.
    pub enum ConstructSupport {
        /// The collector reads the construct in full.
        Supported = "supported",
        /// The collector reads the construct in part.
        Partial = "partial",
        /// The collector does not read the construct.
        Unsupported = "unsupported",
        /// The collector decides the construct by its own rule.
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
        /// The project declares a valid requirement.
        Declared = "declared",
        /// The project has no metadata file.
        MetadataMissing = "metadata_missing",
        /// The metadata file is not valid.
        MetadataInvalid = "metadata_invalid",
        /// The metadata declares no requirement.
        RequirementMissing = "requirement_missing",
        /// The requirement is not valid.
        RequirementInvalid = "requirement_invalid",
    }
}
