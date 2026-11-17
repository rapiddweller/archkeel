// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The profile limits of a contract and the layer metadata of `layer_order` (slice S4).
//!
//! Reference engine: `check/evaluation/rules.py` `profile_failures` with the table of
//! `ir/profiles.py`, `check/evaluation/crate_scope.py` `root_limits`, and `_layer_metadata_failures`
//! with `_layer_order_components`. The reference engine makes each limit a coverage failure: no
//! rule of the run passes.
//!
//! AD-644: a limit holds only what reads the part that it makes unknown. `rule_limit` gives the
//! limit that holds one rule: its own construct, kind or shape limit, or a symbol selector that it
//! reads (`symbol_reader`). `run_limits` gives the limits that hold the run and no rule: the
//! declarations that no rule reads and the symbol entries of the components. The scope proof
//! (`run.rs`, `Scope::hold_rule` and `Scope::hold_run`) turns a limit into a reason.
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
//! AD-500: a feature that the linked collector states as unsupported is not a limit of the run.
//! It holds only each rule that reads it: `symbol_reader` gives the symbol selector that a rule
//! reads, and `interface::receipt` refuses each `interface_boundary` rule without the feature.

use std::collections::HashSet;

use archkeel_contract::{BudgetName, Component, Contract, LayerOrder, Rule, RuleKind};
use archkeel_facts::envelope::LimitSupport;

use crate::observed::Observed;

/// The rule kinds that no store-accepted profile decides (`unsupported_rules`).
const UNDECIDED_KINDS: &[RuleKind] = &[
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

/// The profile limits that hold the run and no rule (AD-644), in the order of
/// `profile_failures`: a symbol entry of a component (a rule that reads it is held by
/// `rule_limit`), and a declaration that no rule reads. The core decides no declaration, so each
/// one keeps the run UNKNOWN.
pub(crate) fn run_limits(contract: &Contract, observed: &Observed) -> Vec<Limit> {
    let symbols = |subject: &str| symbol_limit(observed, subject);
    let mut found = Vec::new();
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

/// The profile limit that holds one rule (AD-644): the limit of the rule itself (`own_limit`),
/// else the limit of the first symbol selector that the rule reads (`symbol_reader`). Each other
/// limit makes unknown a part that this rule does not read.
pub(crate) fn rule_limit(contract: &Contract, rule: &Rule, observed: &Observed) -> Option<Limit> {
    own_limit(rule, observed).or_else(|| {
        symbol_reader(contract, rule).and_then(|subject| symbol_limit(observed, &subject))
    })
}

/// A limit of a store-accepted profile for one rule. A stated unsupported feature is not a limit
/// of the run: `stated_hold` holds each rule that reads the selector (AD-500).
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

/// What the evaluation of one rule reads besides the module-level import edges (AD-500).
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
    /// The shapes of the written signature types (`boundary_types`, AD-550).
    Shapes,
    /// The public symbols of the modules and every import (`unused_public`, AD-670).
    Published,
    /// The class inventory and class symbols.
    Placement,
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
        undecided_rule!() => Reads::Undecided,
        Rule::BoundaryTypes(_) => Reads::Shapes,
        Rule::UnusedPublic(_) => Reads::Published,
        Rule::SymbolPlacement(_) => Reads::Placement,
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

/// The limit of the part that only this rule reads (AD-644): its unexamined constructs, its
/// kind that no profile decides, its shapes, or its interface. A symbol selector is read by more
/// rules (`symbol_reader`), so `rule_limit` gives it.
fn own_limit(rule: &Rule, observed: &Observed) -> Option<Limit> {
    let id = archkeel_contract::head_of(rule).id().as_text().to_owned();
    match (reads(rule), rule) {
        (Reads::Interface, _) => match observed
            .profile_limits
            .map(|limits| limits.interface_boundary)
        {
            // AD-500: `interface::receipt` refuses this rule alone without the feature.
            Some(LimitSupport::Supported | LimitSupport::Unsupported) => None,
            None => Some(Limit::Unread(id)),
        },
        // The subject names what the collector lacks, so the row says why it is held.
        (Reads::Constructs, Rule::ForbiddenConstruct(rule)) => {
            let examined: HashSet<&str> = observed.constructs.iter().map(String::as_str).collect();
            let unexamined: Vec<String> = rule
                .constructs()
                .iter()
                .map(word)
                .filter(|kind| !examined.contains(kind.as_str()))
                .collect();
            if !unexamined.is_empty() {
                let words = unexamined.join(", ");
                Some(Limit::Certain(format!(
                    "{id}: the collector examines no {words}"
                )))
            } else if rule.selector().is_some() && !observed.construct_selectors {
                let lack = "the collector reads no construct selector";
                Some(Limit::Certain(format!("{id}: {lack}")))
            } else {
                None
            }
        }
        (Reads::Undecided, _) => Some(Limit::Certain(id)),
        // AD-550: a profile whose collector writes no shape cannot read the types.
        (Reads::Shapes, _) if !observed.type_shapes => Some(Limit::Certain(id)),
        // AD-670: an absent symbol record may be an item that nobody uses, so a PASS needs every
        // public symbol; a violation that the model sees stays FAIL (AD-718).
        (Reads::Published, _) if !observed.public_symbols => Some(Limit::Certain(format!(
            "{id}: the collector does not state every public symbol"
        ))),
        // No store-accepted profile limits these kinds (`profile_failures`); `rule_limit` gives
        // the limit of the own symbol of a `target_symbol` rule.
        (
            Reads::Constructs
            | Reads::OwnSymbol
            | Reads::Ports
            | Reads::Edges
            | Reads::Shapes
            | Reads::Published
            | Reads::Placement,
            _,
        ) => None,
    }
}

/// The symbol selector that holds one rule when the linked collector states that it reads no
/// dependency symbol (AD-500), or `None` when the rule reads none. The interface statement has
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
fn symbol_reader(contract: &Contract, rule: &Rule) -> Option<String> {
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
        // AD-670: without the names of the imports, every item would look unused.
        Reads::Published => Some(archkeel_contract::head_of(rule).id().as_text().to_owned()),
        Reads::Undecided | Reads::Constructs | Reads::Edges | Reads::Shapes | Reads::Placement => {
            None
        }
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
