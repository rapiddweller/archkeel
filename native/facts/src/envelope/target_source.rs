// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The source of a collector's selected target version.

/// The source of a collector's selected target version.
#[derive(
    Clone, Copy, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum TargetSource {
    /// The scan configuration selects the target.
    Config,
    /// The project requirement selects the target.
    Requirement,
    /// The collector uses its default target.
    Default,
    /// A legacy request supplies an interpreter description.
    Legacy,
}
