// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `Ruling`: the decided head of the engine frame of the core (AD-388, #1073 item 4).
//!
//! The core writes the status of a run and the verdict of each rule only through a `Ruling`.
//! `rule` is its only maker. It evaluates the model itself, so no other outcome can enter. The status comes from the status rule of the report (`run_status`,
//! the same rule as `status_of`). A PASS status needs the run proof of the model
//! (`Scope::run_complete`), as `build` does. The core adds only gaps (`Named`): a gap can make a
//! status stricter, never PASS. The frame keeps its rows and the `Decided` mark.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use std::collections::{BTreeMap, BTreeSet};

use archkeel_eval::{evaluate, Outcome};
use archkeel_model::{
    Decision, Model, ModelTree, Reason, UmlGap, UmlOutcome, UmlTarget, Unsupported,
    Verdict as ModelVerdict,
};
use serde::Serialize;

#[path = "explain.rs"]
mod explain;
pub use explain::Explain;

use crate::{
    build_error::BuildError,
    engine_frame::{EngineFrame, FrameError},
    head::{RuleVerdict, Status},
    report::{Decided, RunStatus},
    run_scope::RunScope,
    status::{run_status, Unexplained},
    violation_detail::ViolationDetail,
    why::WhyUnknown,
};

/// The gaps that the core names next to the model. No field holds a verdict: each gap only
/// holds back a PASS.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Named {
    /// The reason of each rule that has no decision of the model (an inside rule, a UML target,
    /// each rule of a run without a model).
    pub rules: BTreeMap<String, Reason>,
    /// One reason for the whole contract (a baseline, a missing or refused contract). Then the
    /// frame has no rule row.
    pub contract: Option<String>,
    /// The `GapKind` word of `contract` (AD-546). Empty text is the word `other`.
    pub contract_kind: Option<&'static str>,
    /// A reason that holds back each PASS of the run (the scope of a contract tree).
    pub hold: Option<Reason>,
    /// The UML target row of the tree, by its id (AD-470): the target that the model compares,
    /// or the cause that keeps the row UNKNOWN (AD-494).
    pub uml: Option<(String, UmlTarget)>,
}

/// The reasons of the rules without a decision: one for each rule, or one for the contract.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(untagged)]
pub enum RuleReasons {
    /// One reason for each rule, by rule id.
    Each(BTreeMap<String, String>),
    /// One reason for all rules.
    All(String),
}

impl RuleReasons {
    /// True when no rule has a reason.
    pub fn is_empty(&self) -> bool {
        match self {
            RuleReasons::Each(each) => each.is_empty(),
            RuleReasons::All(_) => false,
        }
    }
}

/// The decided head of the engine frame. The fields are private: only `rule` makes one.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct Ruling {
    #[schemars(extend("const" = "archkeel-core-frame-1"))]
    protocol: &'static str,
    #[serde(skip)]
    html: bool,
    #[serde(skip)]
    decided: Decided,
    status: Status,
    /// The kind word and the verdict of each decided rule.
    rules: BTreeMap<String, (String, RuleVerdict)>,
    /// The reason of each UNKNOWN rule.
    explained: BTreeMap<String, String>,
    /// The number of violations of each FAIL rule.
    violations: BTreeMap<String, usize>,
    details: BTreeMap<String, Vec<ViolationDetail>>,
    unknown_kinds: BTreeMap<String, WhyUnknown>,
    /// Each PASS rule of a run with kept pair gaps: the reference engine gives it UNKNOWN, and
    /// the model proves that no kept gap can change it (AD-384 point 4).
    beyond: BTreeMap<String, String>,
    /// The premises of the PASS rules (AD-664, #1549).
    #[serde(flatten)]
    premises: crate::assumed::Premises,
    /// Why the scope of the run is not complete, or `complete`.
    scope: RunScope,
    /// The one assumption that the collector states for its proofs (AD-540). The word of `scope`
    /// stays `complete`: the shell reads it.
    #[serde(skip_serializing_if = "Option::is_none")]
    premise: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    excluded_sources: Vec<String>,
    #[serde(skip)]
    unsupported: RuleReasons,
    /// The typed reason of each rule without a decision, UNKNOWN rows and named rows alike. The
    /// baseline key reads these and never the text (AD-546).
    #[serde(skip)]
    causes: BTreeMap<String, Reason>,
    /// The word and the text that name the whole contract, when one reason does.
    #[serde(skip)]
    contract_kind: Option<&'static str>,
    /// What the `explain` part copies; the core adds the coverage gaps of the reply (AD-484).
    #[serde(skip)]
    explain: explain::Collected,
}

impl Ruling {
    /// Request a static presentation of this same ruling, without changing its decision.
    pub fn with_html(mut self, html: bool) -> Self {
        self.html = html;
        self
    }

