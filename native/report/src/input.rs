// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The inputs of `build`: the seam that the eval crate and the model slices fill (AD-371).
//!
//! `RunOutcome` is the Decision of the evaluator (AD-361 point 3): each rule with its
//! `Decision`, reason and undecided positions, the Target and the diagnostics. A PASS in it can
//! only come from an `Outcome` of the evaluator (AD-363, AD-381). `Records` holds the rows
//! that the model derives. A table that no slice produces yet is `Produced::NotProduced` with the
//! part that ports it, never an empty list.

use archkeel_contract::RuleKind;
use archkeel_eval::Outcome;
use archkeel_model::{Decision, Model, Unsupported, Verdict as ModelVerdict};

use crate::codes::{
    BudgetVerdict, Disposition, EdgeTarget, FindingKind, FindingReason, Gap, Kind, MeasureDef,
    MeasureState, NodeLevel, Permission, Vis,
};
use crate::head::{Coverage, RunContract};
use crate::why::WhyUnknown;

/// Rows of one table, or the named part that does not produce them yet.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Produced<T> {
    /// The rows that the core produced.
    Rows(T),
    /// The reason that the core did not produce the rows.
    NotProduced(Unsupported),
}

/// Whether the run has a Target (explore has none, AD-285).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Target {
    /// The contract has a target.
    Present,
    /// The contract has no target.
    Absent,
}

/// The decision of one rule: a `Decision` of the evaluator, or a permission declaration that
/// does not evaluate conformance. Only this crate makes one (AD-381).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum RuleDecision {
    Decided(Decision),
    Declaration,
}

/// One position that the evaluator left undecided for a rule (AD-92).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Undecided {
    /// What the finding is about.
    pub subject: String,
}

/// The text of one rule row: what the contract says and what the evaluator saw. No field holds
/// a verdict.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuleText {
    /// The short title.
    pub title: String,
    /// Why it exists, as the contract states it.
    pub rationale: String,
    /// Who decided it.
    pub decided_by: Option<String>,
    /// True when the evaluator wrote a complete receipt for the rule (AD-117).
    pub evaluated: bool,
    /// How many assessments are not decided.
    pub undecided: Vec<Undecided>,
}

/// One rule of the outcome. The fields are private (AD-381): the id and the decision come
/// together from an `Outcome` of the evaluator, and `build` checks each PASS against the model
/// and the rule (`Decision::passes`). No caller can put a PASS of rule A into the row of rule B.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuleOutcome {
    pub(crate) id: String,
    pub(crate) kind: String,
    pub(crate) title: String,
    pub(crate) decision: RuleDecision,
    pub(crate) evaluated: bool,
    /// Set for an UNKNOWN rule only; any other verdict with it is `BuildError::ReasonMismatch`.
    pub(crate) why_unknown: Option<WhyUnknown>,
    pub(crate) undecided: Vec<Undecided>,
    pub(crate) rationale: String,
    pub(crate) decided_by: Option<String>,
}

impl RuleOutcome {
    /// The row of a rule that the evaluator decided: its id, kind and decision come from the
    /// outcome, and an UNKNOWN takes its `WhyUnknown` from the reason of the decision.
    pub fn evaluated(outcome: &Outcome, text: RuleText) -> RuleOutcome {
        let (decision, why_unknown) = match outcome.decision() {
            Some(decision) => {
                let why = match decision.verdict() {
                    ModelVerdict::Unknown => decision.reason().map(WhyUnknown::of),
                    ModelVerdict::Pass(_) | ModelVerdict::Fail => None,
                };
                (RuleDecision::Decided(decision.clone()), why)
            }
            // A permission declaration: `build` checks that the model declares it (AD-381).
            None => (RuleDecision::Declaration, None),
        };
        RuleOutcome::of(
            outcome.rule().to_owned(),
            crate::kind::word(outcome.kind()).to_owned(),
            decision,
            why_unknown,
            text,
        )
    }

    /// The row of a permission declaration: it does not evaluate conformance. `None` unless
    /// `id` is a declaration rule of the contract of `model`, so a FAIL rule cannot be shown
    /// as DECLARATION (AD-381).
    pub fn declaration(model: &Model, id: String, text: RuleText) -> Option<RuleOutcome> {
        let kind = crate::kind::word(RuleKind::AllowedDependency).to_owned();
        model
            .declares(&id)
            .then(|| RuleOutcome::of(id, kind, RuleDecision::Declaration, None, text))
    }

