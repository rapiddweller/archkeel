// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The version and the budgets of the `explain` part of the frame (AD-484): each list is cut at
//! its budget, and the schema states the budgets so that the shell keeps no copy.

use serde::Serialize;

pub(super) const VERSION: u8 = 1;
/// The most cycles that one rule lists.
pub(super) const MAX_CYCLES: usize = 50;
/// The most steps that one path lists.
pub(super) const MAX_STEPS: usize = 64;
/// The most evidence ids that one step lists.
pub(super) const MAX_EVIDENCE: usize = 5;
/// The most gaps and pairs that one rule lists.
pub(super) const MAX_HELD: usize = 20;
/// The most rules that one gap lists.
pub(super) const MAX_RULES: usize = 200;
/// The most gaps that the part lists.
pub(super) const MAX_GAPS: usize = 500;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(super) struct Budgets {
    pub(super) cycles_per_rule: usize,
    pub(super) path_steps: usize,
    pub(super) evidence_per_step: usize,
    pub(super) held_per_rule: usize,
    pub(super) rules_per_gap: usize,
    pub(super) gaps: usize,
}

/// The schema of the budgets: each field is a constant, the value of `BUDGETS`. The shell reads
/// the limits from the schema and keeps no copy of them.
pub(super) fn budgets_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
    let values = serde_json::to_value(BUDGETS).unwrap_or_default();
    let fields: serde_json::Map<String, serde_json::Value> = values
        .as_object()
        .into_iter()
        .flatten()
        .map(|(name, value)| (name.clone(), serde_json::json!({"const": value})))
        .collect();
    let required: Vec<&String> = fields.keys().collect();
    schemars::json_schema!({
        "type": "object",
        "properties": fields,
        "required": required,
        "additionalProperties": false,
    })
}

/// The schema of the version of the part: the constant `VERSION`.
pub(super) fn version_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
    schemars::json_schema!({"const": VERSION})
}

pub(super) const BUDGETS: Budgets = Budgets {
    cycles_per_rule: MAX_CYCLES,
    path_steps: MAX_STEPS,
    evidence_per_step: MAX_EVIDENCE,
    held_per_rule: MAX_HELD,
    rules_per_gap: MAX_RULES,
    gaps: MAX_GAPS,
};
