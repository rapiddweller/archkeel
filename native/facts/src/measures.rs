// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The counts of the selected source file that a collector parsed.

use serde::{Deserialize, Serialize};

/// Counts of one source file. Each call belongs to exactly one call class.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileMeasures {
    /// The path of the file.
    pub file: String,
    /// The module of the file.
    pub module: crate::ids::ModuleName,
    /// All calls in the file.
    pub calls_total: u64,
    /// Calls with one proven target.
    pub calls_resolved: u64,
    /// Calls with a target that is only partly proven.
    pub calls_partial: u64,
    /// Calls of a builtin.
    pub calls_builtin: u64,
    /// Calls of a name outside the scan.
    pub calls_external: u64,
    /// Calls with no proven target.
    pub calls_unresolved: u64,
    /// Unresolved calls on `self`.
    pub unresolved_self: u64,
    /// Unresolved calls of an attribute.
    pub unresolved_attribute: u64,
    /// Unresolved calls of a plain name.
    pub unresolved_name: u64,
    /// Unresolved calls whose target is computed at run time.
    pub unresolved_dynamic: u64,
    /// The positions that a type annotation can fill.
    pub typing_positions: u64,
    /// Accesses to a private member that no type proves.
    pub untyped_private_accesses: u64,
}
