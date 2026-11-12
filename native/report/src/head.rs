// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The head of the payload: run, summary, rules, gaps, components and trend (AD-361).
//!
//! The field order of each struct is the canonical key order of the schema (`required`). The
//! host prints the summary from this head and from the node 0 rows of `measures`.

use serde::{Deserialize, Serialize};

use crate::codes::{Code, Gap, MeasureDef, Relation};

/// The status of a run or of its observation: the three verdicts of the Decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Status {
    #[serde(rename = "PASS")]
    Pass,
    #[serde(rename = "FAIL")]
    Fail,
    #[serde(rename = "UNKNOWN")]
    Unknown,
}

/// The encoded verdict of one rule row. It is the wire form only: a built report writes it from
/// a `Decision` of the model, and a decoded report holds it as read bytes (AD-363 point 4).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuleVerdict {
    #[serde(rename = "PASS")]
    Pass,
    #[serde(rename = "FAIL")]
    Fail,
    #[serde(rename = "UNKNOWN")]
    Unknown,
    #[serde(rename = "DECLARATION")]
    Declaration,
}

/// Why a rule verdict is what it is, as a code of the Decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuleReason {
    Evaluated,
    Violations,
    ScopeIncomplete,
    NoReceipt,
    Undecided,
    Declaration,
    OwnershipBlocker,
}

/// What the run read and decided.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Run {
    pub language: String,
    pub source: Source,
    pub contract: Option<RunContract>,
    pub coverage: Coverage,
    pub target: bool,
    pub observation: Status,
    pub not_ranked: Vec<NotRanked>,
    pub not_carried: Vec<Code<Relation>>,
    pub payload_budget: PayloadBudget,
}

/// The source tree of the run.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub git_head: Option<String>,
    pub dirty: bool,
    pub scope: Vec<String>,
}

/// The contract of the run, as recorded.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunContract {
    pub path: String,
    pub digest: String,
    pub schema_version: String,
}

/// The files of the run.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Coverage {
    pub files_discovered: u64,
    pub files_read: u64,
    pub files_parsed: u64,
}

/// A derived shape that is never ranked while its rule passes.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotRanked {
    pub kind: String,
    pub count: u64,
}

/// The byte budget of the payload.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PayloadBudget {
    pub max_bytes: u64,
}

/// What the host prints: the status and the counts.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Summary {
    pub status: Status,
    pub counts: Counts,
}

/// The counts of the summary, in schema order.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Counts {
    pub packages: u64,
    pub components: u64,
    pub modules: u64,
    pub units: u64,
    pub module_edges: u64,
    pub component_edges: u64,
    pub package_edges: u64,
    pub crossing_names: u64,
    pub crossing_names_unbound: u64,
    pub undeclared_edges: u64,
    pub forbidden_edges: u64,
    pub unused_edges: u64,
    pub cycles: u64,
    pub unowned_modules: u64,
    pub findings_ranked: u64,
    pub findings_declared: u64,
    pub findings_context: u64,
    pub rules_pass: u64,
    pub rules_fail: u64,
    pub rules_unknown: u64,
    pub rules_declaration: u64,
    pub violations: u64,
    pub unknowns: u64,
    pub undecided: u64,
    pub gaps: u64,
}

/// One rule row of the evaluator. Order: id.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleResult {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub verdict: RuleVerdict,
    pub evaluated: bool,
    pub violations: u64,
    pub undecided: u64,
    pub reason: RuleReason,
    pub rationale: String,
    pub decided_by: Option<String>,
}

/// One gap that the payload references. Order: gap code.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GapRow {
    pub gap: Code<Gap>,
    pub blocks: u64,
}

/// The contract text of one component node. Order: node.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Component {
    pub node: u32,
    pub does: Vec<String>,
    pub never: Vec<String>,
    pub decided_by: Option<String>,
    pub provenance: Vec<String>,
    pub role: Option<String>,
    pub public_api: Option<Vec<String>>,
}

/// The system measures of one earlier commit.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrendPoint {
    pub commit: String,
    pub date: String,
    pub measure: Vec<Code<MeasureDef>>,
    pub value: Vec<i64>,
    pub of: Vec<i64>,
}
