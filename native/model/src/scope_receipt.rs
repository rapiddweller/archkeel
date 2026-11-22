// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scope proof reads about one rule (AD-363, AD-378): its receipt, its undecided
//! positions, a dynamic import that reaches it, the reason that the model rescues, the gap scope
//! of its reading and the scan proof of the model. `scope_order.rs` reads these in its one order;
//! `scope.rs` keeps the brand and the proof.

use std::collections::HashSet;

use archkeel_contract::{kind_of, CallOwner, CycleLevel, PremiseName, Rule};

use crate::causes::{Cause, Held, Part};
use crate::coverage::Incomplete;
use crate::direction;
use crate::dropped_gaps;
use crate::graph::{ExactCall, Graph};
use crate::model::Model;
use crate::modules::Module;
use crate::ownership::{in_scope, owner_of};
use crate::pair_gaps::{reads, sides_match, Reads};
use crate::reason::{Reason, Unsupported};
use crate::receipts::{call_allowed, live_calls};
use crate::receipts::{GapScope, ScanProof};
use crate::roots::Roots;
use crate::selection;
use archkeel_facts::profile_traits::Layout;

/// The gap scope of one rule, or the kept gaps that can change what it reads.
pub(crate) fn gap_scope<'id>(model: &Model, rule: &Rule) -> Result<GapScope<'id>, Reason> {
    let contract = model.contract();
    let reading = reads(rule, contract.components(), contract.rules());
    let pairs = model.pairs();
    // Dispatch can add a user, but cannot undo a known use or add an item to the inventory.
    let users_proven = match rule {
        Rule::UnusedPublic(rule) => {
            pairs
                .kept
                .iter()
                .chain(&pairs.dropped)
                .any(|gap| gap.observed && gap.dispatch)
                && model.graph().published().is_some()
                && crate::published::unused(model, rule).is_empty()
        }
        _ => false,
    };
    let reads_pair = |observed, dispatch| !(users_proven && observed && dispatch);
    let held = pairs
        .kept
        .iter()
        .filter(|gap| reads_pair(gap.observed, gap.dispatch))
        .filter(|gap| {
            if !matches!(rule, Rule::CompleteRequires(_)) || !gap.observed {
                return true;
            }
            let components = model.components();
            let owners = [
                owner_of(components, &gap.source),
                owner_of(components, &gap.target),
            ];
            let [Some(source), Some(target)] = owners else {
                return true;
            };
            if source == target {
                return false;
            }
            let Some((source, target)) = components.get(source).zip(components.get(target)) else {
                return true;
            };
            direction::assessment(source, target, &gap.target, None, false)
                != direction::Judged::Pass
        })
        .filter(|gap| gap.holds(&reading))
        .map(|gap| (gap.source.as_str(), gap.target.as_str()));
    let named = matches!(reading, Reads::Interface | Reads::SourceNames(_))
        .then(|| open_sites(model, &reading))
        .into_iter()
        .flatten();
    let mut seen = HashSet::new();
    let distinct = held
        .chain(named)
        .filter(|pair| !matches!(reading, Reads::SourceNames(_)) || seen.insert(*pair));
    if let Some(held) = Held::of(distinct) {
        return Err(Reason::NotComplete(Cause::PairGaps(held)));
    }
    let dropped = pairs
        .dropped
        .iter()
        .filter(|gap| reads_pair(gap.observed, gap.dispatch))
        .filter(|gap| dropped_gaps::holds(gap, rule, &reading))
        .map(|gap| (gap.source.as_str(), gap.target.as_str()));
    match Held::of(dropped) {
        Some(held) => Err(Reason::NotComplete(Cause::AllowedPairGaps(held))),
        None => Ok(GapScope::of()),
    }
}

/// An observed module edge does not prove the publication of a separate name.
fn open_sites<'m>(
    model: &'m Model,
    reading: &'m Reads<'_>,
) -> impl Iterator<Item = (&'m str, &'m str)> {
    let components = model.components();
    model
        .graph()
        .observed()
        .named_sites
        .iter()
        .filter_map(|((source, target), name_free)| {
            if !model.selects(source) {
                return None;
            }
            let owners = [owner_of(components, source), owner_of(components, target)];
            let relevant = match reading {
                Reads::Interface => {
                    let [Some(from), Some(to)] = owners else {
                        return None;
                    };
                    from != to && components.get(to)?.public().is_some()
                }
                Reads::SourceNames(sides) => {
                    (!name_free || owners.contains(&None))
                        && sides_match(sides, [source, target], owners.map(|owner| owner.is_some()))
                }
                _ => false,
            };
            if !relevant {
                return None;
            }
            Some((source.as_str(), target.as_str()))
        })
}

