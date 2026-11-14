// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The profile limits of a contract and the layer metadata of `layer_order` (slice S4).
//!
//! Reference engine: `check/evaluation/rules.py` `profile_failures` with the table of
//! `ir/profiles.py`, `check/evaluation/crate_scope.py` `root_limits`, and `_layer_metadata_failures`
//! with `_layer_order_components`. Each limit is a coverage failure: no rule of the run passes.
//!
//! The core reads no profile table and names no language. The linked collector states the
//! profile differences as typed data. Without those statements the run stays conservative:
//!
//! - `interface_boundary` is a limit of one profile only;
//! - a symbol-level selector is a limit unless the reply has the feature after which one profile
//!   reads such selectors.
//!
//! No profile has `crate_edges_only` today, so the crate scope limits of `root_limits` are empty.
//!
//! AD-474: a feature that the linked collector states as unsupported is not a limit of the run.
//! It holds only each rule that reads it: `symbol_reader` gives the symbol selector that a rule
//! reads, and `interface::receipt` refuses each `interface_boundary` rule without the feature.

use std::collections::HashSet;

use archkeel_contract::{BudgetName, Component, Contract, LayerOrder, Rule, RuleKind};
use archkeel_facts::envelope::LimitSupport;

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
    let symbols = |subject: &str| symbol_limit(observed, subject);
    let mut found = Vec::new();
    for rule in contract.rules() {
        rule_limits(rule, observed, &mut found);
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
            found.extend(symbols(id));
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

/// A limit of a store-accepted profile for one rule. A stated unsupported feature is not a limit
/// of the run: `stated_hold` holds each rule that reads the selector (AD-474).
fn symbol_limit(observed: &Observed, subject: &str) -> Option<Limit> {
    match observed
        .profile_limits
        .map(|limits| limits.dependency_symbols)
    {
        Some(LimitSupport::Supported | LimitSupport::Unsupported) => None,
        None if observed.symbol_feature => Some(Limit::Unread(subject.to_owned())),
        None => Some(Limit::Certain(subject.to_owned())),
    }
}

/// What the evaluation of one rule reads besides the module-level import edges (AD-474).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Reads {
    /// No store-accepted profile decides the kind (`unsupported_rules`).
    Undecided,
    /// The source constructs (`forbidden_construct`).
    Constructs,
    /// The `target_symbol` of the rule itself (`direction::forbidden`).
    OwnSymbol,
    /// The `through` ports of each component (`direction::crossings`).
    Ports,
    /// The module interface: the `public` entries of each component and the verdicts of each
    /// `target_symbol` rule (`interface::assess`, `interface::interface_crossings`).
    Interface,
    /// Only the module-level import edges.
    Edges,
}

/// What one rule reads. The match has no catch-all arm: a new rule kind does not compile until
/// it states what it reads, so it cannot forget a limit.
fn reads(rule: &Rule) -> Reads {
    match rule {
        Rule::InterfaceBoundary(_) => Reads::Interface,
        Rule::ForbiddenConstruct(_) => Reads::Constructs,
        Rule::ForbiddenDependency(rule) if rule.target_symbol().is_some() => Reads::OwnSymbol,
        Rule::CompleteRequires(_) => Reads::Ports,
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::SourceOwnership(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_) => Reads::Undecided,
        Rule::ForbiddenDependency(_)
        | Rule::AllowedDependency(_)
        | Rule::ExternalDependencyScope(_)
        | Rule::CompleteAssignment(_)
        | Rule::RootLayout(_)
        | Rule::CompleteExternalScope(_)
        | Rule::LayerOrder(_)
        | Rule::NoComponentCycles(_)
        | Rule::SiblingIsolation(_) => Reads::Edges,
    }
}

/// The limits of one rule, in the order of `profile_failures`.
fn rule_limits(rule: &Rule, observed: &Observed, found: &mut Vec<Limit>) {
    let id = archkeel_contract::head_of(rule).id().as_text();
    match (reads(rule), rule) {
        (Reads::Interface, _) => {
            match observed
                .profile_limits
                .map(|limits| limits.interface_boundary)
            {
                // AD-474: `interface::receipt` refuses this rule alone without the feature.
                Some(LimitSupport::Supported | LimitSupport::Unsupported) => {}
                None => found.push(Limit::Unread(id.to_owned())),
            }
        }
        (Reads::Constructs, Rule::ForbiddenConstruct(rule)) => {
            let examined: HashSet<&str> = observed.constructs.iter().map(String::as_str).collect();
            let unexamined = rule
                .constructs()
                .iter()
                .any(|kind| !examined.contains(word(kind).as_str()));
            if unexamined || (rule.selector().is_some() && !observed.construct_selectors) {
                found.push(Limit::Certain(id.to_owned()));
            }
        }
        (Reads::OwnSymbol, _) => found.extend(symbol_limit(observed, id)),
        (Reads::Undecided, _) => found.push(Limit::Certain(id.to_owned())),
        // No store-accepted profile limits these kinds (`profile_failures`).
        (Reads::Constructs | Reads::Ports | Reads::Edges, _) => {}
    }
}

/// The symbol selector that holds one rule when the linked collector states that it reads no
/// dependency symbol (AD-474), or `None` when the rule reads none. The interface statement has
/// one reader only, and `interface::receipt` reads it on the evaluation path of that rule.
pub(crate) fn stated_hold(contract: &Contract, rule: &Rule, observed: &Observed) -> Option<String> {
    let stated = observed.profile_limits?.dependency_symbols;
    (stated == LimitSupport::Unsupported)
        .then(|| symbol_reader(contract, rule))
        .flatten()
}

/// The first symbol selector of the contract that the evaluation of `rule` reads (`reads`), by
/// its subject: a `target_symbol` rule, a component with a `through` symbol port or a component
/// with a `public` symbol entry. Each other kind reads no symbol fact.
pub(crate) fn symbol_reader(contract: &Contract, rule: &Rule) -> Option<String> {
    let components = contract.components();
    let symbolic = |entry: &str| entry.contains(':');
    let ports = || {
        components
            .iter()
            .filter(|c| {
                c.requires()
                    .iter()
                    .flatten()
                    .flat_map(|required| required.through())
                    .any(|port| symbolic(port.as_text()))
            })
            .map(|c| c.id().as_text().to_owned())
    };
    let publics = || {
        components
            .iter()
            .filter(|c| c.public().iter().flatten().any(|e| symbolic(e.as_text())))
            .map(|c| c.id().as_text().to_owned())
    };
    let selectors = || {
        contract
            .rules()
            .iter()
            .filter(|other| reads(other) == Reads::OwnSymbol)
            .map(|other| archkeel_contract::head_of(other).id().as_text().to_owned())
    };
    match reads(rule) {
        Reads::OwnSymbol => Some(archkeel_contract::head_of(rule).id().as_text().to_owned()),
        Reads::Ports => ports().next(),
        Reads::Interface => publics().chain(selectors()).next(),
        Reads::Undecided | Reads::Constructs | Reads::Edges => None,
    }
}

/// The components of a `layer_order` rule whose layer is absent or outside its order.
pub(crate) fn layer_gaps<'a>(contract: &'a Contract, rule: &LayerOrder) -> Vec<&'a Component> {
    crate::selection::layer_components(contract, rule)
        .into_iter()
        .filter(|c| {
            !c.layer()
                .as_ref()
                .is_some_and(|layer| rule.layers().contains(layer))
        })
        .collect()
}

/// The word of a closed contract value (`string_literal_compare`).
pub(crate) fn word<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_default()
}

#[cfg(test)]
#[path = "limits_tests.rs"]
mod tests;
