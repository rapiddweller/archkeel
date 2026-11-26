// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reason code of an UNKNOWN rule row from the reason of the model (#1073 item 7, AD-381).
//!
//! Each match lists every variant and has no wildcard: a new reason of the model does not
//! compile here until its row reason is decided.
//!
//! - `undecided`: the rule left imports undecided, an undecided position of AD-92.
//! - `no_receipt`: the evaluator has no receipt for the rule: its kind is not ported, it selects
//!   no module, a dynamic import reaches it, or a cited child has no module record.
//! - `scope_incomplete`: each other reason. The scope of the run is not complete or not read.
//! - `ownership_blocker`: no reason of the model maps to it yet.
//! - `no_decided_rule`: a run-only cause; it cannot name a report rule row.
//!
//! The reference engine checks an incomplete observation before the receipt
//! (`ir/decisions.py:770-779`). So `Cause::NoRuleSubjects` (a rule side without subjects is a
//! coverage failure of the run) is `scope_incomplete`, and `Reason::NoSubjects` (this rule has
//! no receipt in a complete scope) is `no_receipt`. A dynamic import leaves the rule without its
//! receipt (AD-378), so it is `no_receipt`; `Cause::Undecided` is an undecided position. A receipt
//! that is not complete (`Cause::Receipt`, AD-384) is `no_receipt`; a pair gap that holds the rule
//! is `scope_incomplete`.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use std::collections::BTreeMap;

use archkeel_model::{Cause, Reason, Unsupported};
use serde::Serialize;

/// Why the evaluator left a rule UNKNOWN. The builder derives the reason of every other verdict
/// from the `Decision`: PASS is `evaluated`, FAIL `violations`, a declaration `declaration`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(crate) enum WhyUnknown {
    /// The scope of the run is not complete.
    ScopeIncomplete,
    /// No receipt proves the pass.
    NoReceipt,
    /// Some assessments are not decided.
    Undecided,
    /// A module with no owner blocks the rule.
    #[expect(dead_code, reason = "the frame schema reserves this reason")]
    OwnershipBlocker,
    /// No rule of the kind decides.
    NoDecidedRule,
}

impl WhyUnknown {
    /// The reason code of an UNKNOWN rule with this reason of the model.
    pub(crate) fn of(reason: &Reason) -> WhyUnknown {
        match reason {
            Reason::Unsupported(part) => unsupported(part),
            Reason::NotComplete(cause) => not_complete(cause),
            Reason::Interface(_) | Reason::Hygiene(_) => WhyUnknown::Undecided,
            // AD-470: the reference engine gives the UML target `no_receipt` without a complete
            // comparison, and the core has no comparison.
            Reason::NoSubjects | Reason::UncitedChild(_) | Reason::Uml(_) => WhyUnknown::NoReceipt,
            Reason::TooManyRows(_)
            | Reason::MissingInput(_)
            | Reason::Incomplete(_)
            | Reason::Refused(_) => WhyUnknown::ScopeIncomplete,
        }
    }
}

fn unsupported(part: &Unsupported) -> WhyUnknown {
    match part {
        Unsupported::NoRules => WhyUnknown::NoDecidedRule,
        Unsupported::Rule(_) | Unsupported::InsideRule => WhyUnknown::NoReceipt,
        Unsupported::ScopeProof(_)
        | Unsupported::Section(_)
        | Unsupported::Report
        | Unsupported::InsideTree
        | Unsupported::Baseline
        | Unsupported::TreeScope
        | Unsupported::Hygiene(_)
        | Unsupported::HygieneInput => WhyUnknown::ScopeIncomplete,
    }
}

fn not_complete(cause: &Cause) -> WhyUnknown {
    match cause {
        Cause::Undecided(_) => WhyUnknown::Undecided,
        Cause::DynamicImport | Cause::Receipt(_) | Cause::ClassSite(_) => WhyUnknown::NoReceipt,
        Cause::PairGaps(_)
        | Cause::AllowedPairGaps(_)
        | Cause::ScopedGaps(_)
        | Cause::WorkTree
        | Cause::Runtime
        | Cause::Producer
        | Cause::ProfileLimit(_)
        | Cause::LayerMetadata(_)
        | Cause::NoRuleSubjects(_)
        // A claim of a mount outside its parent is a coverage failure of the run (AD-385).
        | Cause::InsideSourceDomain(_)
        | Cause::OutsideNamespace(_)
        | Cause::DependencyScopeUnproven
        // A file whose owner has another component than its path (AD-468).
        | Cause::OwnedFileOwner(_) => WhyUnknown::ScopeIncomplete,
    }
}

