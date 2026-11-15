// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The counts of the selected source file that a collector parsed.

use serde::{Deserialize, Serialize};

/// Counts of one source file. Each call belongs to exactly one call class.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileMeasures {
    pub file: String,
    pub module: String,
    pub calls_total: u64,
    pub calls_resolved: u64,
    pub calls_partial: u64,
    pub calls_builtin: u64,
    pub calls_external: u64,
    pub calls_unresolved: u64,
    pub unresolved_self: u64,
    pub unresolved_attribute: u64,
    pub unresolved_name: u64,
    pub unresolved_dynamic: u64,
    pub typing_positions: u64,
    pub untyped_private_accesses: u64,
}
