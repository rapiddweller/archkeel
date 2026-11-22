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

use archkeel_contract::{
    CallOwner, CycleLevel, ForbiddenCallArgument, Lifecycle, NoComponentCycles, Rule, RuleKind,
};
use archkeel_facts::envelope::WrittenActual;
use archkeel_facts::nested::Parameter;

use crate::brand::Brand;
use crate::causes::{Cause, Part};
use crate::graph::{CallInventory, ExactCall, Graph};
use crate::model::Model;
use crate::modules::Module;
use crate::ownership::{claims, in_scope};
use crate::reason::{Reason, Unsupported};
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
    // AD-500: without a proof that the reply sees each local package, a cycle can close through
    // a package that it does not see.
    if !model.graph().observed().analysis.cycle_scope {
        return Err(
            Cause::Receipt("the collector does not prove that it sees each local package").into(),
        );
    }
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
                && roots.files().iter().all(|(name, file)| {
                    (namespace.is_empty() || in_scope(name, namespace)) && roots.under(file)
                });
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
    covered(model, &roots)?;
    ownership(model)
}

/// The receipt of an `interface_boundary` rule: the scan roots hold each component domain and
/// one component owns each module of the domain (`receipt_scope_complete` and
/// `_inside_rule_scope_is_complete` of 4.0.1, which `complete_requires` shares, AD-480).
pub(crate) fn interface(
    model: &Model,
    scan: Result<ScanProof<'_, '_>, Reason>,
) -> Result<(), Reason> {
    let ScanProof { brand: _, roots } = scan?;
    covered(model, &roots)?;
    ownership(model)?;
    // AD-428 skips a target without `public`; with none declared, the rule examined nothing.
    if model
        .components()
        .iter()
        .all(|(_, component)| component.public().is_none())
    {
        return Err(Reason::NotComplete(Cause::Receipt(
            "no component declares a public interface",
        )));
    }
    Ok(())
}

/// The scan roots hold the packages and the exact modules of each component, and, for a mount,
/// of its parent component (`source_roots`, `source_exact_modules`, AD-480).
fn covered(model: &Model, roots: &Roots<'_>) -> Result<(), Reason> {
    let contract = model.contract();
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
    Ok(())
}

/// The one ownership-completeness proof shared by dependency and interface receipts. It reads
/// the modules of the source domain of the model: every module for a root, and the modules of
/// its mount for an inside contract (`_inside_rule_scope_is_complete`, AD-480).
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
const MODULE_KINDS: [RuleKind; 9] = [
    RuleKind::BoundaryTypes,
    RuleKind::BoundedNumericOperand,
    RuleKind::CallOwner,
    RuleKind::CompleteAssignment,
    RuleKind::CompleteExternalScope,
    RuleKind::ExternalDependencyScope,
    RuleKind::RootLayout,
    RuleKind::SymbolPlacement,
    RuleKind::UnusedPublic,
];

#[cfg(test)]
#[path = "receipts_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "receipts_mount_tests.rs"]
mod mount_tests;

pub(crate) fn live_calls<'m>(
    model: &'m Model,
    rule: &CallOwner,
) -> Result<&'m CallInventory, Reason> {
    let graph = Model::graph(model);
    let scope = CallOwner::source(rule).as_text();
    let modules = Graph::modules(graph);
    let inventory = Graph::exact_calls(graph)
        .ok_or(Reason::Unsupported(Unsupported::Rule(RuleKind::CallOwner)))?;
    let selected = modules
        .iter()
        .any(|(id, module)| model.holds(id) && in_scope(Module::name(module), scope));
    let body = inventory.targets.contains(scope)
        && inventory.bodies.contains_key(scope)
        && scope.rsplit_once('.').is_some_and(|(owner, _)| {
            modules
                .iter()
                .any(|(id, module)| model.holds(id) && Module::name(module) == owner)
        });
    if !selected && !body {
        return Err(Reason::Unsupported(Unsupported::Rule(RuleKind::CallOwner)));
    }
    Ok(inventory)
}

pub(crate) fn call_allowed(rule: &CallOwner, module: &str, caller: &str) -> bool {
    rule.allowed_sources()
        .iter()
        .any(|source| in_scope(caller, source.as_text()))
        || rule
            .exact_sources()
            .iter()
            .any(|source| source.as_text() == module || source.as_text() == caller)
}

