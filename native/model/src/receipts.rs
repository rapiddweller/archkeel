// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receipts of slice S7 and the two proofs that they read (AD-384).
//!
//! - `GapScope`: no kept pair gap can change what one rule reads (`pair_gaps.rs`). Only
//!   `Scope::gaps` (`scope.rs`) makes one, with the brand of its model.
//! - `ScanProof`: the scan roots of the settings, bound to the scope of the reply, and a profile
//!   whose module files the core maps (`Layout::ProjectFiles`). Only `Scope::scan` makes one.
//!
//! The cycle receipts are `rules.py` `_component_cycle_violations` and `_module_cycle_violations`
//! with `_cycle_scan_coverage`; the receipt of `complete_requires` is `scope_receipts_complete`
//! with `_inside_rule_scope_is_complete`. The reference engine gives the cycle receipt only when
//! the coverage has no gap and no failure (`evaluate.py:1229`): that is the scope state and the
//! gap scope, which `Scope::complete` checks first.

use archkeel_contract::{CycleLevel, Lifecycle, NoComponentCycles, Rule, RuleKind};

use crate::brand::Brand;
use crate::causes::{Cause, Part};
use crate::model::Model;
use crate::ownership::{claims, in_scope};
use crate::reason::Reason;
use crate::roots::Roots;

/// The proof that no kept pair gap can change what one rule of the model of `'id` reads.
#[derive(Debug)]
pub struct GapScope<'id> {
    brand: Brand<'id>,
}

/// The proof that the scan roots of the model of `'id` are the roots of its reply.
#[derive(Debug)]
pub struct ScanProof<'id, 'm> {
    brand: Brand<'id>,
    roots: Roots<'m>,
}

impl GapScope<'_> {
    /// The proof of a rule that no kept gap holds (`Scope::gaps` checks it).
    pub(crate) fn of() -> Self {
        GapScope {
            brand: std::marker::PhantomData,
        }
    }

    /// Use the proof up: one gap scope stands for one rule.
    pub(crate) fn spent(self) {
        let GapScope { brand: _ } = self;
    }
}

impl<'id, 'm> ScanProof<'id, 'm> {
    /// The proof of bound roots over the module files of the reply (`Scope::scan` checks it).
    pub(crate) fn of(roots: Roots<'m>) -> Self {
        ScanProof {
            brand: std::marker::PhantomData,
            roots,
        }
    }
}

/// True when the contract has a planned component.
fn planned(model: &Model) -> bool {
    model
        .contract()
        .components()
        .iter()
        .any(|component| component.lifecycle() == &Some(Lifecycle::Planned))
}

/// The receipt of a `no_component_cycles` rule. A rule that selects no owned module has none.
pub(crate) fn cycle(
    model: &Model,
    rule: &NoComponentCycles,
    scan: Result<ScanProof<'_, '_>, Reason>,
) -> Result<(), Reason> {
    let selected = |label: &str| {
        rule.components()
            .as_ref()
            .is_none_or(|labels| labels.iter().any(|l| l.as_text() == label))
    };
    let modules = model.graph().modules();
    match rule.level() {
        CycleLevel::Component => {
            let any = modules.iter().any(|(id, _)| {
                model
                    .owner(id)
                    .and_then(|owner| model.components().get(owner))
                    .is_some_and(|component| selected(component.label().as_text()))
            });
            if !any {
                return Err(Reason::NoSubjects);
            }
            let ScanProof { brand: _, roots } = scan?;
            // `cycle_graph_components` holds every component, and the contract has one.
            let components = model.contract().components();
            let covered = components.iter().all(|component| {
                let packages: Vec<&str> =
                    component.packages().iter().map(|p| p.as_text()).collect();
                let exact: Vec<&str> = component
                    .exact_modules()
                    .iter()
                    .map(|e| e.as_text())
                    .collect();
                component.lifecycle() != &Some(Lifecycle::Planned)
                    && roots.covers(&packages, &exact)
            });
            if components.is_empty() || !covered {
                return Err(Cause::Receipt(
                    "a component is planned or lies outside the scan roots",
                )
                .into());
            }
        }
        CycleLevel::Module => {
            let scope: Vec<_> = model
                .contract()
                .components()
                .iter()
                .filter(|component| selected(component.label().as_text()))
                .collect();
            let any = modules.iter().any(|(_, module)| {
                rule.components().is_none() || scope.iter().any(|c| claims(c, module.name()))
            });
            if !any {
                return Err(Reason::NoSubjects);
            }
            let ScanProof { brand: _, roots } = scan?;
            let namespace = model.graph().settings().namespace();
            let inside = !roots.files().is_empty()
                && roots
                    .files()
                    .iter()
                    .all(|(name, file)| in_scope(name, namespace) && roots.under(file));
            if !inside {
                return Err(Cause::Receipt(
                    "a module lies outside the namespace or the scan roots",
                )
                .into());
            }
            if planned(model) {
                return Err(Cause::Receipt("the contract has a planned component").into());
            }
        }
    }
    Ok(())
}

