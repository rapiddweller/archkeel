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

use crate::contract::Usable;

/// A permission declaration (`allowed_dependency`): no verdict, and it does not hold back a PASS
/// of the run (`check/run.py` `inspect_observation` reads only FAIL and UNKNOWN).
pub(crate) const DECLARATION: &str = "DECLARATION";

/// True for a rule kind that `archkeel-eval` decides (slices S1, S2, S5 and S7).
fn decided(kind: RuleKind) -> bool {
    // Each kind has an arm: a new kind does not compile without a decision here.
    match kind {
        RuleKind::CompleteAssignment
        | RuleKind::RootLayout
        | RuleKind::ExternalDependencyScope
        | RuleKind::CompleteExternalScope
        | RuleKind::ForbiddenDependency
        | RuleKind::AllowedDependency
        | RuleKind::SiblingIsolation
        | RuleKind::LayerOrder
        | RuleKind::CompleteRequires
        | RuleKind::NoComponentCycles => true,
        RuleKind::InterfaceBoundary => false,
        RuleKind::ForbiddenConstruct => false,
        RuleKind::SymbolPlacement => false,
        RuleKind::SourceOwnership => false,
        RuleKind::BoundedNumericOperand => false,
        RuleKind::CallOwner => false,
        RuleKind::ForbiddenCallArgument => false,
        RuleKind::CatalogArgument => false,
        RuleKind::CatalogUse => false,
        RuleKind::ForbiddenEffectUnderCondition => false,
        RuleKind::ProtocolDeclarations => false,
        RuleKind::BoundaryTypes => false,
    }
}

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
    /// Each PASS rule of a run with kept pair gaps: the reference engine gives it UNKNOWN, and
    /// the core proves that no kept gap can change it (AD-384 point 4).
    pub(crate) beyond: BTreeMap<String, String>,
}

/// What an inside-contract tree adds to the root rules (AD-379): the rules of its mounts, each a
/// named gap, and whether the root mounts any contract. A root rule of a tree never passes: the
/// scope proof does not read the coverage of the mounts yet.
#[derive(Debug, Default)]
pub(crate) struct Tree {
    inside: Vec<(String, RuleKind)>,
    mounted: bool,
}

impl Tree {
    /// A tree of the given inside rules and mount state (a test builds the second line alone).
    #[cfg(test)]
    pub(crate) fn new(inside: Vec<(String, RuleKind)>, mounted: bool) -> Tree {
        Tree { inside, mounted }
    }

    pub(crate) fn of(usable: &Usable) -> Tree {
        Tree {
            inside: usable.inside.clone(),
            mounted: usable.mounted,
        }
    }
}

/// The outcome of each rule, or the reason that the run has no model.
pub(crate) fn outcomes(model: Result<&Model, Reason>) -> Vec<Outcome> {
    match model {
        Ok(model) => archkeel_eval::evaluate(model),
        Err(_) => Vec::new(),
    }
}

pub(crate) fn answer(
    contract: Option<&Contract>,
    model: Result<&Model, Reason>,
    tree: Option<Tree>,
) -> RuleAnswer {
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
    let tree = tree.unwrap_or_default();
    for (id, _) in &tree.inside {
        let reason = Reason::Unsupported(Unsupported::InsideRule);
        answer.reasons.insert(id.clone(), reason);
    }
    if let Err(reason) = &model {
        for rule in contract.rules() {
            let kind = kind_of(rule);
            let reason = if decided(kind) {
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
    for outcome in outcomes(Ok(model_of)) {
        let Some(decision) = outcome.decision() else {
            // A permission declaration has no verdict (`_rule_status` `declared_only`).
            answer.decided.insert(
                outcome.rule().to_owned(),
                [word(outcome.kind()), DECLARATION.to_owned()],
            );
            continue;
        };
        let status = match (decision.verdict(), decision.reason()) {
            (_, Some(reason @ Reason::Unsupported(_))) => {
                answer
                    .reasons
                    .insert(outcome.rule().to_owned(), reason.clone());
                continue;
            }
            // AD-379: the second line after the proof. A root rule of a mounted tree never passes.
            (Verdict::Pass(_), _) if tree.mounted => {
                let reason = Reason::Unsupported(Unsupported::TreeScope);
                answer.reasons.insert(outcome.rule().to_owned(), reason);
                continue;
            }
            (Verdict::Pass(_), _) if decision.passes(model_of, outcome.rule()) => {
                let kept = model_of.kept_pair_gaps();
                if kept > 0 {
                    let why = format!("no one of the {kept} kept pair gaps can change the rule");
                    answer.beyond.insert(outcome.rule().to_owned(), why);
                }
                "PASS"
            }
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
