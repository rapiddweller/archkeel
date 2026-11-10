// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The ids and names of the facts. Each one is a newtype over its text.
//!
//! The types have no conversion between them. A source id (`FactId`, `EvidenceId`) never becomes
//! the Target id of a contract: the two meet only in a match by a rule (WP1, section 3). The Target
//! id type comes with the model crate that reads the contract.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

macro_rules! text_id {
    ($(#[$doc:meta])* $name:ident) => {
        $(#[$doc])*
        #[derive(
            Clone, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
            JsonSchema,
        )]
        #[serde(transparent)]
        pub struct $name(String);

        impl $name {
            pub fn new(text: impl Into<String>) -> Self {
                Self(text.into())
            }

            pub fn as_str(&self) -> &str {
                &self.0
            }
        }
    };
}

text_id!(
    /// The id of a source record (`PREFIX-` and 16 hex digits, `identity::stable_id`).
    FactId
);
text_id!(
    /// The id of one cited source location (`EVD-…`, `identity::evidence_id`).
    EvidenceId
);
text_id!(
    /// A module identity: a dotted name (Python, Dart) or `identity::module_identity` (TypeScript).
    ModuleName
);
text_id!(
    /// The package of a module, or the package of an external dependency.
    PackageName
);
