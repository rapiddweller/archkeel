// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The validation block of a protocol 11 reply (AD-688): what the store checks of the reply beyond
//! its language-free minimum, stated by the collector from its own table.
//!
//! The block can only add checks. The store keeps its minimum for each reply: a feature that a
//! registered set names must be a feature that the store can check, and the standard library is a
//! pinned table of this crate that the block only names by its owner key. A reply that a block
//! would let through below that minimum is refused (`archkeel-store`).

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::envelope_vocab::{ConstructSupport, Profile, SectionName};

/// What the store checks of one reply beyond its language-free minimum.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Validation {
    /// The capability sets that the collector registers. The sections, the resolution features
    /// and the construct capabilities of the reply are exactly one of them.
    pub registered: Vec<Registered>,
    /// What an interface statement of the collector needs (`profile_limits`).
    pub interface: InterfaceNeed,
    /// The owner key of the pinned standard library of the reply (`STANDARD_LIBRARY`): the
    /// profile, or the profile and the minor version of its target after `@`. The part before `@`
    /// is also the owner of the SDK libraries (`SDK_LIBRARIES`).
    pub standard_library: String,
}

/// What an interface statement of a collector needs. Each value but `Nothing` adds a check.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum InterfaceNeed {
    /// The statement needs nothing of the reply.
    Nothing,
    /// The collector makes no interface statement.
    Unsupported,
    /// The statement holds exactly when the reply states this resolution feature.
    Feature(String),
}

/// One registered capability set: the sections and the features that a reply must state, the
/// ones that it may state in addition, and its construct capabilities in order.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Registered {
    /// The sections that the reply must hold.
    pub sections: Vec<SectionName>,
    /// The sections that the reply may hold in addition.
    pub optional_sections: Vec<SectionName>,
    /// The resolution features that the reply must state.
    pub features: Vec<String>,
    /// The resolution features that the reply may state in addition.
    pub optional_features: Vec<String>,
    /// The construct capabilities of the reply, in order: each name with the statuses it may have.
    pub constructs: Vec<RegisteredConstruct>,
}

/// One construct capability of a registered set: its name and the statuses that it may state.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RegisteredConstruct {
    /// The name of the construct kind.
    pub name: String,
    /// The statuses that the reply may state for it.
    pub statuses: Vec<ConstructSupport>,
}

impl Registered {
    /// A set with the required sections and features and no optional part or construct.
    pub fn of(sections: &[SectionName], features: &[&str]) -> Self {
        Self {
            sections: sections.to_vec(),
            optional_sections: Vec::new(),
            features: features.iter().map(|name| (*name).to_owned()).collect(),
            optional_features: Vec::new(),
            constructs: Vec::new(),
        }
    }

    /// The set with these optional sections in addition.
    pub fn with_optional_sections(mut self, sections: &[SectionName]) -> Self {
        self.optional_sections = sections.to_vec();
        self
    }

    /// The set with these optional features in addition.
    pub fn with_optional_features(mut self, features: &[&str]) -> Self {
        self.optional_features = features.iter().map(|name| (*name).to_owned()).collect();
        self
    }

    /// The set with one more construct capability, after the ones that it has.
    pub fn with_construct(mut self, name: &str, statuses: &[ConstructSupport]) -> Self {
        self.constructs.push(RegisteredConstruct {
            name: name.to_owned(),
            statuses: statuses.to_vec(),
        });
        self
    }

    /// Each feature that the set names, required or optional.
    pub fn named_features(&self) -> impl Iterator<Item = &str> {
        self.features
            .iter()
            .chain(&self.optional_features)
            .map(String::as_str)
    }
}

/// The owner of the SDK libraries and of the version lists of a standard library key: the part
/// before `@`.
pub fn library_family(key: &str) -> &str {
    key.split('@').next().unwrap_or(key)
}

/// The owner key of a version list: `owner@major.minor` of `version` (`3.12.1` gives `@3.12`).
/// A version without two parts gives a key that no list has, so the store finds no table.
pub fn versioned_owner(owner: &str, version: &str) -> String {
    let mut parts = version.split('.');
    let (major, minor) = (parts.next().unwrap_or(""), parts.next().unwrap_or(""));
    format!("{owner}@{major}.{minor}")
}

/// The owner key of the standard library of a reply: the key of its block, or for a reply of
/// protocol 8, 9 or 10 without a block the key of its profile, with the minor version of the
/// runtime for Python (the reader of the transition, AD-688).
pub fn library_key(block: Option<&Validation>, profile: Profile, runtime_version: &str) -> String {
    match block {
        Some(validation) => validation.standard_library.clone(),
        None if profile == Profile::Python => versioned_owner(profile.as_str(), runtime_version),
        None => profile.as_str().to_owned(),
    }
}
