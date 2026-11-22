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
use archkeel_model::{shape, Applied, Cause, CoverageGap, Incomplete, Model, Reason, Shape};
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

/// The schema of the budgets: each field is a constant, the value of `BUDGETS`. The shell reads
/// the limits from the schema and keeps no copy of them.
fn budgets_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
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
fn version_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
    schemars::json_schema!({"const": VERSION})
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct RuleShape {
    kind: &'static str,
    direction: &'static str,
    source: Vec<String>,
    target: Vec<String>,
}

/// One step of a cycle path.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct Step {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    possible: bool,
    from: String,
    to: String,
    from_component: Option<String>,
    to_component: Option<String>,
    imports: usize,
    /// The declared edges of the step: the declaration, the module of its site and the module that
    /// it may load (AD-1048).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    declared: Vec<DeclaredEdge>,
    evidence: Vec<String>,
    evidence_total: usize,
}

/// One possible import that a declaration supplies to a cycle step.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct DeclaredEdge {
    declaration: String,
    source: String,
    target: String,
}

/// One cycle: its members and one closed path through them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct Cycles {
    total: usize,
    truncated: bool,
    items: Vec<CyclePath>,
}

/// What kind of gap holds a rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
enum HoldKind {
    CoverageGaps,
    PairGaps,
    AllowedPairGaps,
    /// Gaps that state their effect, and the rule reads the effect (AD-564).
    ScopedGaps,
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
    /// The ids of the gaps that the reason itself names (AD-564).
    ids: Vec<String>,
    unnamed_imports: usize,
}

impl Held {
    /// The kind of hold that a reason states, with the pairs, the gap ids and the unnamed
    /// imports that it names.
    fn of(reason: &Reason) -> Held {
        let mut held = Held {
            cause: WhyUnknown::of(reason),
            kind: HoldKind::Other,
            pairs: Vec::new(),
            ids: Vec::new(),
            unnamed_imports: 0,
        };
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
            held.pairs = distinct(pairs.pairs());
        }
        if let Reason::NotComplete(Cause::AllowedPairGaps(pairs)) = reason {
            held.kind = HoldKind::AllowedPairGaps;
            held.pairs = distinct(pairs.pairs());
        }
        if let Reason::NotComplete(Cause::ScopedGaps(scoped)) = reason {
            held.kind = HoldKind::ScopedGaps;
            held.ids = scoped.ids().to_vec();
        }
        held
    }
}

/// The facts that `explain` collects while the rules are decided.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Collected {
    rules: BTreeMap<String, RuleShape>,
    cycles: BTreeMap<String, Cycles>,
    held: BTreeMap<String, Held>,
}

/// The pairs of the gap records, each once, in the order of their first record.
fn distinct(records: &[(String, String)]) -> Vec<(String, String)> {
    let mut seen = BTreeSet::new();
    records
        .iter()
        .filter(|pair| seen.insert(*pair))
        .cloned()
        .collect()
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
            .filter_map(|(index, violation)| {
                if let Violation::Cycle(cycle) = violation {
                    Some(cycle_path(index, cycle, model))
                } else {
                    None
                }
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

fn cycle_path(index: usize, cycle: &archkeel_eval::Cyclic, model: &Model) -> CyclePath {
    let steps_total = cycle.path.len();
    let applied = model.graph().trojan_horses().applied();
    CyclePath {
        id: cycle.id.clone(),
        index,
        members: cycle.members.clone(),
        path: (cycle.path.iter().take(MAX_STEPS))
            .map(|each| step(each, applied))
            .collect(),
        steps_total,
        truncated: steps_total > MAX_STEPS,
    }
}

/// The declared edges behind the imports of a step: a declared import has the id that its
/// declaration gives it, so the join needs no module name.
fn declared_edges(step: &CycleStep, applied: &[Applied]) -> Vec<DeclaredEdge> {
    let mut found = Vec::new();
    for site in applied {
        for (target, id) in &site.edges {
            if step.imports.contains(id) {
                found.push(DeclaredEdge {
                    declaration: site.id.clone(),
                    source: site.module.clone(),
                    target: target.clone(),
                });
            }
        }
    }
    found
}

fn step(step: &CycleStep, applied: &[Applied]) -> Step {
    Step {
        declared: declared_edges(step, applied),
        possible: step.possible,
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct Pair {
    source: String,
    target: String,
}

/// The gaps that hold one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct RuleHolds {
    cause: WhyUnknown,
    kind: HoldKind,
    /// The ids of the coverage gaps of the reply that hold the rule.
    gaps: Vec<String>,
    /// The first module pairs that hold the rule (a pair is two modules with a gap between them).
    pairs: Vec<Pair>,
    /// The number of module pairs that hold the rule. A pair can have several gap records. A
    /// rule that no pair holds counts gap ids. `pairs` and `gaps` keep at most `held_per_rule`.
    total: usize,
    /// True when `total` is larger than the lists that this frame keeps.
    truncated: bool,
    /// The imports that the collector could not resolve and that no gap names.
    unnamed_imports: usize,
}

/// One coverage gap and the rules that it holds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct GapHolds {
    id: String,
    kind: String,
    reason: String,
    rules: Vec<String>,
    rules_total: usize,
    truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct Explain {
    #[schemars(schema_with = "version_schema")]
    version: u8,
    #[schemars(schema_with = "budgets_schema")]
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
            .filter(|gap| gap.whole)
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
        HoldKind::ScopedGaps => held.ids.clone(),
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
            // A pair rule counts distinct pairs; a record count would not match the noun.
            let total = match held.kind {
                HoldKind::PairGaps | HoldKind::AllowedPairGaps => held.pairs.len(),
                HoldKind::CoverageGaps
                | HoldKind::ScopedGaps
                | HoldKind::UnknownImports
                | HoldKind::NoSourceFiles
                | HoldKind::Other => ids.len(),
            };
            held_by_rule.insert(
                rule.clone(),
                RuleHolds {
                    cause: held.cause,
                    kind: held.kind,
                    // The host checks that no list is longer than `total`, which counts pairs here.
                    gaps: ids.into_iter().take(MAX_HELD.min(total)).collect(),
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