/// What kind of gap holds a rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(crate) enum HoldKind {
    CoverageGaps,
    PairGaps,
    AllowedPairGaps,
    /// Gaps that state their effect, and the rule reads the effect (AD-564).
    ScopedGaps,
    UnknownImports,
    /// The imports of an `interface_boundary` rule that it could not decide (`interface`).
    InterfaceImports,
    NoSourceFiles,
    /// Any other cause: the text of `explained` names it.
    Other,
}

/// The pair of a gap between two modules.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Pair {
    pub(crate) source: String,
    pub(crate) target: String,
    /// Why the pair holds an interface rule; absent for the other rules.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) origin: Option<&'static str>,
}

/// The number of held pairs of one origin (an interface rule).
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct OriginCount {
    pub(crate) origin: &'static str,
    pub(crate) count: usize,
}

/// The gaps that hold one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct RuleHolds {
    pub(crate) cause: WhyUnknown,
    pub(crate) kind: HoldKind,
    /// The ids of the coverage gaps of the reply that hold the rule.
    pub(crate) gaps: Vec<String>,
    /// The first module pairs that hold the rule (a pair is two modules with a gap between them).
    pub(crate) pairs: Vec<Pair>,
    /// The number of module pairs that hold the rule. A pair can have several gap records. A
    /// rule that no pair holds counts gap ids. `pairs` and `gaps` keep at most `held_per_rule`.
    pub(crate) total: usize,
    /// True when `total` is larger than the lists that this frame keeps.
    pub(crate) truncated: bool,
    /// The imports that the collector could not resolve and that no gap names.
    pub(crate) unnamed_imports: usize,
    /// The number of held pairs of each origin, for an interface rule.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(crate) origins: Vec<OriginCount>,
    /// The held imports of an `interface_boundary` rule, each with its stated cause.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) interface: Option<InterfaceHolds>,
}

/// One coverage gap and the rules that it holds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct GapHolds {
    pub(crate) id: String,
    pub(crate) kind: String,
    pub(crate) reason: String,
    pub(crate) rules: Vec<String>,
    pub(crate) rules_total: usize,
    pub(crate) truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Holds {
    pub(crate) rules: BTreeMap<String, RuleHolds>,
    pub(crate) gaps: Vec<GapHolds>,
    /// The number of coverage gaps of the reply.
    pub(crate) gaps_total: usize,
    /// The number of coverage gaps that hold at least one rule.
    pub(crate) gaps_holding: usize,
    pub(crate) gaps_truncated: bool,
}

/// One held import.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct HeldImport {
    pub(crate) source: String,
    pub(crate) target: String,
    pub(crate) name: Option<String>,
    pub(crate) gap: &'static str,
    pub(crate) class: &'static str,
    /// The cause that the collector states; null when it states none.
    pub(crate) cause: Option<serde_json::Value>,
    pub(crate) evidence: Vec<String>,
}

/// The number of held imports of one gap and class.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct ClassCount {
    pub(crate) gap: &'static str,
    pub(crate) class: &'static str,
    pub(crate) count: usize,
}

/// What holds an `interface_boundary` rule: the count of each class and the first imports.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct InterfaceHolds {
    pub(crate) classes: Vec<ClassCount>,
    pub(crate) imports: Vec<HeldImport>,
}

/// One step of a cycle path.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Step {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub(crate) possible: bool,
    pub(crate) from: String,
    pub(crate) to: String,
    pub(crate) from_component: Option<String>,
    pub(crate) to_component: Option<String>,
    pub(crate) imports: usize,
    /// The declared edges of the step: the declaration, the module of its site and the module that
    /// it may load (AD-1057).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) declared: Vec<DeclaredEdge>,
    pub(crate) evidence: Vec<String>,
    pub(crate) evidence_total: usize,
}

/// One possible import that a declaration supplies to a cycle step.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct DeclaredEdge {
    pub(crate) declaration: String,
    pub(crate) source: String,
    pub(crate) target: String,
}

/// One cycle: its members and one closed path through them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct CyclePath {
    pub(crate) id: String,
    /// The position of the violation in `details` of the rule.
    pub(crate) index: usize,
    pub(crate) members: Vec<String>,
    pub(crate) path: Vec<Step>,
    pub(crate) steps_total: usize,
    pub(crate) truncated: bool,
}

/// The cycles of one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Cycles {
    pub(crate) total: usize,
    pub(crate) truncated: bool,
    pub(crate) items: Vec<CyclePath>,
}
