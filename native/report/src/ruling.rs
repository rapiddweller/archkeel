// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `Ruling`: the decided head of the engine frame of the core (AD-388, #1073 item 4).
//!
//! The core writes the status of a run and the verdict of each rule only through a `Ruling`.
//! `rule` is its only maker. It evaluates the model itself, so an outcome of another model or a
//! bare verdict cannot enter. The status comes from the status rule of the report (`run_status`,
//! the same rule as `status_of`). A PASS status needs the run proof of the model
//! (`Scope::run_complete`), as `build` does. The core adds only gaps (`Named`): a gap can make a
//! status stricter, never PASS.
//!
//! A full `Report<Decided>` needs tables that no slice produces yet (`BuildError::NotProduced`),
//! so the engine frame keeps its rows and holds the same `Decided` mark.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use std::collections::{BTreeMap, BTreeSet};

use archkeel_eval::{evaluate, Outcome};
use archkeel_model::{
    Decision, Model, ModelTree, Reason, UmlGap, Unsupported, Verdict as ModelVerdict,
};
use serde::Serialize;

use crate::{
    build_error::BuildError,
    engine_frame::{EngineFrame, FrameError},
    head::{RuleVerdict, Status},
    report::Decided,
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
    /// A reason that holds back each PASS of the run (the scope of a contract tree).
    pub hold: Option<Reason>,
    /// The UML target row of the tree, by its id (AD-470). The cause has no verdict, so the row
    /// is UNKNOWN: it cannot pass and it cannot fail.
    pub uml: Option<(String, UmlGap)>,
}

/// The reasons of the rules without a decision: one for each rule, or one for the contract.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(untagged)]
pub enum RuleReasons {
    Each(BTreeMap<String, String>),
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Ruling {
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
    /// Why the scope of the run is not complete, or `complete`.
    scope: String,
    #[serde(skip)]
    unsupported: RuleReasons,
}

impl Ruling {
    /// Request a static presentation of this same ruling, without changing its decision.
    pub fn with_html(mut self, html: bool) -> Self {
        self.html = html;
        self
    }

    /// The decided mark: the status, the run proof of a PASS and the Decision of each rule.
    pub fn decided(&self) -> &Decided {
        &self.decided
    }

    /// The reasons of the rules without a decision.
    pub fn unsupported(&self) -> &RuleReasons {
        &self.unsupported
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
            .find_map(|model| model.scope(|scope| scope.run()).err()),
        Err(reason) => Some(reason.clone()),
    };
    let complete = scope.is_none();
    let scope = scope.map_or_else(|| "complete".to_owned(), |reason| reason.to_string());
    let mut rows = Rows::default();
    let mut edge_links = crate::edge_links::Links::new();
    let mut reasons: BTreeMap<String, String> = BTreeMap::new();
    let mut gaps = named.rules;
    // Each row reads the model whose contract holds its rule; a reason for the whole contract
    // leaves no row.
    let decided = models.ok().filter(|_| named.contract.is_none());
    for model in decided.into_iter().flat_map(ModelTree::models) {
        for outcome in evaluate(model) {
            rows.add(&outcome, model, named.hold.as_ref(), &mut gaps)?;
            if keep_links {
                crate::edge_links::add(&mut edge_links, &outcome);
            }
        }
    }
    let uml = rows.uml(named.uml, decided.is_some(), models.err(), &mut gaps)?;
    reasons.extend(
        gaps.into_iter()
            .map(|(id, reason)| (id, reason.to_string())),
    );
    // AD-416: declarations have no decision and cannot make a run PASS by themselves. An UNKNOWN
    // UML row is a row of the run, so the contract has a row that names why it is open.
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
    let status = run_status(true, failed, complete, open);
    let pass = match status {
        Status::Pass => Some(run_pass(&rows.decisions, models)?),
        Status::Fail | Status::Unknown => None,
    };
    let observation = if complete {
        Status::Pass
    } else {
        Status::Unknown
    };
    let unsupported = match contract {
        Some(reason) => RuleReasons::All(reason),
        None => RuleReasons::Each(reasons),
    };
    let ruling = Ruling {
        protocol: "archkeel-core-frame-1",
        html: false,
        decided: Decided {
            status,
            pass,
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
        scope,
        unsupported,
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
    beyond: BTreeMap<String, String>,
    decisions: Vec<(String, Option<Decision>)>,
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
                        let kept = model.kept_pair_gaps();
                        if kept > 0 {
                            let why =
                                format!("no one of the {kept} kept pair gaps can change the rule");
                            self.beyond.insert(id.clone(), why);
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
                        self.unknown_kinds
                            .insert(id.clone(), WhyUnknown::of(reason));
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
    /// The UML target row (AD-470): an UNKNOWN row with its cause when the model decides the
    /// rules, and a gap with the reason of the run when no model decides them. It never enters
    /// `decisions`, so it takes no part in a run proof. True when the row is written.
    fn uml(
        &mut self,
        target: Option<(String, UmlGap)>,
        decided: bool,
        run: Option<&Reason>,
        gaps: &mut BTreeMap<String, Reason>,
    ) -> Result<bool, BuildError> {
        let Some((id, gap)) = target else {
            return Ok(false);
        };
        if !self.seen.insert(id.clone()) {
            return Err(BuildError::DuplicateRule { rule: id });
        }
        if !decided {
            gaps.insert(id, run.cloned().unwrap_or(Reason::Uml(gap)));
            return Ok(false);
        }
        let reason = Reason::Uml(gap);
        self.explained.insert(id.clone(), reason.to_string());
        self.unknown_kinds
            .insert(id.clone(), WhyUnknown::of(&reason));
        self.rules
            .insert(id, ("uml_target".to_owned(), RuleVerdict::Unknown));
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
    models: Result<&ModelTree, &Reason>,
) -> Result<archkeel_model::RunPass, BuildError> {
    let models = models.map_err(|_| BuildError::PassWithoutProof(None))?;
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
