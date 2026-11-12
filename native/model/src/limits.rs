// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The profile limits of a contract and the layer metadata of `layer_order` (slice S4).
//!
//! Reference engine: `check/evaluation/rules.py` `profile_failures` with the table of
//! `ir/profiles.py`, `check/evaluation/crate_scope.py` `root_limits`, and `_layer_metadata_failures`
//! with `_layer_order_components`. Each limit is a coverage failure: no rule of the run passes.
//!
//! The core reads no profile table and names no language. It takes the limits that hold for
//! every profile whose reply the store accepts, and for the profiles that the store refuses
//! today. Where the profiles differ, the limit is not read and the run gives no PASS:
//!
//! - `interface_boundary` is a limit of one profile only;
//! - a symbol-level selector is a limit unless the reply has the feature after which one profile
//!   reads such selectors.
//!
//! No profile has `crate_edges_only` today, so the crate scope limits of `root_limits` are empty.

use std::collections::HashSet;

use archkeel_contract::{BudgetName, Component, Contract, LayerOrder, Rule, RuleKind};

use crate::observed::Observed;

/// The rule kinds that no store-accepted profile decides (`unsupported_rules`).
const UNDECIDED_KINDS: &[RuleKind] = &[
    RuleKind::SymbolPlacement,
    RuleKind::BoundaryTypes,
    RuleKind::CallOwner,
    RuleKind::BoundedNumericOperand,
    RuleKind::ProtocolDeclarations,
    RuleKind::ForbiddenCallArgument,
    RuleKind::CatalogArgument,
    RuleKind::CatalogUse,
    RuleKind::SourceOwnership,
    RuleKind::ForbiddenEffectUnderCondition,
];

/// The measurement budgets that no store-accepted profile measures (`unmeasured`).
const UNMEASURED: &[BudgetName] = &[
    BudgetName::PrivateCrossings,
    BudgetName::TypingPositions,
    BudgetName::CallsUnresolved,
    BudgetName::UntypedPrivateAccesses,
];

/// A part of the contract that a profile limit can hold back.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Limit {
    /// A limit of every store-accepted profile: the subject that it names.
    Certain(String),
    /// A limit of some profiles only: the subject that it names.
    Unread(String),
}

/// True for a rule kind that no store-accepted profile decides.
pub(crate) fn undecided_kind(kind: RuleKind) -> bool {
    UNDECIDED_KINDS.contains(&kind)
}

/// The profile limits of a contract, in the order of `profile_failures`.
pub(crate) fn limits(contract: &Contract, observed: &Observed) -> Vec<Limit> {
    let symbols = |subject: &str| {
        if observed.symbol_feature {
            Limit::Unread(subject.to_owned())
        } else {
            Limit::Certain(subject.to_owned())
        }
    };
    let mut found = Vec::new();
    for rule in contract.rules() {
        let id = archkeel_contract::head_of(rule).id().as_text();
        match rule {
            Rule::InterfaceBoundary(rule) => {
                if rule
                    .module_object_grants()
                    .iter()
                    .flatten()
                    .next()
                    .is_some()
                {
                    found.push(Limit::Certain(id.to_owned()));
                }
                found.push(Limit::Unread(id.to_owned()));
            }
            Rule::ForbiddenConstruct(rule) => {
                let examined: HashSet<&str> =
                    observed.constructs.iter().map(String::as_str).collect();
                let unexamined = rule
                    .constructs()
                    .iter()
                    .any(|kind| !examined.contains(word(kind).as_str()));
                if unexamined || rule.selector().is_some() {
                    found.push(Limit::Certain(id.to_owned()));
                }
            }
            Rule::ForbiddenDependency(rule) if rule.target_symbol().is_some() => {
                found.push(symbols(id));
            }
            other if undecided_kind(archkeel_contract::kind_of(other)) => {
                found.push(Limit::Certain(id.to_owned()));
            }
            _ => {}
        }
    }
    for component in contract.components() {
        let id = component.id().as_text();
        let public = component.public().iter().flatten();
        let through = component
            .requires()
            .iter()
            .flatten()
            .flat_map(|required| required.through());
        if public
            .chain(through)
            .any(|entry| entry.as_text().contains(':'))
        {
            found.push(symbols(id));
        }
    }
    if let Some(declarations) = contract.declarations() {
        let declared = [
            ("context_roots", !declarations.context_roots().is_empty()),
            (
                "facade_budgets",
                declarations
                    .facade_budgets()
                    .iter()
                    .flatten()
                    .next()
                    .is_some(),
            ),
            (
                "coupling_budgets",
                declarations
                    .coupling_budgets()
                    .iter()
                    .flatten()
                    .next()
                    .is_some(),
            ),
        ];
        for (name, _) in declared.iter().filter(|(_, declared)| *declared) {
            found.push(Limit::Certain(format!("declarations.{name}")));
        }
        for budget in declarations.measurement_budgets() {
            if UNMEASURED.contains(budget.name()) {
                found.push(Limit::Certain(format!(
                    "declarations.measurement_budgets.{}",
                    word(budget.name())
                )));
            }
        }
    }
    found
}

/// The components of a `layer_order` rule whose layer is absent or outside its order.
pub(crate) fn layer_gaps<'a>(contract: &'a Contract, rule: &LayerOrder) -> Vec<&'a Component> {
    let selected: Option<Vec<&str>> = rule
        .components()
        .as_ref()
        .map(|labels| labels.iter().map(|label| label.as_text()).collect());
    let sources: Vec<&Component> = contract
        .components()
        .iter()
        .filter(|c| {
            selected
                .as_ref()
                .is_none_or(|s| s.contains(&c.label().as_text()))
        })
        .collect();
    let targets: HashSet<&str> = sources
        .iter()
        .flat_map(|component| component.requires().iter().flatten())
        .map(|required| required.component().as_text())
        .collect();
    let ids: HashSet<&str> = sources.iter().map(|c| c.id().as_text()).collect();
    contract
        .components()
        .iter()
        .filter(|c| ids.contains(c.id().as_text()) || targets.contains(c.label().as_text()))
        .filter(|c| {
            !c.layer()
                .as_ref()
                .is_some_and(|layer| rule.layers().contains(layer))
        })
        .collect()
}

/// The word of a closed contract value (`string_literal_compare`).
fn word<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_default()
}