/// The scan proof of the model: the bound roots and the module files of the reply.
pub(crate) fn scan_proof<'id, 'm>(model: &'m Model) -> Result<ScanProof<'id, 'm>, Reason> {
    let graph = model.graph();
    let roots = graph.settings().roots().ok_or(Part::ScanRoots)?;
    if graph.observed().analysis.layout != Layout::ProjectFiles {
        return Err(Part::ScanLayout.into());
    }
    let files = graph
        .modules()
        .iter()
        .map(|(_, module)| (module.name(), module.file()))
        .collect();
    Ok(ScanProof::of(Roots::new(roots, files)))
}

/// The receipt of a rule (`rules.py` `_rule_evaluation_facts_for_rule`): the rule selects a
/// module of the reply. Only the kinds that the evaluator decides have one here.
pub(crate) fn receipt(model: &Model, rule: &Rule) -> Result<(), Reason> {
    // `_observed_rule_modules`: the modules of the source domain of the model (AD-385).
    let observed = || {
        model
            .graph()
            .modules()
            .iter()
            .filter(|(id, _)| model.holds(*id))
    };
    let selected = match rule {
        Rule::CompleteAssignment(rule) | Rule::CompleteExternalScope(rule) => {
            !model.source_modules(rule.source().as_text()).is_empty()
        }
        Rule::RootLayout(rule) => {
            observed().any(|(_, module)| in_scope(module.name(), rule.root().as_text()))
        }
        Rule::ExternalDependencyScope(rule) => {
            observed().next().is_some()
                && direction::dependency_named(model, rule.dependency().as_text()).map(|()| true)?
        }
        Rule::InterfaceBoundary(_) => observed().next().is_some(),
        Rule::ForbiddenConstruct(rule) => {
            if Option::is_some(&crate::construct_match::receipt(model, rule)?)
                && !archkeel_contract::declared_premises(model.contract())
                    .contains(&PremiseName::StandardLibraryUnchanged)
            {
                return Err(Reason::NotComplete(Cause::Receipt(
                    "Protocol declarations need standard_library_unchanged",
                )));
            }
            true
        }
        // Slice S5 (AD-380), `_rule_evaluation_facts_for_rule`.
        // An undecided position (`symbol_limits`) withholds the receipt as well.
        Rule::ForbiddenDependency(rule) => {
            let judged = direction::forbidden(model, rule)
                .into_iter()
                .map(|(_, j)| j);
            undecided(direction::undecided(judged))?;
            direction::symbol_named(model, rule)?;
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            observed().any(|(_, module)| sources.matches(module.name()))
        }
        Rule::SiblingIsolation(rule) => observed().any(|(_, module)| {
            rule.members()
                .iter()
                .any(|member| in_scope(module.name(), member.as_text()))
        }),
        // `_layer_order_evaluation_facts`: the selected components; the receipt cites the
        // contract file (`_layer_order_evidence`). The layer gaps are a cause of the state.
        Rule::LayerOrder(rule) => {
            // AD-385: the receipt of an inside rule cites the file of the inside contract.
            if model.is_mount() {
                return Err(Part::MountedLayerOrder.into());
            }
            let digest = model.contract().digest().as_text();
            if model.graph().settings().contract_evidence(digest).is_none() {
                return Err(Part::ContractSource.into());
            }
            !selection::layer_components(model.contract(), rule).is_empty()
        }
        // `scope_receipts_complete` reads the scan roots: `receipts::requires` (slice S7).
        Rule::CompleteRequires(rule) => {
            let judged = direction::crossings(model, rule)
                .into_iter()
                .map(|c| c.judged);
            undecided(direction::undecided(judged))?;
            true
        }
        // AD-550: the rule has its receipt when its surface has no named gap.
        Rule::BoundaryTypes(rule) => {
            crate::boundary_positions::receipt(model, rule)?;
            true
        }
        Rule::SymbolPlacement(rule) => {
            placement_receipt(model, rule)?;
            true
        }
        // AD-670: an item that another component may use without a proven import holds it back.
        Rule::UnusedPublic(rule) => crate::published::receipt(model, rule)?,
        Rule::CallOwner(rule) => {
            call_owner_receipt(model, rule)?;
            true
        }
        Rule::ForbiddenCallArgument(rule) => {
            crate::receipts::argument_receipt(model, rule)?;
            true
        }
        Rule::ProtocolDeclarations(rule) => {
            crate::gap_effects::protocol_receipt(model, rule)?;
            true
        }
        // Each kind that no slice decides: its slice states its receipt here (AD-378). A
        // permission declaration (`allowed_dependency`) has no verdict, so it has no receipt.
        other @ (Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::AllowedDependency(_)
        | Rule::SourceOwnership(_)
        | Rule::NoComponentCycles(_)
        | Rule::BoundedNumericOperand(_)) => {
            // `receipts::cycle` gives the receipt of `no_component_cycles` (slice S7).
            return Err(Reason::Unsupported(Unsupported::Rule(kind_of(other))));
        }
    };
    if selected {
        Ok(())
    } else {
        Err(Reason::NoSubjects)
    }
}

