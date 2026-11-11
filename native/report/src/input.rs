// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The inputs of `build`: the seam that the eval crate and the model slices fill (AD-371).
//!
//! `Outcome` is the Decision of the evaluator (AD-361 point 3): the status, the observation, each
//! rule with its `Decision`, reason and undecided positions, the Target and the diagnostics. A
//! PASS in it can only come from `Scope::pass` of the model (AD-363). `Records` holds the rows
//! that the model derives. A table that no slice produces yet is `Produced::NotProduced` with the
//! part that ports it, never an empty list.

use archkeel_model::{Decision, Unsupported};

use crate::codes::{
    Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, Measure, MeasureState, Permission,
    Reason, Verdict, Vis,
};
use crate::head::{Coverage, RuleReason, RunContract};

/// Rows of one table, or the named part that does not produce them yet.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Produced<T> {
    Rows(T),
    NotProduced(Unsupported),
}

/// Whether the run has a Target (explore has none, AD-285).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Target {
    Present,
    Absent,
}

/// The decision of one rule: a `Decision` of the model, or a permission declaration that does
/// not evaluate conformance.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RuleDecision {
    Decided(Decision),
    Declaration,
}

/// One position that the evaluator left undecided for a rule (AD-92).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Undecided {
    pub subject: String,
}

/// One rule of the outcome.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuleOutcome {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub decision: RuleDecision,
    /// True when the evaluator wrote a complete receipt for the rule (AD-117).
    pub evaluated: bool,
    pub reason: RuleReason,
    pub undecided: Vec<Undecided>,
    pub rationale: String,
    pub decided_by: Option<String>,
}

/// One diagnostic of the run: why a scan or a proof is incomplete.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    pub kind: String,
    /// The module, file or package that the diagnostic names; else the system.
    pub subject: String,
    pub claim: String,
}

/// The Decision of the evaluator for one run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    pub status: Decision,
    pub target: Target,
    /// The completeness verdict of the observation.
    pub observation: Decision,
    pub rules: Vec<RuleOutcome>,
    pub diagnostics: Vec<Diagnostic>,
}

/// What the run read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunFacts {
    pub language: String,
    pub git_head: Option<String>,
    pub dirty: bool,
    pub scope: Vec<String>,
    pub contract: Option<RunContract>,
    pub coverage: Coverage,
}

/// One node of the containment tree, in table order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NodeRow {
    pub level: Level,
    pub parent: Option<u32>,
    pub key: String,
    pub name: String,
    pub path: Option<String>,
    pub package: Option<u32>,
    pub modules: u64,
    pub units: u64,
    pub fan_in: u64,
    pub fan_out: u64,
}

/// The contract text of one component node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ComponentText {
    pub node: u32,
    pub does: Vec<String>,
    pub never: Vec<String>,
    pub decided_by: Option<String>,
    pub provenance: Vec<String>,
    pub role: Option<String>,
    pub public_api: Option<Vec<String>>,
}

/// The tree of the model (slice S1): nodes, component texts and the modules without an owner.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Tree {
    pub nodes: Vec<NodeRow>,
    pub components: Vec<ComponentText>,
    pub unowned_modules: u64,
}

/// One measure row (slice S10).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MeasureRow {
    pub node: u32,
    pub measure: Measure,
    pub state: MeasureState,
    pub value: Option<u64>,
    pub of: Option<u64>,
    pub gap: Option<Gap>,
    pub budget: Option<u64>,
    pub budget_source: Option<String>,
    pub baseline: Option<u64>,
    pub baseline_source: Option<String>,
    pub verdict: Verdict,
}

/// One unit with its enum variants.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnitRow {
    pub module: u32,
    pub name: String,
    pub kind: Kind,
    pub vis: Vis,
    pub line: u64,
    pub end_line: Option<u64>,
    pub parent: Option<u32>,
    pub decl: String,
    pub is_static: bool,
    pub variants: Vec<String>,
}

/// One name that crosses a module edge.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CrossingRow {
    pub name: String,
    pub kind: Kind,
    pub unit: Option<u32>,
    pub sites: u64,
    pub line: Option<u64>,
    pub reexport: bool,
}

/// One direct edge. `crossings` holds every crossing; the payload keeps the first 200.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EdgeRow {
    pub level: Level,
    pub from: u32,
    pub to: u32,
    pub names: u64,
    pub sites: u64,
    pub target: EdgeTarget,
    pub rationale: Option<String>,
    pub via: Vec<u32>,
    pub crossings: Vec<CrossingRow>,
}

/// The edges of the model (slices S2 and S3).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Graph {
    pub edges: Vec<EdgeRow>,
}

/// The permission of one ordered pair of sibling components.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PermissionRow {
    pub component: u32,
    pub target: u32,
    pub status: Permission,
    pub rule: Option<String>,
}

/// One violation record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ViolationRow {
    pub kind: String,
    pub rules: Vec<String>,
    pub subjects: Vec<String>,
    pub source_module: Option<String>,
    pub target_module: Option<String>,
    pub symbol: Option<String>,
    pub source_component: Option<u32>,
    pub target_component: Option<u32>,
    pub evidence: Vec<String>,
    pub path: Option<String>,
    pub line: Option<u64>,
    pub node: Option<u32>,
}

/// One record of the unknowns section or one coverage failure.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnknownRecord {
    pub kind: String,
    pub module: Option<String>,
    pub subjects: Vec<String>,
    pub rules: Vec<String>,
    pub title: String,
}

/// One finding with its carriers (name, importers, unit).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FindingRow {
    pub kind: FindingKind,
    pub subject: u32,
    pub value: u64,
    pub pool: Option<u64>,
    pub absolute: Option<u64>,
    pub relative_permille: Option<u64>,
    pub disposition: Disposition,
    pub reason: Reason,
    pub carrier_total: u64,
    pub gap: Option<Gap>,
    pub carriers: Vec<(String, u64, Option<u32>)>,
}

/// The rows of the model for one run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Records {
    pub run: RunFacts,
    pub tree: Produced<Tree>,
    pub measures: Produced<Vec<MeasureRow>>,
    pub units: Produced<Vec<UnitRow>>,
    /// Without a graph the payload names `imports` and `reexports` in `run.not_carried`.
    pub graph: Produced<Graph>,
    pub permissions: Produced<Vec<PermissionRow>>,
    pub violations: Produced<Vec<ViolationRow>>,
    pub unknowns: Produced<Vec<UnknownRecord>>,
    pub findings: Produced<Vec<FindingRow>>,
}
