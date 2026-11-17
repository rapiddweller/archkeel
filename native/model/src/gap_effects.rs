// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a gap with an effect holds (AD-564).
//!
//! This file states for each rule kind which facts of a module the rule reads (`reads`). A gap
//! with an effect (`gap_class.rs`) holds a rule only when the effect meets the read set of the
//! rule.
//!
//! The match of `reads` has no catch-all arm: a new rule kind does not compile until it states
//! what it reads.

use std::collections::BTreeSet;

use archkeel_contract::{CycleLevel, Rule};
use archkeel_facts::data::GapEffect;

use crate::door_reach::Applied;
use crate::gap_class::{Doubt, Scoped};
use crate::model::Model;
use crate::ownership::{claims, in_scope, owner_of};
use crate::selection;

/// The facts of one module that a rule reads.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct ReadSet {
    /// The import edges that leave the module.
    edges: bool,
    /// The code of the module: its members, its positions and its constructs.
    code: bool,
    /// The file of the module and its place in the layout (`L`).
    layout: bool,
}

impl ReadSet {
    const BOTH: ReadSet = ReadSet {
        edges: true,
        code: true,
        layout: false,
    };
    /// Each fact of each module: the run reads all of them.
    const ALL: ReadSet = ReadSet {
        edges: true,
        code: true,
        layout: true,
    };

    fn edges(edges: bool) -> ReadSet {
        ReadSet {
            edges,
            ..ReadSet::default()
        }
    }

    fn layout(layout: bool) -> ReadSet {
        ReadSet {
            layout,
            ..ReadSet::default()
        }
    }

    fn any(self) -> bool {
        self.edges || self.code
    }
}

/// The gaps with an effect that hold `rule` in `model`, if any.
pub(crate) fn held(model: &Model, rule: &Rule) -> Option<Scoped> {
    scoped(model, |module| reads(model, rule, module))
}

/// The applied door declarations whose stated effect meets what `rule` reads (AD-664): a PASS of
/// the rule holds only under their premise.
pub fn assumed<'m>(model: &'m Model, rule: &Rule) -> Vec<&'m Applied> {
    let reads = |module: Option<&str>| reads(model, rule, module);
    let applied = model.graph().doors().applied().iter();
    applied
        .filter(|door| !met(&door.stated, &reads).is_empty())
        .collect()
}

/// Each gap with an effect: with one, the scope of the whole run is not complete.
pub(crate) fn every(model: &Model) -> Option<Scoped> {
    scoped(model, |_| ReadSet::ALL)
}

fn scoped(model: &Model, reads: impl Fn(Option<&str>) -> ReadSet) -> Option<Scoped> {
    let mut ids = Vec::new();
    let mut doubts = BTreeSet::new();
    for gap in &model.graph().observed().effect_gaps {
        let met = met(&gap.effect, &reads);
        if !met.is_empty() {
            ids.push(gap.id.clone());
            doubts.extend(met);
        }
    }
    Scoped::of(ids, doubts.into_iter().collect())
}

/// The facts that `effect` leaves unknown and that `reads` reads.
fn met(effect: &GapEffect, reads: &impl Fn(Option<&str>) -> ReadSet) -> Vec<Doubt> {
    match effect {
        GapEffect::Edges { sources } => sources
            .iter()
            .map(|name| name.as_str())
            .filter(|module| reads(Some(module)).edges)
            .map(|module| Doubt::Edges(module.to_owned()))
            .collect(),
        GapEffect::Modules { modules } => modules
            .iter()
            .map(|name| name.as_str())
            .filter(|module| reads(Some(module)).any())
            .map(|module| Doubt::Code(module.to_owned()))
            .collect(),
        GapEffect::EveryModule if reads(None).any() => vec![Doubt::EveryModule],
        GapEffect::EveryModule => Vec::new(),
        GapEffect::Layout { modules } => modules
            .iter()
            .map(|name| name.as_str())
            .filter(|module| reads(Some(module)).layout)
            .map(|module| Doubt::Layout(module.to_owned()))
            .collect(),
    }
}