    /// The `explain` part of the frame (AD-484): the shape of each rule, the path of each cycle
    /// and the gaps that hold each rule. It copies what the decision states and decides nothing.
    pub fn explain(&self, gaps: &[archkeel_model::CoverageGap]) -> explain::Explain {
        self.explain.clone().finish(gaps)
    }

    /// The decided mark: the status, the run proof of a PASS and the Decision of each rule.
    pub fn decided(&self) -> &Decided {
        &self.decided
    }

    /// The scope of the run: complete, or open with its reason.
    pub fn scope(&self) -> &RunScope {
        &self.scope
    }

    /// The reasons of the rules without a decision.
    pub fn unsupported(&self) -> &RuleReasons {
        &self.unsupported
    }

    /// Each violation as the rule, the source and the target that it names. The baseline reads
    /// these rows (AD-546).
    pub fn violation_rows(&self) -> Vec<(&str, &str, Option<&str>)> {
        self.details
            .iter()
            .flat_map(|(rule, rows)| {
                rows.iter()
                    .map(move |row| (rule.as_str(), row.source(), row.target()))
            })
            .collect()
    }

    /// The typed reason of each rule without a decision (AD-546).
    pub fn causes(&self) -> &BTreeMap<String, Reason> {
        &self.causes
    }

    /// The `GapKind` word of the reason of the whole contract, if one reason names it.
    pub fn contract_kind(&self) -> Option<&'static str> {
        self.contract_kind
    }

    /// The frame of this ruling with the parts of the core: the only maker of `EngineFrame`. It
    /// writes the keys of the ruling and `unsupported.rules`; a part with one of them is refused.
    pub fn frame<P: Serialize>(&self, parts: &P) -> Result<EngineFrame, FrameError> {
        let ruling = serde_json::to_value(self);
        let reasons = serde_json::to_value(&self.unsupported);
        crate::engine_frame::write(ruling, reasons, parts, self.html)
    }
}

/// The ruling of a run: the outcomes of each model of the tree (the root, then each mount,
/// AD-385), the gaps of the core, the status and its proof. A frame that breaks the explaining
/// rows of AD-361 point 5 is an error, never a ruling.
pub fn rule(models: Result<&ModelTree, &Reason>, named: Named) -> Result<Ruling, BuildError> {
    rule_with_edge_links(models, named, false).map(|(ruling, _)| ruling)
}

/// Evaluate once and also give the rules whose FAIL rows cite each import identity; the map is
/// empty unless `keep_links` is set.
pub fn rule_with_edge_links(
    models: Result<&ModelTree, &Reason>,
    named: Named,
    keep_links: bool,
) -> Result<(Ruling, BTreeMap<String, BTreeSet<String>>), BuildError> {
    let scope = match models {
        Ok(models) => models
            .models()
            .find_map(|checked: &Model| checked.scope(|scope| scope.run()).err()),
        Err(reason) => Some(reason.clone()),
    };
    let observed = models.ok();
    let premise = observed.and_then(|tree| tree.models().find_map(Model::scope_premise));
    let scope = scope.map_or(RunScope::Complete, RunScope::Open);
    let mut rows = Rows::default();
    let mut edge_links = crate::edge_links::Links::new();
    let mut reasons: BTreeMap<String, String> = BTreeMap::new();
    let mut gaps = named.rules;
    // Each row reads the model whose contract holds its rule; a reason for the whole contract
    // leaves no row.
    let decided = models.ok().filter(|_| named.contract.is_none());
    for model in decided.into_iter().flat_map(ModelTree::models) {
        for outcome in evaluate(model) {
            rows.explain.rule(&outcome, model);
            rows.add(&outcome, model, named.hold.as_ref(), &mut gaps)?;
            if keep_links {
                crate::edge_links::add(&mut edge_links, &outcome);
            }
        }
    }
    let uml = rows.uml(named.uml, decided, models.err(), &mut gaps)?;
    for (id, reason) in &gaps {
        rows.explain.unknown(id, reason);
    }
    for (id, reason) in &gaps {
        rows.causes.insert(id.clone(), reason.clone());
    }
    reasons.extend(
        gaps.into_iter()
            .map(|(id, reason)| (id, reason.to_string())),
    );
    // AD-416: declarations have no decision and cannot make a run PASS by themselves. An UNKNOWN
    // UML row is a row of the run, so the contract has a row that names why it is open.
    let given = named.contract.is_some();
    let contract = named.contract.or_else(|| {
        (models.is_ok()
            && !uml
            && rows
                .decisions
                .iter()
                .all(|(_, decision)| decision.is_none())
            && reasons.is_empty())
        .then(|| Reason::Unsupported(Unsupported::NoRules).to_string())
    });
    let open = contract.is_some()
        || !reasons.is_empty()
        || rows.rules.values().any(|(_, v)| *v == RuleVerdict::Unknown);
    let failed = rows.rules.values().any(|(_, v)| *v == RuleVerdict::Fail);
    let status = run_status(true, failed, scope.is_complete(), open);
    let run = match status {
        Status::Pass => RunStatus::Pass(run_pass(
            &rows.decisions,
            models.map_err(|_| BuildError::PassWithoutProof(None))?,
        )?),
        Status::Fail => RunStatus::Fail,
        Status::Unknown => RunStatus::Unknown,
    };
    let observation = if scope.is_complete() {
        Status::Pass
    } else {
        Status::Unknown
    };
    let contract_kind = match (given, contract.is_some()) {
        (true, _) => Some(named.contract_kind.unwrap_or("other")),
        (false, true) => Some("no_decided_rule"),
        (false, false) => None,
    };
    let unsupported = match contract {
        Some(reason) => RuleReasons::All(reason),
        None => RuleReasons::Each(reasons),
    };
    let fails = ViolationDetail::declared_by_rule(&rows.details);
    let premises = crate::assumed::Premises::of(rows.premises, models.ok(), &fails);
    let ruling = Ruling {
        protocol: "archkeel-core-frame-1",
        html: false,
        decided: Decided {
            run,
            observation,
            rules: rows.decisions,
        },
        status,
        rules: rows.rules,
        explained: rows.explained,
        violations: rows.violations,
        details: rows.details,
        unknown_kinds: rows.unknown_kinds,
        beyond: rows.beyond,
        premises,
        scope,
        excluded_sources: observed.map_or_else(Vec::new, ModelTree::excluded_sources),
        premise: premise.map(str::to_owned),
        unsupported,
        causes: rows.causes,
        contract_kind,
        explain: rows.explain,
    };
    Ok((ruling, edge_links))
}

