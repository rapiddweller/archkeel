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

/// Why a rule verdict is what it is, as a code of the Decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuleReason {
    /// The core evaluated the rule.
    Evaluated,
    /// The rule has violations.
    Violations,
    /// The scope of the run is not complete.
    ScopeIncomplete,
    /// No receipt proves the pass.
    NoReceipt,
    /// Some assessments are not decided.
    Undecided,
    /// The rule only declares.
    Declaration,
    /// A module with no owner blocks the rule.
    OwnershipBlocker,
}

/// What the run read and decided.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Run {
    /// The language of the scan.
    pub language: String,
    /// The source of the run.
    pub source: Source,
    /// The contract of the run.
    pub contract: Option<RunContract>,
    /// How much of the scope the scan read.
    pub coverage: Coverage,
    /// True when the contract has a target.
    pub target: bool,
    /// The status of the observation.
    pub observation: Status,
    /// The finding kinds that the report does not rank.
    pub not_ranked: Vec<NotRanked>,
    /// The relations that the report does not carry.
    pub not_carried: Vec<Code<Relation>>,
    /// The limit of the payload.
    pub payload_budget: PayloadBudget,
}

/// The source tree of the run.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    /// The commit that the tree is at.
    pub git_head: Option<String>,
    /// True when the tree has uncommitted changes.
    pub dirty: bool,
    /// The scan roots.
    pub scope: Vec<String>,
}

/// The contract of the run, as recorded.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunContract {
    /// The path.
    pub path: String,
    /// The digest of the contract file.
    pub digest: String,
    /// The schema version of the contract.
    pub schema_version: String,
}

/// The files of the run.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Coverage {
    /// How many files the scan found.
    pub files_discovered: u64,
    /// How many files the scan read.
    pub files_read: u64,
    /// How many files the scan parsed.
    pub files_parsed: u64,
}

/// A derived shape that is never ranked while its rule passes.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotRanked {
    /// The kind of the row.
    pub kind: String,
    /// How many.
    pub count: u64,
}

/// The byte budget of the payload.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PayloadBudget {
    /// The most bytes that the payload may have.
    pub max_bytes: u64,
}

/// What the host prints: the status and the counts.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Summary {
    /// The status of the run.
    pub status: Status,
    /// The counts of the run.
    pub counts: Counts,
}

/// The counts of the summary, in schema order.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Counts {
    /// How many packages.
    pub packages: u64,
    /// How many components.
    pub components: u64,
    /// How many modules the node holds.
    pub modules: u64,
    /// How many definitions the node holds.
    pub units: u64,
    /// How many edges between modules.
    pub module_edges: u64,
    /// How many edges between components.
    pub component_edges: u64,
    /// How many edges between packages.
    pub package_edges: u64,
    /// How many names cross a module edge.
    pub crossing_names: u64,
    /// How many crossing names have no bound definition.
    pub crossing_names_unbound: u64,
    /// How many edges the contract does not declare.
    pub undeclared_edges: u64,
    /// How many edges the contract forbids.
    pub forbidden_edges: u64,
    /// How many allowed edges no import uses.
    pub unused_edges: u64,
    /// How many cycles.
    pub cycles: u64,
    /// How many modules no component owns.
    pub unowned_modules: u64,
    /// How many ranked findings.
    pub findings_ranked: u64,
    /// How many findings of a declared kind.
    pub findings_declared: u64,
    /// How many findings that only give context.
    pub findings_context: u64,
    /// How many rules pass.
    pub rules_pass: u64,
    /// How many rules fail.
    pub rules_fail: u64,
    /// How many rules are unknown.
    pub rules_unknown: u64,
    /// How many rules only declare.
    pub rules_declaration: u64,
    /// How many violations.
    pub violations: u64,
    /// How many unknown records.
    pub unknowns: u64,
    /// How many assessments are not decided.
    pub undecided: u64,
    /// How many gaps.
    pub gaps: u64,
}

/// One rule row of the evaluator. Order: id.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleResult {
    /// The id of the rule.
    pub id: String,
    /// The kind of the row.
    pub kind: String,
    /// The short title.
    pub title: String,
    /// The verdict.
    pub verdict: RuleVerdict,
    /// True when the core evaluated the rule.
    pub evaluated: bool,
    /// How many violations.
    pub violations: u64,
    /// How many assessments are not decided.
    pub undecided: u64,
    /// Why.
    pub reason: RuleReason,
    /// Why it exists, as the contract states it.
    pub rationale: String,
    /// Who decided it.
    pub decided_by: Option<String>,
}

/// One gap that the payload references. Order: gap code.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GapRow {
    /// The gap.
    pub gap: Code<Gap>,
    /// How many items the gap blocks.
    pub blocks: u64,
}

/// The contract text of one component node. Order: node.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Component {
    /// The index of the node.
    pub node: u32,
    /// What the component is responsible for.
    pub does: Vec<String>,
    /// What the component must not do.
    pub never: Vec<String>,
    /// Who decided it.
    pub decided_by: Option<String>,
    /// Where it comes from.
    pub provenance: Vec<String>,
    /// The role of the component.
    pub role: Option<String>,
    /// The public names of the component.
    pub public_api: Option<Vec<String>>,
}

/// The system measures of one earlier commit.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TrendPoint {
    /// The commit of the point.
    pub commit: String,
    /// The date of the point.
    pub date: String,
    /// The measure that the point records.
    pub measure: Vec<Code<MeasureDef>>,
    /// The values of the point.
    pub value: Vec<i64>,
    /// The sizes that the values are part of.
    pub of: Vec<i64>,
}