    pub(crate) fn of(
        id: String,
        kind: String,
        decision: RuleDecision,
        why_unknown: Option<WhyUnknown>,
        text: RuleText,
    ) -> RuleOutcome {
        RuleOutcome {
            id,
            kind,
            title: text.title,
            decision,
            evaluated: text.evaluated,
            why_unknown,
            undecided: text.undecided,
            rationale: text.rationale,
            decided_by: text.decided_by,
        }
    }

    /// The rule id.
    pub fn id(&self) -> &str {
        &self.id
    }
}

/// One diagnostic of the run: why a scan or a proof is incomplete.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    /// The kind of the row.
    pub kind: String,
    /// The module, file or package that the diagnostic names; else the system.
    pub subject: String,
    /// The claim that the diagnostic makes.
    pub claim: String,
}

/// The Decision of the evaluator for one run. It has no status and no observation verdict:
/// `build` takes the status from the rows (`status_of`), the observation from the scope of the
/// model (`Scope::run`), and asks the model for the run proof only when the status is PASS.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunOutcome {
    /// True when the contract has a target.
    pub target: Target,
    /// The outcomes of the rules.
    pub rules: Vec<RuleOutcome>,
    /// The diagnostics of the run.
    pub diagnostics: Vec<Diagnostic>,
}

/// What the run read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunFacts {
    /// The language of the scan.
    pub language: String,
    /// The commit that the tree is at.
    pub git_head: Option<String>,
    /// True when the tree has uncommitted changes.
    pub dirty: bool,
    /// The scan roots.
    pub scope: Vec<String>,
    /// The contract of the run.
    pub contract: Option<RunContract>,
    /// How much of the scope the scan read.
    pub coverage: Coverage,
}

/// One node of the containment tree, in table order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NodeRow {
    /// The level of the node or the edge.
    pub level: NodeLevel,
    /// The index of the parent.
    pub parent: Option<u32>,
    /// The key of the node.
    pub key: String,
    /// The name as written.
    pub name: String,
    /// The path.
    pub path: Option<String>,
    /// The index of the package node.
    pub package: Option<u32>,
    /// How many modules the node holds.
    pub modules: u64,
    /// How many definitions the node holds.
    pub units: u64,
    /// How many nodes import this one.
    pub fan_in: u64,
    /// How many nodes this one imports.
    pub fan_out: u64,
}

/// The contract text of one component node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ComponentText {
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

/// The tree of the model (slice S1): nodes, component texts and the modules without an owner.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Tree {
    /// The nodes.
    pub nodes: Vec<NodeRow>,
    /// How many components.
    pub components: Vec<ComponentText>,
    /// How many modules no component owns.
    pub unowned_modules: u64,
}

/// One measure row (slice S10).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MeasureRow {
    /// The index of the node.
    pub node: u32,
    /// The measure that the point records.
    pub measure: MeasureDef,
    /// The state of the measure.
    pub state: MeasureState,
    /// The values of the point.
    pub value: Option<u64>,
    /// The size that the value is part of.
    pub of: Option<u64>,
    /// The gap.
    pub gap: Option<Gap>,
    /// The budget.
    pub budget: Option<u64>,
    /// Where the budget comes from.
    pub budget_source: Option<String>,
    /// The baseline value.
    pub baseline: Option<u64>,
    /// Where the baseline comes from.
    pub baseline_source: Option<String>,
    /// The verdict.
    pub verdict: BudgetVerdict,
}

/// One unit with its enum variants.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnitRow {
    /// The module.
    pub module: u32,
    /// The name as written.
    pub name: String,
    /// The kind of the row.
    pub kind: Kind,
    /// The visibility.
    pub vis: Vis,
    /// The line, counted from 1.
    pub line: u64,
    /// The last line.
    pub end_line: Option<u64>,
    /// The index of the parent.
    pub parent: Option<u32>,
    /// The declaration as written.
    pub decl: String,
    /// True when the definition is static.
    pub is_static: bool,
    /// The variants of the enum.
    pub variants: Vec<String>,
}

