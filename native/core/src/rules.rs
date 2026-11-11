// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Rules` request: the decision of each rule of the contract (`archkeel-eval`).
//!
//! A decided rule has its status. A rule whose decision names an unsupported part (its kind, or
//! the scope proof of S4) and a rule of a ported kind without a model have their reason: the
//! harness counts a named reason as a difference, never as equal (AD-363).

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, Contract, RuleKind};
use archkeel_eval::Outcome;
use archkeel_model::{Model, Reason, Unsupported, Verdict};

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
}

/// The outcome of each rule, or the reason that the run has no model.
pub(crate) fn outcomes(contract: &Contract, model: &Result<Model, Reason>) -> Vec<Outcome> {
    match model {
        Ok(model) => archkeel_eval::evaluate(contract, model),
        Err(_) => Vec::new(),
    }
}

pub(crate) fn answer(contract: Option<&Contract>, model: &Result<Model, Reason>) -> RuleAnswer {
    let mut answer = RuleAnswer::default();
    let Some(contract) = contract else {
        return answer;
    };
    if let Err(reason) = model {
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
    for outcome in outcomes(contract, model) {
        let decision = outcome.decision();
        let status = match (decision.verdict(), decision.reason()) {
            (_, Some(reason @ Reason::Unsupported(_))) => {
                answer
                    .reasons
                    .insert(outcome.rule().to_owned(), reason.clone());
                continue;
            }
            (Verdict::Pass(_), _) => "PASS",
            (Verdict::Fail, _) => "FAIL",
            (Verdict::Unknown, _) => "UNKNOWN",
        };
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
