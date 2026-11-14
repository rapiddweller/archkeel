// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `explain` part of the engine frame (AD-484): what a page needs to draw a rule, a cycle and
//! a gap without parsing text. It copies what the model and the evaluator state. It decides
//! nothing, it changes no verdict and it recomputes no hold: a rule holds the gaps that its own
//! reason names.
//!
//! - `rules`: the kind, the direction and the component ids of the two sides of each rule.
//! - `cycles`: for each FAIL cycle rule, one ordered closed path for each cycle.
//! - `holds`: for each rule without a verdict, the gaps that hold it; for each coverage gap that
//!   holds a rule, the rules that it holds.
//!
//! Each list has a budget. A list over its budget keeps the first rows, sets `truncated` and keeps
//! the exact `total`: a short list never hides its size.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_contract::{head_of, Rule};
use archkeel_eval::{CycleStep, Outcome, Violation};
use archkeel_model::{shape, Cause, CoverageGap, Incomplete, Model, Reason, Shape};
use serde::Serialize;

use crate::why::WhyUnknown;

const VERSION: u8 = 1;
/// The most cycles that one rule lists.
const MAX_CYCLES: usize = 50;
/// The most steps that one path lists.
const MAX_STEPS: usize = 64;
/// The most evidence ids that one step lists.
const MAX_EVIDENCE: usize = 5;
/// The most gaps and pairs that one rule lists.
const MAX_HELD: usize = 20;
/// The most rules that one gap lists.
const MAX_RULES: usize = 200;
/// The most gaps that the part lists.
const MAX_GAPS: usize = 500;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Budgets {
    cycles_per_rule: usize,
    path_steps: usize,
    evidence_per_step: usize,
    held_per_rule: usize,
    rules_per_gap: usize,
    gaps: usize,
}

const BUDGETS: Budgets = Budgets {
    cycles_per_rule: MAX_CYCLES,
    path_steps: MAX_STEPS,
    evidence_per_step: MAX_EVIDENCE,
    held_per_rule: MAX_HELD,
    rules_per_gap: MAX_RULES,
    gaps: MAX_GAPS,
};

/// The shape of one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct RuleShape {
    kind: &'static str,
    direction: &'static str,
    source: Vec<String>,
    target: Vec<String>,
}

/// One step of a cycle path.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Step {
    from: String,
    to: String,
    from_component: Option<String>,
    to_component: Option<String>,
    imports: usize,
    evidence: Vec<String>,
    evidence_total: usize,
}

/// One cycle: its members and one closed path through them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct CyclePath {
    id: String,
    /// The position of the violation in `details` of the rule.
    index: usize,
    members: Vec<String>,
    path: Vec<Step>,
    steps_total: usize,
    truncated: bool,
}

/// The cycles of one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Cycles {
    total: usize,
    truncated: bool,
    items: Vec<CyclePath>,
}

/// What kind of gap holds a rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum HoldKind {
    CoverageGaps,
    PairGaps,
    AllowedPairGaps,
    UnknownImports,
    NoSourceFiles,
    /// Any other cause: the text of `explained` names it.
    Other,
}

/// What the reason of one rule says about the gaps that hold it.
#[derive(Clone, Debug, PartialEq, Eq)]
struct Held {
    cause: WhyUnknown,
    kind: HoldKind,
    pairs: Vec<(String, String)>,
    unnamed_imports: usize,
}

impl Held {
    fn of(reason: &Reason) -> Held {
        let (kind, pairs, unnamed_imports) = match reason {
            Reason::Incomplete(Incomplete::CoverageGaps(_)) => {
                (HoldKind::CoverageGaps, Vec::new(), 0)
            }
            Reason::Incomplete(Incomplete::UnknownImports(count)) => {
                (HoldKind::UnknownImports, Vec::new(), *count)
            }
            Reason::Incomplete(Incomplete::NoSourceFiles) => {
                (HoldKind::NoSourceFiles, Vec::new(), 0)
            }
            Reason::NotComplete(Cause::PairGaps(held)) => {
                (HoldKind::PairGaps, held.pairs().to_vec(), 0)
            }
            Reason::NotComplete(Cause::AllowedPairGaps(held)) => {
                (HoldKind::AllowedPairGaps, held.pairs().to_vec(), 0)
            }
            _ => (HoldKind::Other, Vec::new(), 0),
        };
        Held {
            cause: WhyUnknown::of(reason),
            kind,
            pairs,
            unnamed_imports,
        }
    }
}

/// The facts that `explain` collects while the rules are decided.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Collected {
    rules: BTreeMap<String, RuleShape>,
    cycles: BTreeMap<String, Cycles>,
    held: BTreeMap<String, Held>,
}

impl Collected {
    /// The shape of the rule of an outcome, and the cycles of its violations.
    pub(crate) fn rule(&mut self, outcome: &Outcome, model: &Model) {
        let id = outcome.rule();
        let found = model
            .contract()
            .rules()
            .iter()
            .find(|rule: &&Rule| head_of(rule).id().as_text() == id);
        if let Some(rule) = found {
            let Shape {
                kind,
                direction,
                source,
                target,
            } = shape(model.contract(), rule);
            self.rules.insert(
                id.to_owned(),
                RuleShape {
                    kind: crate::kind::word(kind),
                    direction: direction.word(),
                    source,
                    target,
                },
            );
        }
        let cycles: Vec<CyclePath> = outcome
            .violations()
            .iter()
            .enumerate()
            .filter_map(|(index, violation)| match violation {
                Violation::Cycle(cycle) => Some(cycle_path(index, cycle)),
                _ => None,
            })
            .collect();
        if !cycles.is_empty() {
            let total = cycles.len();
            self.cycles.insert(
                id.to_owned(),
                Cycles {
                    total,
                    truncated: total > MAX_CYCLES,
                    items: cycles.into_iter().take(MAX_CYCLES).collect(),
                },
            );
        }
    }

