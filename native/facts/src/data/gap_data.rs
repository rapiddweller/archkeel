// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of a gap of the coverage or of the `unknowns` section. It has a file of its own, with
//! no macro call at module level, so the scan of the Rust collector places the type.

use crate::data::gap_effect::GapEffect;
use crate::ids::ModuleName;
use crate::reason::ReasonCode;
use crate::vocab::ResolutionDimension;

/// An UNKNOWN gap of the coverage or of the `unknowns` section.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GapData {
    #[serde(skip)]
    pub code: Option<ReasonCode>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub module: Option<ModuleName>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub resolution_dimension: Option<ResolutionDimension>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub annotation: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub attribute: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub file: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub function: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub line: Option<i64>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub message: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub parameter: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub path: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_module: Option<ModuleName>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub under_type_checking: Option<bool>,
    /// The facts that the gap leaves unknown (AD-564). A gap without an effect leaves the whole
    /// scope unknown.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub effect: Option<GapEffect>,
}