/// One name that crosses a module edge.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CrossingRow {
    /// The name as written.
    pub name: String,
    /// The kind of the row.
    pub kind: Kind,
    /// The index of the definition.
    pub unit: Option<u32>,
    /// How many sites use it.
    pub sites: u64,
    /// The line, counted from 1.
    pub line: Option<u64>,
    /// True when the name is published again.
    pub reexport: bool,
}

/// One direct edge. `crossings` holds every crossing; the payload keeps the first 200.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EdgeRow {
    /// The level of the node or the edge.
    pub level: NodeLevel,
    /// The node where the edge starts.
    pub from: u32,
    /// The node where the edge ends.
    pub to: u32,
    /// How many names cross.
    pub names: u64,
    /// How many sites use it.
    pub sites: u64,
    /// True when the contract has a target.
    pub target: EdgeTarget,
    /// Why it exists, as the contract states it.
    pub rationale: Option<String>,
    /// The indexes of the nodes that the edge passes through.
    pub via: Vec<u32>,
    /// The names that cross the edge.
    pub crossings: Vec<CrossingRow>,
}

/// The edges of the model (slices S2 and S3).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GraphRows {
    /// The edges.
    pub edges: Vec<EdgeRow>,
}

/// The permission of one ordered pair of sibling components.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PermissionRow {
    /// The index of the component.
    pub component: u32,
    /// True when the contract has a target.
    pub target: u32,
    /// The status.
    pub status: Permission,
    /// The id of the rule.
    pub rule: Option<String>,
}

/// One violation record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ViolationRow {
    /// The kind of the row.
    pub kind: String,
    /// The outcomes of the rules.
    pub rules: Vec<String>,
    /// The subjects of the rules.
    pub subjects: Vec<String>,
    /// The module that holds the import.
    pub source_module: Option<String>,
    /// The module that the import reaches.
    pub target_module: Option<String>,
    /// The imported name.
    pub symbol: Option<String>,
    /// The component of the importing module.
    pub source_component: Option<u32>,
    /// The component of the imported module.
    pub target_component: Option<u32>,
    /// The evidence rows of the record.
    pub evidence: Vec<String>,
    /// The path.
    pub path: Option<String>,
    /// The line, counted from 1.
    pub line: Option<u64>,
    /// The index of the node.
    pub node: Option<u32>,
}

/// One record of the unknowns section or one coverage failure.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnknownRecord {
    /// The kind of the row.
    pub kind: String,
    /// The module.
    pub module: Option<String>,
    /// The subjects of the rules.
    pub subjects: Vec<String>,
    /// The outcomes of the rules.
    pub rules: Vec<String>,
    /// The short title.
    pub title: String,
}

/// One finding with its carriers (name, importers, unit).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FindingRow {
    /// The kind of the row.
    pub kind: FindingKind,
    /// What the finding is about.
    pub subject: u32,
    /// The values of the point.
    pub value: u64,
    /// The size of the pool that the finding is ranked in.
    pub pool: Option<u64>,
    /// The absolute value.
    pub absolute: Option<u64>,
    /// The share of the pool, in parts per thousand.
    pub relative_permille: Option<u64>,
    /// How the finding is shown.
    pub disposition: Disposition,
    /// Why.
    pub reason: FindingReason,
    /// The total of the names that carry the finding.
    pub carrier_total: u64,
    /// The gap.
    pub gap: Option<Gap>,
    /// The names that carry the finding: name, importers and unit.
    pub carriers: Vec<(String, u64, Option<u32>)>,
}

/// The rows of the model for one run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Records {
    /// The facts of the run.
    pub run: RunFacts,
    /// The containment tree.
    pub tree: Produced<Tree>,
    /// The measure rows.
    pub measures: Produced<Vec<MeasureRow>>,
    /// How many definitions the node holds.
    pub units: Produced<Vec<UnitRow>>,
    /// Without a graph the payload names `imports` and `reexports` in `run.not_carried`.
    pub graph: Produced<GraphRows>,
    /// The permission rows.
    pub permissions: Produced<Vec<PermissionRow>>,
    /// How many violations.
    pub violations: Produced<Vec<ViolationRow>>,
    /// How many unknown records.
    pub unknowns: Produced<Vec<UnknownRecord>>,
    /// The finding rows.
    pub findings: Produced<Vec<FindingRow>>,
}
