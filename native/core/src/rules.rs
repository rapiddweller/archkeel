// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Rules` request: the decision of each rule of the contract (`archkeel-eval`).
//!
//! A decided rule has its status. A rule whose decision names an unsupported part (its kind, or
//! a part of the scope proof that the core cannot read) and a rule of a ported kind without a
//! model have their reason: the harness counts a named reason as a difference, never as equal
//! (AD-363). A decided UNKNOWN keeps its reason and a FAIL its number of violations, so each
//! status other than PASS has its explaining row (AD-361 point 5, AD-378).

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, Contract, RuleKind};
use archkeel_eval::Outcome;
use archkeel_model::{Model, Part, Reason, Unsupported, Verdict};

/// The rule kinds that `archkeel-eval` decides.
const DECIDED: &[RuleKind] = &[
    RuleKind::CompleteAssignment,
    RuleKind::RootLayout,
    RuleKind::ExternalDependencyScope,
    RuleKind::CompleteExternalScope,
];

/// The decided rules (id to kind and status) and the reason of each rule without a decision.
#[derive(Debug, Default)]
pub(crate) struct RuleAnswer {
    pub(crate) decided: BTreeMap<String, [String; 2]>,
    pub(crate) reasons: BTreeMap<String, Reason>,
    /// The reason of each decided UNKNOWN rule.
    pub(crate) explained: BTreeMap<String, String>,
    /// The number of violations of each decided rule that has one.
    pub(crate) violations: BTreeMap<String, usize>,
    /// Why the scope of the run is not complete, or `None` when it is (`Scope::run`).
    pub(crate) scope: Option<String>,
}

/// The outcome of each rule, or the reason that the run has no model.
pub(crate) fn outcomes(contract: &Contract, model: Result<&Model, Reason>) -> Vec<Outcome> {
    match model {
        Ok(model) => archkeel_eval::evaluate(contract, model),
        Err(_) => Vec::new(),
    }
}

pub(crate) fn answer(contract: Option<&Contract>, model: Result<&Model, Reason>) -> RuleAnswer {
    let mut answer = RuleAnswer {
        scope: Some(match &model {
            Ok(model) => match model.scope(|scope| scope.run()) {
                Ok(()) => String::new(),
                Err(reason) => reason.to_string(),
            },
            Err(reason) => reason.to_string(),
        })
        .filter(|why| !why.is_empty()),
        ..RuleAnswer::default()
    };
    let Some(contract) = contract else {
        answer.scope = Some(Reason::MissingInput(archkeel_model::Input::Contract).to_string());
        return answer;
    };
    if let Err(reason) = &model {
        for rule in contract.rules() {
            let kind = kind_of(rule);
            let reason = if DECIDED.contains(&kind) {
                reason.clone()
            } else {
                Reason::Unsupported(Unsupported::Rule(kind))
            };
            let id = head_of(rule).id().as_text().to_owned();
            answer.reasons.insert(id, reason);
        }
        return answer;
    }
    let Ok(model_of) = model else {
        return answer;
    };
    for outcome in outcomes(contract, Ok(model_of)) {
        let decision = outcome.decision();
        let status = match (decision.verdict(), decision.reason()) {
            (_, Some(reason @ Reason::Unsupported(_))) => {
                answer
                    .reasons
                    .insert(outcome.rule().to_owned(), reason.clone());
                continue;
            }
            (Verdict::Pass(_), _) if decision.passes(model_of, outcome.rule()) => "PASS",
            (Verdict::Pass(_), _) => {
                // AD-378: a PASS of another rule or model is a named gap, never a PASS.
                let foreign = Reason::Unsupported(Unsupported::ScopeProof(Part::ForeignRule));
                answer.reasons.insert(outcome.rule().to_owned(), foreign);
                continue;
            }
            (Verdict::Fail, _) => "FAIL",
            (Verdict::Unknown, reason) => {
                let why = reason.map_or_else(String::new, ToString::to_string);
                answer.explained.insert(outcome.rule().to_owned(), why);
                "UNKNOWN"
            }
        };
        if !outcome.violations().is_empty() {
            let count = outcome.violations().len();
            answer.violations.insert(outcome.rule().to_owned(), count);
        }
        answer.decided.insert(
            outcome.rule().to_owned(),
            [word(outcome.kind()), status.to_owned()],
        );
    }
    answer
}

/// The word of a rule kind in the verdict map (`complete_assignment`).
fn word(kind: RuleKind) -> String {
    serde_json::to_value(kind)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_else(|| format!("{kind:?}"))
}
