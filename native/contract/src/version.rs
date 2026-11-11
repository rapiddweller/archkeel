// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract schema versions and the version where each feature starts
//! (`ir/contract_version.py`).

use serde::{Deserialize, Serialize};

use crate::words::{spelling, value_of};

/// A contract schema version. The order of the variants is the order of contract evolution.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum ContractVersion {
    #[serde(rename = "2.1.0")]
    V2_1,
    #[serde(rename = "2.2.0")]
    V2_2,
    #[serde(rename = "2.3.0")]
    V2_3,
    #[serde(rename = "2.4.0")]
    V2_4,
    #[serde(rename = "3.0.0")]
    V3_0,
    #[serde(rename = "3.1.0")]
    V3_1,
    #[serde(rename = "3.2.0")]
    V3_2,
    #[serde(rename = "3.3.0")]
    V3_3,
    #[serde(rename = "3.4.0")]
    V3_4,
    #[serde(rename = "3.5.0")]
    V3_5,
    #[serde(rename = "3.6.0")]
    V3_6,
    #[serde(rename = "3.7.0")]
    V3_7,
    #[serde(rename = "3.8.0")]
    V3_8,
    #[serde(rename = "3.9.0")]
    V3_9,
    #[serde(rename = "3.10.0")]
    V3_10,
    #[serde(rename = "3.11.0")]
    V3_11,
    #[serde(rename = "3.12.0")]
    V3_12,
    #[serde(rename = "3.13.0")]
    V3_13,
    #[serde(rename = "3.14.0")]
    V3_14,
}

/// The version of its spelling, or `None` for an unknown spelling.
pub(crate) fn version_of(text: &str) -> Option<ContractVersion> {
    value_of(text)
}

/// The spelling of a version, as the contract writes it.
pub fn version_text(version: ContractVersion) -> String {
    spelling(&version)
}

/// A contract feature that the parser checks against the declared version.
#[derive(Clone, Copy)]
pub(crate) enum Feature {
    Layers,
    PlannedComponentOwner,
    ModuleSelectors,
    ImportNamespaces,
    ModuleObjectGrants,
    CallOwner,
    BoundedNumericOperand,
    ProtocolDeclarations,
    ForbiddenCallArgument,
    ConstructSelector,
    SourceOwnership,
    GuardedEffect,
    Catalog,
}

/// The first version that holds the feature (`_FEATURE_START`).
fn start(feature: Feature) -> ContractVersion {
    match feature {
        Feature::Layers => ContractVersion::V2_3,
        Feature::PlannedComponentOwner => ContractVersion::V2_4,
        Feature::ModuleSelectors => ContractVersion::V3_4,
        Feature::ImportNamespaces => ContractVersion::V3_5,
        Feature::ModuleObjectGrants => ContractVersion::V3_6,
        Feature::CallOwner => ContractVersion::V3_7,
        Feature::BoundedNumericOperand => ContractVersion::V3_8,
        Feature::ProtocolDeclarations => ContractVersion::V3_9,
        Feature::ForbiddenCallArgument => ContractVersion::V3_10,
        Feature::ConstructSelector => ContractVersion::V3_11,
        Feature::SourceOwnership => ContractVersion::V3_12,
        Feature::GuardedEffect => ContractVersion::V3_13,
        Feature::Catalog => ContractVersion::V3_14,
    }
}

/// `supports_feature`: read and write use the same rule.
pub(crate) fn supports(version: ContractVersion, feature: Feature) -> bool {
    version >= start(feature)
}