/// The rows of the decided rules.
#[derive(Default)]
struct Rows {
    seen: BTreeSet<String>,
    rules: BTreeMap<String, (String, RuleVerdict)>,
    explained: BTreeMap<String, String>,
    violations: BTreeMap<String, usize>,
    details: BTreeMap<String, Vec<ViolationDetail>>,
    unknown_kinds: BTreeMap<String, WhyUnknown>,
    causes: BTreeMap<String, Reason>,
    beyond: BTreeMap<String, String>,
    premises: BTreeMap<String, Vec<crate::assumed::Premise>>,
    decisions: Vec<(String, Option<Decision>)>,
    explain: explain::Collected,
}

impl Rows {
    /// The row of one outcome, or its gap. A PASS row needs a PASS of its own rule of the model
    /// and a DECLARATION row a declaration rule of the model (AD-381); each status other than
    /// PASS has its explaining row.
    fn add(
        &mut self,
        outcome: &Outcome,
        model: &Model,
        hold: Option<&Reason>,
        gaps: &mut BTreeMap<String, Reason>,
    ) -> Result<(), BuildError> {
        let id = outcome.rule().to_owned();
        if !self.seen.insert(id.clone()) {
            return Err(BuildError::DuplicateRule { rule: id });
        }
        let count = outcome.violations().len();
        let verdict = match outcome.decision() {
            None if model.declares(&id) => RuleVerdict::Declaration,
            None => return Err(BuildError::ForeignDeclaration { rule: id }),
            Some(decision) => match (decision.verdict(), decision.reason()) {
                (_, Some(reason @ Reason::Unsupported(_))) => {
                    gaps.insert(id, reason.clone());
                    return Ok(());
                }
                (ModelVerdict::Pass(_), _) if !decision.passes(model, &id) => {
                    return Err(BuildError::ForeignPass { rule: id });
                }
                // AD-379: a root rule of a mounted tree never passes.
                (ModelVerdict::Pass(_), _) => match hold {
                    Some(reason) => {
                        gaps.insert(id, reason.clone());
                        return Ok(());
                    }
                    None => {
                        if let Some(why) = crate::beyond::reason(model) {
                            self.beyond.insert(id.clone(), why);
                        }
                        let premises = crate::assumed::of(model, &id);
                        if !premises.is_empty() {
                            self.premises.insert(id.clone(), premises);
                        }
                        RuleVerdict::Pass
                    }
                },
                (ModelVerdict::Fail, _) => RuleVerdict::Fail,
                (ModelVerdict::Unknown, reason) => {
                    let why = reason.map_or_else(String::new, ToString::to_string);
                    if why.is_empty() {
                        let found = vec![Unexplained::UnknownWithoutRow];
                        return Err(BuildError::Unexplained(found));
                    }
                    self.explained.insert(id.clone(), why);
                    if let Some(reason) = reason {
                        self.explain.unknown(&id, reason);
                        self.unknown_kinds
                            .insert(id.clone(), WhyUnknown::of(reason));
                        self.causes.insert(id.clone(), reason.clone());
                    }
                    RuleVerdict::Unknown
                }
            },
        };
        fits(verdict, count, &id)?;
        if verdict == RuleVerdict::Fail {
            self.violations.insert(id.clone(), count);
            self.details.insert(
                id.clone(),
                outcome
                    .violations()
                    .iter()
                    .map(ViolationDetail::of)
                    .collect(),
            );
        }
        let kind = crate::kind::word(outcome.kind()).to_owned();
        self.rules.insert(id.clone(), (kind, verdict));
        self.decisions.push((id, outcome.decision().cloned()));
        Ok(())
    }
}