/// The proved calls that break this rule, even if another call is open.
pub fn call_owner_violations<'m>(
    model: &'m Model,
    rule: &CallOwner,
) -> Result<Vec<&'m ExactCall>, Reason> {
    let inventory = live_calls(model, rule)?;
    let scope = CallOwner::source(rule).as_text();
    let target = CallOwner::target(rule).as_text();
    let module_scope = Graph::modules(Model::graph(model))
        .iter()
        .any(|(id, module)| model.holds(id) && in_scope(Module::name(module), scope));
    Ok(inventory
        .calls
        .iter()
        .filter(|(_, module, caller, callee, _)| {
            model.selects(module)
                && (in_scope(module, scope)
                    || (!module_scope
                        && inventory.bodies.contains_key(scope)
                        && in_scope(caller, scope)))
                && callee == target
                && !call_allowed(rule, module, caller)
        })
        .collect())
}

fn call_owner_receipt(model: &Model, rule: &CallOwner) -> Result<(), Reason> {
    let inventory = live_calls(model, rule)?;
    if !inventory
        .targets
        .contains(CallOwner::target(rule).as_text())
    {
        return Err(Cause::Receipt("call ownership needs an exact target declaration").into());
    }
    let graph = Model::graph(model);
    let scope = CallOwner::source(rule).as_text();
    let mut nonempty = false;
    let modules = Graph::modules(graph);
    for (id, module) in modules.iter() {
        let name = Module::name(module);
        if !model.holds(id) || !in_scope(name, scope) {
            continue;
        }
        nonempty |= !Module::blank(module);
        if !call_allowed(rule, name, name) && !inventory.complete.contains(name) {
            return Err(
                Cause::Receipt("call ownership: a selected call has no exact target").into(),
            );
        }
    }
    if !nonempty {
        if modules
            .iter()
            .any(|(id, module)| model.holds(id) && in_scope(Module::name(module), scope))
        {
            return Err(Reason::NoSubjects);
        }
        let Some(total) = std::collections::HashMap::get(&inventory.bodies, scope) else {
            return Err(Reason::NoSubjects);
        };
        let found = inventory
            .calls
            .iter()
            .filter(|(_, _, caller, _, _)| caller == scope)
            .map(|(site, ..)| 1 + u64::from(inventory.constructors.contains(site)))
            .sum::<u64>();
        if found != *total {
            return Err(
                Cause::Receipt("call ownership: a selected call has no exact target").into(),
            );
        }
    }
    Ok(())
}

fn placement_receipt(
    model: &Model,
    rule: &archkeel_contract::SymbolPlacement,
) -> Result<(), Reason> {
    let modules = model.source_modules(rule.source().as_text());
    if modules.is_empty() {
        return Err(Reason::NoSubjects);
    }
    crate::graph::Graph::placement(model.graph()).ok_or(Reason::Unsupported(Unsupported::Rule(
        archkeel_contract::RuleKind::SymbolPlacement,
    )))?;
    let found = modules
        .iter()
        .map(|id| crate::ids::Table::get(model.graph().modules(), *id));
    let missing: Vec<_> = found
        .filter(|found| {
            found.is_none_or(|module| {
                let allowed = rule
                    .allowed_sources()
                    .iter()
                    .any(|source| in_scope(module.name(), source.as_text()))
                    || rule
                        .exact_sources()
                        .iter()
                        .any(|source| module.name() == source.as_text());
                !allowed && !module.class_inventory_empty()
            })
        })
        .collect();
    if !missing.is_empty() {
        // #1713: a call that can create a class names its site.
        let site = (missing.into_iter().flatten()).find_map(|module| module.class_inventory_site());
        return Err(Reason::NotComplete(match site {
            Some(site) => Cause::ClassSite(site.to_owned()),
            None => Cause::Receipt("symbol placement: class inventory is incomplete"),
        }));
    }
    Ok(())
}

