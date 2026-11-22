// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of a gap of the coverage or of the `unknowns` section. It has a file of its own, with
//! no macro call at module level, so the scan of the Rust collector places the type.

use crate::data::gap_effect::GapEffect;
use crate::data::trojan_horse::TrojanHorseSite;
use crate::ids::ModuleName;
use crate::reason::ReasonCode;
use crate::vocab::ResolutionDimension;

/// An UNKNOWN gap of the coverage or of the `unknowns` section.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GapData {
    /// The closed code of the reason.
    #[serde(skip)]
    pub code: Option<ReasonCode>,
    /// The gap is an unresolved dispatch to an internal module in a linked collector reply.
    #[serde(skip)]
    pub dispatch: bool,
    /// The live collector proves that this gap does not hide a written name route.
    #[serde(skip)]
    pub no_name_route: bool,
    /// The reason as written.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub reason: Option<String>,
    /// The module that the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub module: Option<ModuleName>,
    /// The dimension of the resolution that the collector does not prove.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub resolution_dimension: Option<ResolutionDimension>,
    /// The annotation that the collector does not read.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub annotation: Option<String>,
    /// The attribute that the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub attribute: Option<String>,
    /// The path of the file, relative to the root.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub file: Option<String>,
    /// The function that the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub function: Option<String>,
    /// The line of the place, counted from 1.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub line: Option<i64>,
    /// The message of the failure.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub message: Option<String>,
    /// The parameter that the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub parameter: Option<String>,
    /// The path that the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub path: Option<String>,
    /// The module whose import the gap is about.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_module: Option<ModuleName>,
    /// True when the import sits under `TYPE_CHECKING`.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub under_type_checking: Option<bool>,
    /// The facts that the gap leaves unknown (AD-564). A gap without an effect leaves the whole
    /// scope unknown.
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub effect: Option<GapEffect>,
    /// The trojan horse of the site, when the gap is a trojan horse whose reach a contract can declare
    /// (AD-664). A stored facts 11 file spells the key `door`; it reads as an alias (AD-1054).
    #[serde(default, alias = "door", skip_serializing_if = "crate::skip::omitted")]
    pub trojan_horse: Option<TrojanHorseSite>,
}