fn argument_calls<'m>(
    model: &'m Model,
    rule: &ForbiddenCallArgument,
) -> Result<(&'m CallInventory, Vec<&'m ExactCall>), Reason> {
    let graph = Model::graph(model);
    let inventory = Graph::exact_calls(graph).ok_or(Reason::Unsupported(Unsupported::Rule(
        RuleKind::ForbiddenCallArgument,
    )))?;
    let source = archkeel_contract::Selector::as_text(ForbiddenCallArgument::source(rule));
    let selected = Model::source_modules(model, source);
    if selected.is_empty() {
        return Err(Reason::NoSubjects);
    }
    let modules = Graph::modules(graph);
    let names: std::collections::HashSet<&str> = selected
        .into_iter()
        .filter_map(|id| crate::ids::Table::get(modules, id).map(Module::name))
        .collect();
    let target = archkeel_contract::Selector::as_text(ForbiddenCallArgument::target(rule));
    let calls = inventory
        .calls
        .iter()
        .filter(|(_, module, _, callee, _)| {
            names.contains(String::as_str(module)) && callee == target
        })
        .collect();
    Ok((inventory, calls))
}

/// Calls whose explicit string literal binds to the selected formal.
pub fn forbidden_argument_violations<'m>(
    model: &'m Model,
    rule: &ForbiddenCallArgument,
) -> Result<Vec<&'m ExactCall>, Reason> {
    let (inventory, calls) = argument_calls(model, rule)?;
    Ok(calls
        .into_iter()
        .filter(|call| argument_binds(inventory, rule, call) == Some(true))
        .collect())
}

pub(crate) fn argument_receipt(model: &Model, rule: &ForbiddenCallArgument) -> Result<(), Reason> {
    let (inventory, calls) = argument_calls(model, rule)?;
    let graph = Model::graph(model);
    let selected = Model::source_modules(
        model,
        archkeel_contract::Selector::as_text(ForbiddenCallArgument::source(rule)),
    );
    let modules = Graph::modules(graph);
    let complete = selected.iter().all(|id| {
        crate::ids::Table::get(modules, *id).is_some_and(|module| {
            !Module::blank(module) && inventory.complete.contains(Module::name(module))
        })
    });
    let target = std::collections::HashMap::get(
        &inventory.formals,
        archkeel_contract::Selector::as_text(ForbiddenCallArgument::target(rule)),
    );
    if complete
        && target.is_some_and(|formals| supports_arguments(formals, rule.parameter()))
        && calls
            .iter()
            .all(|call| argument_binds(inventory, rule, call).is_some())
    {
        Ok(())
    } else {
        Err(Cause::Receipt("call arguments need complete calls and proved bindings").into())
    }
}

fn argument_binds(
    inventory: &CallInventory,
    rule: &ForbiddenCallArgument,
    call: &ExactCall,
) -> Option<bool> {
    let args = std::collections::HashMap::get(&inventory.actuals, &call.0)?;
    let params = std::collections::HashMap::get(&inventory.formals, &call.3)?;
    bind_actuals(params, args, rule.parameter())
}

fn bind_actuals(params: &[Parameter], args: &[WrittenActual], name: &str) -> Option<bool> {
    if !supports_arguments(params, name) {
        return None;
    }
    let mut remaining = params.iter().filter(|param| param.kind != "keyword_only");
    let mut bound = std::collections::HashSet::new();
    let mut literal = false;
    for (keyword, is_literal) in args {
        let formal = if let Some(keyword) = keyword {
            params
                .iter()
                .find(|param| param.name == *keyword && param.kind != "positional_only")
        } else {
            remaining.next()
        }?;
        if !bound.insert(String::as_str(&formal.name)) {
            return None;
        }
        literal |= formal.name == name && *is_literal;
    }
    if params
        .iter()
        .any(|param| param.default.is_none() && !bound.contains(String::as_str(&param.name)))
    {
        return None;
    }
    Some(literal)
}

fn supports_arguments(params: &[Parameter], name: &str) -> bool {
    params.iter().any(|param| param.name == name)
        && params.iter().all(|param| {
            param.default_known
                && matches!(
                    String::as_str(&param.kind),
                    "positional_only" | "positional" | "keyword_only"
                )
        })
}