/// An undecided position is a fact: the reference engine gives UNKNOWN (`_rule_status`).
fn undecided(count: usize) -> Result<(), Reason> {
    if count > 0 {
        Err(Reason::NotComplete(Cause::Undecided(count)))
    } else {
        Ok(())
    }
}

/// True when an unresolved dynamic import reaches the rule (`dynamic_dependency_limits`): the
/// reference engine leaves the rule without its receipt. A limit without a source module stops
/// the reference engine, so it reaches each rule.
pub(crate) fn dynamic_import(model: &Model, rule: &Rule) -> bool {
    let reaches = |source: Source<'_>| match rule {
        Rule::ExternalDependencyScope(rule) => {
            !(rule
                .exact_sources()
                .iter()
                .any(|exact| exact.as_text() == source.module)
                || rule
                    .allowed_sources()
                    .iter()
                    .any(|allowed| in_scope(source.module, allowed.as_text())))
        }
        Rule::CompleteExternalScope(rule) => in_scope(source.module, rule.source().as_text()),
        // Slice S5 (AD-380): a rule that leaves out type-only imports does not see a type-only
        // limit (`rule_support.py:200`).
        Rule::ForbiddenDependency(rule) => {
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            sources.matches(source.module)
                && !rule
                    .allowed_sources()
                    .iter()
                    .any(|allowed| allowed.as_text() == source.module)
                && !(source.type_only && !rule.include_type_checking())
        }
        Rule::SiblingIsolation(rule) => {
            rule.members()
                .iter()
                .any(|member| in_scope(source.module, member.as_text()))
                && !(source.type_only && !rule.include_type_checking())
        }
        Rule::CompleteRequires(rule) => {
            owner_of(model.components(), source.module).is_some()
                && !(source.type_only && !rule.include_type_checking())
        }
        Rule::InterfaceBoundary(rule) => {
            owner_of(model.components(), source.module).is_some()
                && !(source.type_only && !rule.include_type_checking())
        }
        // Slice S7: a module cycle can close through any module; a component cycle through an
        // owned module. The type-only flag does not narrow a cycle rule.
        Rule::NoComponentCycles(rule) => {
            *rule.level() == CycleLevel::Module
                || owner_of(model.components(), source.module).is_some()
        }
        // `dynamic_dependency_limits` does not read these kinds.
        Rule::CompleteAssignment(_)
        | Rule::RootLayout(_)
        | Rule::LayerOrder(_)
        | Rule::AllowedDependency(_) => false,
        Rule::ForbiddenConstruct(_) => false,
        // A kind that no slice decides has no receipt; its slice states its limits here. Until
        // then a dynamic import reaches it (fail closed).
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::SourceOwnership(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::UnusedPublic(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_) => true,
    };
    model
        .graph()
        .observed()
        .dynamic_imports
        .iter()
        .any(|limit| {
            // `dynamic_dependency_limits(source_modules=...)`: a mount reads only the limits of
            // its domain. A limit without a source module stops the reference engine.
            limit.source.as_deref().is_none_or(|module| {
                model.selects(module)
                    && reaches(Source {
                        module,
                        type_only: limit.type_only(),
                    })
            })
        })
}

/// The source module of a dynamic import limit and its type-only flag.
struct Source<'a> {
    module: &'a str,
    type_only: bool,
}

/// The reason of an incomplete state for one rule. A coverage gap holds `complete_requires`:
/// the core cannot prove the dependency scope. The former host could accept such a gap (AD-418).
/// Other gaps keep their existing treatment when the runtime could carry the host proof.
pub(crate) fn rescued(model: &Model, rule: &Rule, reason: &Reason) -> Reason {
    if matches!(reason, Reason::Incomplete(Incomplete::CoverageGaps { .. }))
        && matches!(rule, Rule::CompleteRequires(_))
        && model.graph().observed().scope_receipt
    {
        return Cause::DependencyScopeUnproven.into();
    }
    let accepted = matches!(
        reason,
        Reason::Incomplete(Incomplete::UnknownImports(_)) | Reason::NotComplete(Cause::PairGaps(_))
    );
    let carried = model.graph().observed().scope_receipt;
    if accepted && carried && matches!(rule, Rule::CompleteRequires(_)) {
        Part::ScopedRequires.into()
    } else {
        reason.clone()
    }
}