/// What `rule` reads of `module` in `model`. `None` stands for some module of the reply, so each
/// test of a name holds for it: an effect on every module meets each rule that reads a module.
///
/// The gaps of a mount are the gaps of its domain (`Model::selects`), as for a dynamic import
/// limit (`scope.rs` `dynamic_import`).
fn reads(model: &Model, rule: &Rule, module: Option<&str>) -> ReadSet {
    let on = |test: &dyn Fn(&str) -> bool| module.is_none_or(test);
    let claimed = |name: &str| {
        model
            .components()
            .iter()
            .any(|(_, component)| claims(component, name))
    };
    // A crossing and a component cycle read an edge only when one component owns each end
    // (`direction::crossings`, `interface.rs`, `component_cycles.rs`). A module that more than
    // one component claims has no owner, but it counts here (the wider reading).
    let owned = on(&claimed);
    match rule {
        // The files and their module names below the root or the source (`layout::check`,
        // `assignment::check`): only a layout effect leaves them unknown.
        Rule::RootLayout(rule) => ReadSet::layout(on(&|name| {
            model.selects(name) && in_scope(name, rule.root().as_text())
        })),
        Rule::CompleteAssignment(rule) => ReadSet::layout(on(&|name| {
            model.selects(name) && in_scope(name, rule.source().as_text())
        })),
        // The components and the contract: each effect leaves them known.
        Rule::LayerOrder(_) | Rule::AllowedDependency(_) => ReadSet::default(),
        // The external imports of each module that the rule does not exempt.
        Rule::ExternalDependencyScope(rule) => ReadSet::edges(on(&|name| {
            let exact = rule.exact_sources().iter().any(|e| e.as_text() == name);
            let allowed = rule
                .allowed_sources()
                .iter()
                .any(|allowed| in_scope(name, allowed.as_text()));
            model.selects(name) && !exact && !allowed
        })),
        Rule::CompleteExternalScope(rule) => ReadSet::edges(on(&|name| {
            model.selects(name) && sourced(model, rule.source().as_text(), name)
        })),
        // The edges of the source side; a module without one owner can be on either side. A
        // `target_symbol` reads the members of the target and each binding on the way to it.
        Rule::ForbiddenDependency(rule) => {
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            let unowned = |name: &str| owner_of(model.components(), name).is_none();
            let exempt = |name: &str| rule.allowed_sources().iter().any(|a| a.as_text() == name);
            ReadSet {
                edges: on(&|name| {
                    model.selects(name) && (sources.matches(name) || unowned(name)) && !exempt(name)
                }),
                code: rule.target_symbol().is_some(),
                layout: false,
            }
        }
        Rule::SiblingIsolation(rule) => ReadSet::edges(on(&|name| {
            let member = rule.members().iter().any(|m| in_scope(name, m.as_text()));
            model.selects(name) && member
        })),
        // The `through` ports are members of the modules of each component.
        Rule::CompleteRequires(_) => ReadSet {
            edges: owned,
            code: owned,
            layout: false,
        },
        // A publication route can go through any module.
        Rule::InterfaceBoundary(_) => ReadSet {
            edges: owned,
            code: true,
            layout: false,
        },
        // A module cycle can close through any module.
        Rule::NoComponentCycles(rule) => {
            ReadSet::edges(*rule.level() == CycleLevel::Module || owned)
        }
        // The constructs of the modules of the source. A selector reads the bindings of each
        // module. No proof yet that an effect on the edges leaves the constructs known.
        Rule::ForbiddenConstruct(rule) => {
            let read = rule.selector().is_some()
                || on(&|name| model.selects(name) && sourced(model, rule.source().as_text(), name));
            ReadSet {
                edges: read,
                code: read,
                layout: false,
            }
        }
        // AD-550 reads the written types of each module, and a type name through its imports.
        Rule::BoundaryTypes(_) => ReadSet::BOTH,
        // AD-670: a use of a public name can come from any import of any module.
        Rule::UnusedPublic(_) => ReadSet::BOTH,
        // A kind that no slice decides: its slice states what it reads here (fail closed).
        undecided_rule!() => ReadSet::BOTH,
    }
}

/// True when a rule `source` can select `module`: the module lies below the source, or a
/// component that declares the source as a package claims it (`ownership::source_modules`).
fn sourced(model: &Model, source: &str, module: &str) -> bool {
    in_scope(module, source)
        || model.components().iter().any(|(_, component)| {
            component.packages().iter().any(|p| p.as_text() == source) && claims(component, module)
        })
}

#[cfg(test)]
#[path = "gap_effects_tests.rs"]
mod tests;
