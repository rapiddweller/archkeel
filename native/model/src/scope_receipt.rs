// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scope proof reads about one rule (AD-363, AD-378): its receipt, its undecided
//! positions, a dynamic import that reaches it, the reason that the model rescues, the gap scope
//! of its reading and the scan proof of the model. `scope_order.rs` reads these in its one order;
//! `scope.rs` keeps the brand and the proof.

use archkeel_contract::{kind_of, CycleLevel, Rule};

use crate::causes::{Cause, Held, Part};
use crate::coverage::Incomplete;
use crate::direction;
use crate::dropped_gaps;
use crate::model::Model;
use crate::ownership::{in_scope, owner_of};
use crate::pair_gaps::reads;
use crate::reason::{Reason, Unsupported};
use crate::receipts::{GapScope, ScanProof};
use crate::roots::Roots;
use crate::selection;
use archkeel_facts::profile_traits::Layout;

/// The gap scope of one rule, or the kept gaps that can change what it reads.
pub(crate) fn gap_scope<'id>(model: &Model, rule: &Rule) -> Result<GapScope<'id>, Reason> {
    let reading = reads(rule, model.contract().components());
    let held = model
        .pairs()
        .kept
        .iter()
        .filter(|gap| gap.holds(&reading))
        .map(|gap| (gap.source.as_str(), gap.target.as_str()));
    if let Some(held) = Held::of(held) {
        return Err(Reason::NotComplete(Cause::PairGaps(held)));
    }
    let dropped = model
        .pairs()
        .dropped
        .iter()
        .filter(|gap| dropped_gaps::holds(gap, rule, &reading))
        .map(|gap| (gap.source.as_str(), gap.target.as_str()));
    match Held::of(dropped) {
        Some(held) => Err(Reason::NotComplete(Cause::AllowedPairGaps(held))),
        None => Ok(GapScope::of()),
    }
}

/// The scan proof of the model: the bound roots and the module files of the reply.
pub(crate) fn scan_proof<'id, 'm>(model: &'m Model) -> Result<ScanProof<'id, 'm>, Reason> {
    let graph = model.graph();
    let roots = graph.settings().roots().ok_or(Part::ScanRoots)?;
    if graph.observed().layout != Layout::ProjectFiles {
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
        Rule::ExternalDependencyScope(_) => observed().next().is_some(),
        Rule::InterfaceBoundary(_) => observed().next().is_some(),
        Rule::ForbiddenConstruct(rule) => {
            crate::construct_match::receipt(model, rule)?;
            true
        }
        // Slice S5 (AD-380), `_rule_evaluation_facts_for_rule`.
        // An undecided position (`symbol_limits`) withholds the receipt as well.
        Rule::ForbiddenDependency(rule) => {
            let judged = direction::forbidden(model, rule)
                .into_iter()
                .map(|(_, j)| j);
            undecided(direction::undecided(judged))?;
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
        // Each kind that no slice decides: its slice states its receipt here (AD-378). A
        // permission declaration (`allowed_dependency`) has no verdict, so it has no receipt.
        other @ (Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::AllowedDependency(_)
        | Rule::SourceOwnership(_)
        | Rule::NoComponentCycles(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_)) => {
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
    if modules.iter().any(|id| {
        crate::ids::Table::get(model.graph().modules(), *id).is_none_or(|module| {
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
    }) {
        return Err(Reason::NotComplete(Cause::Receipt(
            "symbol placement: class inventory is incomplete",
        )));
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
#[derive(Clone, Copy)]
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
