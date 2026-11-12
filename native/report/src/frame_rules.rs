// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rule rows of the frame: the verdict from the `Decision`, the reason from the verdict and
//! the violation count from the rows that cite the rule.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_model::{Decision, Model, Verdict as ModelVerdict};

use crate::build_error::BuildError;
use crate::head::{RuleReason, RuleResult, RuleVerdict, Status};
use crate::input::{RuleDecision, RuleOutcome, ViolationRow};
use crate::why::WhyUnknown;

/// The status of a `Decision`.
pub(crate) fn status(decision: &Decision) -> Status {
    match decision.verdict() {
        ModelVerdict::Pass(_) => Status::Pass,
        ModelVerdict::Fail => Status::Fail,
        ModelVerdict::Unknown => Status::Unknown,
    }
}

fn rule_verdict(decision: &RuleDecision) -> RuleVerdict {
    match decision {
        RuleDecision::Declaration => RuleVerdict::Declaration,
        RuleDecision::Decided(decision) => match status(decision) {
            Status::Pass => RuleVerdict::Pass,
            Status::Fail => RuleVerdict::Fail,
            Status::Unknown => RuleVerdict::Unknown,
        },
    }
}

/// The reason of a rule verdict: derived from the verdict, and for UNKNOWN from `WhyUnknown`.
fn rule_reason(verdict: RuleVerdict, why: Option<WhyUnknown>) -> Option<RuleReason> {
    match (verdict, why) {
        (RuleVerdict::Pass, None) => Some(RuleReason::Evaluated),
        (RuleVerdict::Fail, None) => Some(RuleReason::Violations),
        (RuleVerdict::Declaration, None) => Some(RuleReason::Declaration),
        (RuleVerdict::Unknown, Some(why)) => Some(match why {
            WhyUnknown::ScopeIncomplete => RuleReason::ScopeIncomplete,
            WhyUnknown::NoReceipt => RuleReason::NoReceipt,
            WhyUnknown::Undecided => RuleReason::Undecided,
            WhyUnknown::OwnershipBlocker => RuleReason::OwnershipBlocker,
        }),
        _ => None,
    }
}

/// The rule rows, by id; the violation count of each is the number of violation rows citing it.
/// A PASS row needs a PASS of its own rule of `model` (AD-378, AD-381): a type cannot stop a
/// `Decision` from moving, so the identity is checked. A run without a model has no PASS row.
/// A DECLARATION row needs a declaration rule of the contract of `model`.
pub(crate) fn rule_rows(
    rules: &[RuleOutcome],
    violations: &[ViolationRow],
    model: Option<&Model>,
) -> Result<Vec<RuleResult>, BuildError> {
    let mut cited: BTreeMap<&str, u64> = BTreeMap::new();
    for row in violations {
        let names: BTreeSet<&str> = row.rules.iter().map(String::as_str).collect();
        for name in names {
            let count = cited.entry(name).or_insert(0);
            *count = count.saturating_add(1);
        }
    }
    let mut out = Vec::with_capacity(rules.len());
    for rule in rules {
        let verdict = rule_verdict(&rule.decision);
        match &rule.decision {
            RuleDecision::Decided(decision) => {
                let own = model.is_some_and(|model| decision.passes(model, &rule.id));
                if verdict == RuleVerdict::Pass && !own {
                    return Err(BuildError::ForeignPass {
                        rule: rule.id.clone(),
                    });
                }
            }
            // With a model, a DECLARATION row needs a declaration rule of its contract. A run
            // without a model has no PASS, so a row there cannot hide a rule of a PASS run.
            RuleDecision::Declaration => {
                if model.is_some_and(|model| !model.declares(&rule.id)) {
                    return Err(BuildError::ForeignDeclaration {
                        rule: rule.id.clone(),
                    });
                }
            }
        }
        if verdict == RuleVerdict::Pass && !rule.evaluated {
            return Err(BuildError::PassWithoutReceipt {
                rule: rule.id.clone(),
            });
        }
        let reason =
            rule_reason(verdict, rule.why_unknown).ok_or_else(|| BuildError::ReasonMismatch {
                rule: rule.id.clone(),
            })?;
        out.push(RuleResult {
            id: rule.id.clone(),
            kind: rule.kind.clone(),
            title: rule.title.clone(),
            verdict,
            evaluated: rule.evaluated,
            violations: cited.get(rule.id.as_str()).copied().unwrap_or(0),
            undecided: u64::try_from(rule.undecided.len()).unwrap_or(u64::MAX),
            reason,
            rationale: rule.rationale.clone(),
            decided_by: rule.decided_by.clone(),
        });
    }
    out.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(out)
}
