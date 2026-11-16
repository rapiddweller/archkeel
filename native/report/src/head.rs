// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status and rule verdict of the engine frame.

use serde::{Deserialize, Serialize};

/// The status of a run or of its observation: the three verdicts of the Decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
pub enum Status {
    /// Every rule passes.
    #[serde(rename = "PASS")]
    Pass,
    /// At least one rule fails.
    #[serde(rename = "FAIL")]
    Fail,
    /// At least one rule is unknown and none fails.
    #[serde(rename = "UNKNOWN")]
    Unknown,
}

/// The encoded verdict of one rule row. It is the wire form only: a built report writes it from
/// a `Decision` of the model, and a decoded report holds it as read bytes (AD-363 point 4).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
pub enum RuleVerdict {
    /// The rule holds.
    #[serde(rename = "PASS")]
    Pass,
    /// The rule is broken.
    #[serde(rename = "FAIL")]
    Fail,
    /// The facts do not decide the rule.
    #[serde(rename = "UNKNOWN")]
    Unknown,
    /// The rule only declares and has no verdict.
    #[serde(rename = "DECLARATION")]
    Declaration,
}
