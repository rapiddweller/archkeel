// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-eval: the rule families over the model (AD-359, AD-363, AD-370; epic #880).
//!
//! Each rule gives one `Outcome`. An outcome holds a `Decision`, never a bare `Verdict`: a PASS
//! comes only from the scope proof of the model (AD-363). A rule kind that no slice has ported
//! answers `Unsupported::Rule` by name.
//!
//! Slice S1 decides `complete_assignment` and `root_layout`: they read only the modules, the
//! packages and the owners of the model. A violation is a fact also in an incomplete scope, so
//! FAIL needs no proof. UNKNOWN comes from a fact that the reply proves not seen, or from a rule
//! that selects no module (no evaluator receipt). Any other case needs the scope proof of slice
//! S4; until then it is UNKNOWN with the reason `Unsupported::ScopeProof`, a named gap.

#![deny(unreachable_pub)]

mod assignment;
mod decide;
mod layout;
mod violation;

use archkeel_contract::{head_of, kind_of, Contract, Rule, RuleKind};
use archkeel_model::{Decision, Model, Reason, Unsupported};

pub use violation::Violation;

/// The result of one rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    rule: String,
    kind: RuleKind,
    decision: Decision,
    violations: Vec<Violation>,
}

impl Outcome {
    /// The rule id.
    pub fn rule(&self) -> &str {
        &self.rule
    }

    /// The rule kind.
    pub fn kind(&self) -> RuleKind {
        self.kind
    }

    /// The decision: the verdict, and the reason of an UNKNOWN.
    pub fn decision(&self) -> &Decision {
        &self.decision
    }

    /// The violations of the rule, in the order of their ids.
    pub fn violations(&self) -> &[Violation] {
        &self.violations
    }
}

/// The outcome of each rule of the contract, in contract order.
pub fn evaluate(contract: &Contract, model: &Model) -> Vec<Outcome> {
    contract
        .rules()
        .iter()
        .map(|rule| outcome(rule, model))
        .collect()
}

fn outcome(rule: &Rule, model: &Model) -> Outcome {
    let id = head_of(rule).id().as_text();
    let (violations, selected) = match rule {
        Rule::CompleteAssignment(rule) => assignment::check(id, rule, model),
        Rule::RootLayout(rule) => match layout::check(id, rule, model) {
            Ok(found) => found,
            Err(reason) => {
                return Outcome {
                    rule: id.to_owned(),
                    kind: RuleKind::RootLayout,
                    decision: Decision::unknown(reason),
                    violations: Vec::new(),
                };
            }
        },
        other => {
            let kind = kind_of(other);
            let reason = Reason::Unsupported(Unsupported::Rule(kind));
            return Outcome {
                rule: id.to_owned(),
                kind,
                decision: Decision::unknown(reason),
                violations: Vec::new(),
            };
        }
    };
    Outcome {
        rule: id.to_owned(),
        kind: kind_of(rule),
        decision: decide::decide(model, &violations, selected),
        violations,
    }
}

#[cfg(test)]
#[path = "eval_tests.rs"]
mod tests;