    /// The reason of a rule that has no verdict.
    pub(crate) fn unknown(&mut self, rule: &str, reason: &Reason) {
        self.held.insert(rule.to_owned(), Held::of(reason));
    }
}

fn cycle_path(index: usize, cycle: &archkeel_eval::Cyclic) -> CyclePath {
    let steps_total = cycle.path.len();
    CyclePath {
        id: cycle.id.clone(),
        index,
        members: cycle.members.clone(),
        path: cycle.path.iter().take(MAX_STEPS).map(step).collect(),
        steps_total,
        truncated: steps_total > MAX_STEPS,
    }
}

fn step(step: &CycleStep) -> Step {
    Step {
        from: step.from.clone(),
        to: step.to.clone(),
        from_component: step.from_component.clone(),
        to_component: step.to_component.clone(),
        imports: step.imports.len(),
        evidence: step.evidence.iter().take(MAX_EVIDENCE).cloned().collect(),
        evidence_total: step.evidence.len(),
    }
}

/// The pair of a gap between two modules.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Pair {
    source: String,
    target: String,
}

/// The gaps that hold one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct RuleHolds {
    cause: WhyUnknown,
    kind: HoldKind,
    /// The ids of the coverage gaps of the reply that hold the rule.
    gaps: Vec<String>,
    /// The pairs of the gaps between two modules that hold the rule.
    pairs: Vec<Pair>,
    /// The number of gaps that hold the rule.
    total: usize,
    truncated: bool,
    /// The imports that the collector could not resolve and that no gap names.
    unnamed_imports: usize,
}

/// One coverage gap and the rules that it holds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct GapHolds {
    id: String,
    kind: String,
    reason: String,
    rules: Vec<String>,
    rules_total: usize,
    truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Holds {
    rules: BTreeMap<String, RuleHolds>,
    gaps: Vec<GapHolds>,
    /// The number of coverage gaps of the reply.
    gaps_total: usize,
    /// The number of coverage gaps that hold at least one rule.
    gaps_holding: usize,
    gaps_truncated: bool,
}

/// The `explain` part of the frame.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Explain {
    version: u8,
    budgets: Budgets,
    rules: BTreeMap<String, RuleShape>,
    cycles: BTreeMap<String, Cycles>,
    holds: Holds,
}

/// The gaps of a rule that its reason names: the ids of the gaps of the reply that it holds.
fn ids_of(held: &Held, gaps: &[CoverageGap]) -> Vec<String> {
    match held.kind {
        HoldKind::CoverageGaps => gaps
            .iter()
            .filter(|gap| gap.holds_run)
            .map(|gap| gap.id.clone())
            .collect(),
        HoldKind::PairGaps | HoldKind::AllowedPairGaps => {
            let pairs: BTreeSet<(&str, &str)> = held
                .pairs
                .iter()
                .map(|(source, target)| (source.as_str(), target.as_str()))
                .collect();
            gaps.iter()
                .filter(|gap| match (&gap.source, &gap.module) {
                    (Some(source), Some(module)) => pairs.contains(&(source.as_str(), module)),
                    _ => false,
                })
                .map(|gap| gap.id.clone())
                .collect()
        }
        HoldKind::UnknownImports | HoldKind::NoSourceFiles | HoldKind::Other => Vec::new(),
    }
}

impl Collected {
    /// The part of the frame, with the coverage gaps of the reply that the pairs and the run
    /// scope refer to.
    pub(crate) fn finish(self, gaps: &[CoverageGap]) -> Explain {
        let mut held_by_rule: BTreeMap<String, RuleHolds> = BTreeMap::new();
        let mut rules_of: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for (rule, held) in &self.held {
            let ids = ids_of(held, gaps);
            for id in &ids {
                rules_of.entry(id.clone()).or_default().push(rule.clone());
            }
            let total = ids.len().max(held.pairs.len());
            held_by_rule.insert(
                rule.clone(),
                RuleHolds {
                    cause: held.cause,
                    kind: held.kind,
                    gaps: ids.into_iter().take(MAX_HELD).collect(),
                    pairs: held
                        .pairs
                        .iter()
                        .take(MAX_HELD)
                        .map(|(source, target)| Pair {
                            source: source.clone(),
                            target: target.clone(),
                        })
                        .collect(),
                    total,
                    truncated: total > MAX_HELD,
                    unnamed_imports: held.unnamed_imports,
                },
            );
        }
        let listed: Vec<GapHolds> = gaps
            .iter()
            .filter_map(|gap| {
                let rules = rules_of.get(&gap.id)?;
                Some(GapHolds {
                    id: gap.id.clone(),
                    kind: gap.kind.clone(),
                    reason: gap.title.clone(),
                    rules_total: rules.len(),
                    truncated: rules.len() > MAX_RULES,
                    rules: rules.iter().take(MAX_RULES).cloned().collect(),
                })
            })
            .collect();
        let holding = listed.len();
        Explain {
            version: VERSION,
            budgets: BUDGETS,
            rules: self.rules,
            cycles: self.cycles,
            holds: Holds {
                rules: held_by_rule,
                gaps: listed.into_iter().take(MAX_GAPS).collect(),
                gaps_total: gaps.len(),
                gaps_holding: holding,
                gaps_truncated: holding > MAX_GAPS,
            },
        }
    }
}