impl Rows {
    /// The UML target row (AD-470, AD-494). Without a model the row is a gap with the reason of
    /// the run. With a model, the root model compares the target: PASS only with the scope proof
    /// of the run (`Decision::passes`), FAIL with each differing fact, else UNKNOWN with its
    /// cause. The row never enters `decisions`, so the run proof reads only the rules.
    fn uml(
        &mut self,
        target: Option<(String, UmlTarget)>,
        decided: Option<&ModelTree>,
        run: Option<&Reason>,
        gaps: &mut BTreeMap<String, Reason>,
    ) -> Result<bool, BuildError> {
        let Some((id, target)) = target else {
            return Ok(false);
        };
        if !self.seen.insert(id.clone()) {
            return Err(BuildError::DuplicateRule { rule: id });
        }
        let Some(tree) = decided else {
            let gap = match target {
                UmlTarget::Gap(gap) => gap,
                UmlTarget::Compare(found) => {
                    let (entities, relationships, scopes) = found.counts();
                    UmlGap::NotCompared {
                        entities,
                        relationships,
                        scopes,
                    }
                }
            };
            gaps.insert(id, run.cloned().unwrap_or(Reason::Uml(gap)));
            return Ok(false);
        };
        let outcome = match target {
            UmlTarget::Gap(gap) => UmlOutcome::Unknown(gap),
            UmlTarget::Compare(found) => archkeel_model::compare_uml_tree(tree, &found, &id),
        };
        let verdict = match outcome {
            UmlOutcome::Pass(decision) if decision.passes(tree.root(), &id) => RuleVerdict::Pass,
            UmlOutcome::Pass(_) => {
                return Err(BuildError::Unexplained(vec![
                    Unexplained::UnknownWithoutRow,
                ]))
            }
            UmlOutcome::Fail(diffs) => {
                self.violations.insert(id.clone(), diffs.len());
                self.details
                    .insert(id.clone(), diffs.iter().map(ViolationDetail::uml).collect());
                RuleVerdict::Fail
            }
            UmlOutcome::Unknown(gap) => {
                let reason = Reason::Uml(gap);
                self.explain.unknown(&id, &reason);
                self.explained.insert(id.clone(), reason.to_string());
                self.unknown_kinds
                    .insert(id.clone(), WhyUnknown::of(&reason));
                self.causes.insert(id.clone(), reason);
                RuleVerdict::Unknown
            }
        };
        self.rules.insert(id, ("uml_target".to_owned(), verdict));
        Ok(true)
    }
}

/// The row of a verdict with `count` violations, refused unless it explains its verdict: a FAIL
/// needs a violation (L-23), and no other verdict has one.
fn fits(verdict: RuleVerdict, count: usize, id: &str) -> Result<(), BuildError> {
    match (verdict, count) {
        (RuleVerdict::Fail, 0) => Err(BuildError::Unexplained(vec![
            Unexplained::FailWithoutViolation,
        ])),
        (RuleVerdict::Fail, _)
        | (RuleVerdict::Pass | RuleVerdict::Unknown | RuleVerdict::Declaration, 0) => Ok(()),
        (RuleVerdict::Pass | RuleVerdict::Unknown | RuleVerdict::Declaration, _) => {
            Err(BuildError::ReasonMismatch {
                rule: id.to_owned(),
            })
        }
    }
}

/// The run proof of the model over the decided rules (L-35b): a PASS needs it.
/// The run proof of the tree (`ModelTree::pass_run`, the one maker of a run PASS of a tree).
fn run_pass(
    decisions: &[(String, Option<Decision>)],
    models: &ModelTree,
) -> Result<archkeel_model::RunPass, BuildError> {
    let decided = decisions
        .iter()
        .filter_map(|(_, decision)| decision.as_ref());
    models
        .pass_run(decided)
        .map_err(|gap| BuildError::PassWithoutProof(Some(gap)))
}

#[cfg(test)]
#[path = "ruling_tests.rs"]
mod tests;
