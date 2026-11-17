// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence carried by a class-placement violation (AD-728).

/// A class whose source location violates a placement rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlacedClass {
    /// The violation id.
    pub id: String,
    /// The rule id.
    pub rule: String,
    /// The class fact cited by this violation.
    pub fact_id: String,
    /// The qualified name.
    pub name: String,
    /// The defining module.
    pub module: String,
    /// The proven kind.
    pub kind: String,
    /// The source evidence.
    pub evidence: Vec<String>,
}