/// The receipt of a `complete_requires` rule: the scan roots hold each component domain, the
/// collector read each selected file, and one component owns each module of the reply.
pub(crate) fn requires(
    model: &Model,
    scan: Result<ScanProof<'_, '_>, Reason>,
) -> Result<(), Reason> {
    let ScanProof { brand: _, roots } = scan?;
    let contract = model.contract();
    if contract.rules().iter().any(selector_source) {
        return Err(Part::ReceiptSources.into());
    }
    if !model.graph().observed().inventory_complete {
        return Err(
            Cause::Receipt("the collector did not read and parse each selected file").into(),
        );
    }
    // AD-476: the scan roots must also hold the packages and exact modules of the parent of a
    // mount (`source_roots`, `source_exact_modules`); a root has none.
    let (parent_packages, parent_exact) = model.parent_scopes();
    let packages: Vec<&str> = parent_packages
        .iter()
        .map(String::as_str)
        .chain(
            contract
                .components()
                .iter()
                .flat_map(|component| component.packages())
                .map(|package| package.as_text()),
        )
        .collect();
    let exact: Vec<&str> = parent_exact
        .iter()
        .map(String::as_str)
        .chain(
            contract
                .components()
                .iter()
                .flat_map(|component| component.exact_modules())
                .map(|exact| exact.as_text()),
        )
        .collect();
    if !roots.covers(&packages, &exact) {
        return Err(Cause::Receipt("a component domain lies outside the scan roots").into());
    }
    ownership(model)
}

/// The one ownership-completeness proof shared by dependency and interface receipts. It reads
/// the modules of the source domain of the model: every module for a root, and the modules of
/// its mount for an inside contract (`_inside_rule_scope_is_complete`, AD-476).
pub(crate) fn ownership(model: &Model) -> Result<(), Reason> {
    let modules: Vec<_> = model
        .graph()
        .modules()
        .iter()
        .filter(|(id, _)| model.holds(*id))
        .collect();
    if modules.is_empty() {
        return Err(Reason::NoSubjects);
    }
    if planned(model) {
        return Err(Cause::Receipt("the contract has a planned component").into());
    }
    if modules.iter().any(|(id, _)| model.owner(*id).is_none()) {
        return Err(Cause::Receipt("a module has not exactly one owner").into());
    }
    Ok(())
}

/// The kinds of the edges whose rules add no receipt scope (`scope_receipts_complete`).
const EDGE_KINDS: [RuleKind; 7] = [
    RuleKind::AllowedDependency,
    RuleKind::CompleteRequires,
    RuleKind::ForbiddenDependency,
    RuleKind::InterfaceBoundary,
    RuleKind::LayerOrder,
    RuleKind::NoComponentCycles,
    RuleKind::SiblingIsolation,
];

/// A rule whose source `scope_receipts_complete` adds to the receipt scopes. A kind outside the
/// two lists adds one (fail closed); `forbidden_construct` adds one with a selector.
fn selector_source(rule: &Rule) -> bool {
    let kind = archkeel_contract::kind_of(rule);
    match rule {
        Rule::ForbiddenConstruct(rule) => rule.selector().is_some(),
        _ => !(EDGE_KINDS.contains(&kind) || MODULE_KINDS.contains(&kind)),
    }
}

/// The kinds of the modules, symbols and imports whose rules add no receipt scope.
const MODULE_KINDS: [RuleKind; 8] = [
    RuleKind::BoundaryTypes,
    RuleKind::BoundedNumericOperand,
    RuleKind::CallOwner,
    RuleKind::CompleteAssignment,
    RuleKind::CompleteExternalScope,
    RuleKind::ExternalDependencyScope,
    RuleKind::RootLayout,
    RuleKind::SymbolPlacement,
];

impl From<Cause> for Reason {
    fn from(cause: Cause) -> Reason {
        Reason::NotComplete(cause)
    }
}

#[cfg(test)]
#[path = "receipts_tests.rs"]
mod tests;
