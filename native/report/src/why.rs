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

use std::collections::BTreeSet;

use archkeel_facts::vocab::RouteWithheld;
use archkeel_model::{
    Cause, Incomplete, InterfaceGap, InterfaceHold, PairOrigin, Reason, Unsupported,
};
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

/// What the reason of one rule says about the gaps that hold it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Held {
    pub(crate) cause: WhyUnknown,
    pub(crate) kind: HoldKind,
    pub(crate) pairs: Vec<(String, String, Option<PairOrigin>)>,
    /// The ids of the gaps that the reason itself names (AD-564).
    pub(crate) ids: Vec<String>,
    pub(crate) unnamed_imports: usize,
    pub(crate) interface: Option<InterfaceHolds>,
    pub(crate) imports_total: usize,
}

impl Held {
    /// The kind of hold that a reason states, with the pairs, the gap ids and the unnamed
    /// imports that it names.
    pub(crate) fn of(reason: &Reason) -> Held {
        let mut held = Held {
            cause: WhyUnknown::of(reason),
            kind: HoldKind::Other,
            pairs: Vec::new(),
            ids: Vec::new(),
            unnamed_imports: 0,
            interface: None,
            imports_total: 0,
        };
        if let Reason::Interface(hold) = reason {
            held.kind = HoldKind::InterfaceImports;
            held.interface = Some(InterfaceHolds::of(hold));
            held.imports_total = hold.total();
        }
        if let Reason::Incomplete(incomplete) = reason {
            held.kind = match incomplete {
                Incomplete::CoverageGaps { .. } => HoldKind::CoverageGaps,
                Incomplete::UnknownImports(count) => {
                    held.unnamed_imports = *count;
                    HoldKind::UnknownImports
                }
                Incomplete::NoSourceFiles => HoldKind::NoSourceFiles,
            };
        }
        if let Reason::NotComplete(Cause::PairGaps(pairs)) = reason {
            held.kind = HoldKind::PairGaps;
            held.pairs = distinct(pairs.pairs(), pairs.origins());
        }
        if let Reason::NotComplete(Cause::AllowedPairGaps(pairs)) = reason {
            held.kind = HoldKind::AllowedPairGaps;
            held.pairs = distinct(pairs.pairs(), &[]);
        }
        if let Reason::NotComplete(Cause::ScopedGaps(scoped)) = reason {
            held.kind = HoldKind::ScopedGaps;
            held.ids = scoped.ids().to_vec();
        }
        held
    }
}

/// The pairs of the gap records, each once, in the order of their first record, with the origin
/// of that record when the rule states one.
fn distinct(
    records: &[(String, String)],
    origins: &[PairOrigin],
) -> Vec<(String, String, Option<PairOrigin>)> {
    let mut seen = BTreeSet::new();
    records
        .iter()
        .enumerate()
        .filter(|(_, pair)| seen.insert(*pair))
        .map(|(at, (source, target))| (source.clone(), target.clone(), origins.get(at).copied()))
        .collect()
}

/// The most imports that one rule lists.
const MAX_IMPORTS: usize = 20;

/// One held import.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct HeldImport {
    source: String,
    target: String,
    name: Option<String>,
    gap: &'static str,
    class: &'static str,
    /// The cause that the collector states; null when it states none.
    cause: Option<serde_json::Value>,
    evidence: Vec<String>,
}

/// The number of held imports of one gap and class.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct ClassCount {
    gap: &'static str,
    class: &'static str,
    count: usize,
}

/// What holds an `interface_boundary` rule: the count of each class and the first imports.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct InterfaceHolds {
    classes: Vec<ClassCount>,
    imports: Vec<HeldImport>,
}

impl InterfaceHolds {
    /// The projection of the hold of one rule.
    pub(crate) fn of(hold: &InterfaceHold) -> InterfaceHolds {
        InterfaceHolds {
            classes: hold
                .classes()
                .map(|(gap, class, count)| ClassCount {
                    gap: InterfaceGap::word(gap),
                    class: class.map_or("not_stated", RouteWithheld::as_str),
                    count,
                })
                .collect(),
            imports: hold
                .imports()
                .iter()
                .take(MAX_IMPORTS)
                .map(|held| HeldImport {
                    source: held.source.clone(),
                    target: held.target.clone(),
                    name: held.name.clone(),
                    gap: InterfaceGap::word(held.gap),
                    class: held
                        .cause
                        .as_ref()
                        .map_or("not_stated", |(cause, _)| cause.as_str()),
                    cause: held.cause.as_ref().map(cause_value),
                    evidence: held.evidence.clone(),
                })
                .collect(),
        }
    }
}

/// The cause as the frame writes it: its kind and the module or hop that it names.
fn cause_value((cause, at): &(RouteWithheld, Option<String>)) -> serde_json::Value {
    serde_json::json!({"kind": cause.as_str(), "at": at})
}
