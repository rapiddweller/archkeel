// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The identity of the producer of a reply (owner decision 1 of issue #880).
//!
//! Only a bundled producer with a recorded code digest can give PASS. An external collector
//! (`collector_argv`) gives at most UNKNOWN. Protocol 9 writes the name, the version and the digest
//! in `facts.adapter`; the origin is decided by the host. Protocol 10 carries this type.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

closed! {
    /// Where the producer comes from.
    pub enum Origin {
        /// Shipped in the Archkeel wheel and pinned by its code digest.
        Bundled = "bundled",
        /// Configured by the user. Its verdicts are capped at UNKNOWN.
        External = "external",
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Producer {
    /// The adapter name, for example `archkeel-typescript-imports`.
    pub name: String,
    pub version: String,
    /// SHA-256 of the producer code (`code_digest`).
    pub code_digest: String,
    pub origin: Origin,
}
