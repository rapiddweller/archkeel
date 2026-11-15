// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The effect of each gap and the rules that it holds (AD-564).
//!
//! A collector can state what one gap leaves unknown (`GapEffect`). A gap without a statement
//! leaves the whole scope unknown, as before. This file gives each gap its class one time, and
//! it states for each rule kind which facts of a module the rule reads (`reads`). A gap with an
//! effect holds a rule only when the effect meets the read set of the rule.
//!
//! Each doubt goes to the wider class, so a statement can only make a verdict less certain: a
//! gap with an effect that names no module, or a module that the reply does not have, or that
//! also has the form of a gap between two modules, leaves the whole scope unknown.
//!
//! The match of `reads` has no catch-all arm: a new rule kind does not compile until it states
//! what it reads.

use std::collections::BTreeSet;
use std::fmt;

use archkeel_contract::{CycleLevel, Rule};
use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::envelope::Coverage;

use crate::causes::HELD_SHOWN;
use crate::coverage::{data_of, droppable};
use crate::model::Model;
use crate::ownership::{claims, in_scope, owner_of};
use crate::selection;

/// How much one gap leaves unknown.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Class {
    /// The whole scope: no rule has a scope proof.
    Whole,
    /// The edge between two modules (AD-357): `pair_gaps.rs` gives the rules that it holds.
    Pair,
    /// The stated effect: `held` gives the rules that it holds.
    Effect,
}

/// The class of each gap of the coverage, in the order of the reply.
pub(crate) fn classes(coverage: &Coverage, is_module: impl Fn(&str) -> bool) -> Vec<Class> {
    coverage
        .gaps
        .iter()
        .map(|gap| class(data_of(&gap.data), &is_module))
        .collect()
}

fn class(data: &GapData, is_module: &impl Fn(&str) -> bool) -> Class {
    let pair = droppable(data);
    let Some(effect) = &data.effect else {
        return if pair { Class::Pair } else { Class::Whole };
    };
    let named = match effect {
        GapEffect::Edges { sources: names } | GapEffect::Modules { modules: names } => {
            !names.is_empty() && names.iter().all(|name| is_module(name.as_str()))
        }
        GapEffect::EveryModule => true,
    };
    if named && !pair {
        Class::Effect
    } else {
        Class::Whole
    }
}

/// One gap with an effect: its id and its effect.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct EffectGap {
    pub(crate) id: String,
    pub(crate) effect: GapEffect,
}

/// The gaps with an effect, in the order of the reply.
pub(crate) fn effect_gaps(coverage: &Coverage, classes: &[Class]) -> Vec<EffectGap> {
    coverage
        .gaps
        .iter()
        .zip(classes)
        .filter(|(_, class)| **class == Class::Effect)
        .filter_map(|(gap, _)| {
            Some(EffectGap {
                id: gap.id.as_str().to_owned(),
                effect: data_of(&gap.data).effect.clone()?,
            })
        })
        .collect()
}

/// Facts that a gap leaves unknown and that a rule reads.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Doubt {
    /// The import edges that leave this module.
    Edges(String),
    /// The code of this module: its import edges, its members and its constructs.
    Code(String),
    /// The code of every module.
    EveryModule,
}

impl Doubt {
    /// The stable word of the doubt: it holds no gap id and no position (AD-546).
    pub fn word(&self) -> String {
        match self {
            Doubt::Edges(module) => format!("edges: {module}"),
            Doubt::Code(module) => format!("modules: {module}"),
            Doubt::EveryModule => "every_module".to_owned(),
        }
    }
}

impl fmt::Display for Doubt {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Doubt::Edges(module) => write!(formatter, "the import edges of {module}"),
            Doubt::Code(module) => write!(formatter, "the code of {module}"),
            Doubt::EveryModule => formatter.write_str("the code of every module"),
        }
    }
}

/// The gaps with an effect that hold a rule or the run: their ids, in the order of the reply,
/// and the facts that they leave unknown, sorted and distinct. It is a reason, not a proof: it
/// can only make a rule UNKNOWN.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Scoped {
    ids: Vec<String>,
    doubts: Vec<Doubt>,
}

impl Scoped {
    /// The id of each gap that holds the rule.
    pub fn ids(&self) -> &[String] {
        &self.ids
    }

    /// The facts that the gaps leave unknown and that the rule reads.
    pub fn doubts(&self) -> &[Doubt] {
        &self.doubts
    }
}

impl fmt::Display for Scoped {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let shown: Vec<String> = self
            .doubts
            .iter()
            .take(HELD_SHOWN)
            .map(Doubt::to_string)
            .collect();
        write!(
            formatter,
            "{} gaps leave unknown what the rule reads: {}",
            self.ids.len(),
            shown.join(", ")
        )?;
        match self.doubts.len() - shown.len() {
            0 => Ok(()),
            more => write!(formatter, " and {more} more"),
        }
    }
}

/// The facts of one module that a rule reads.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct ReadSet {
    /// The import edges that leave the module.
    edges: bool,
    /// The code of the module: its members, its positions and its constructs.
    code: bool,
}

impl ReadSet {
    const NONE: ReadSet = ReadSet {
        edges: false,
        code: false,
    };
    const BOTH: ReadSet = ReadSet {
        edges: true,
        code: true,
    };

    fn edges(edges: bool) -> ReadSet {
        ReadSet { edges, code: false }
    }

    fn any(self) -> bool {
        self.edges || self.code
    }
}

/// The gaps with an effect that hold `rule` in `model`, if any.
pub(crate) fn held(model: &Model, rule: &Rule) -> Option<Scoped> {
    scoped(model, |module| reads(model, rule, module))
}

/// Each gap with an effect: with one, the scope of the whole run is not complete.
pub(crate) fn every(model: &Model) -> Option<Scoped> {
    scoped(model, |_| ReadSet::BOTH)
}

fn scoped(model: &Model, reads: impl Fn(Option<&str>) -> ReadSet) -> Option<Scoped> {
    let mut ids = Vec::new();
    let mut doubts = BTreeSet::new();
    for gap in &model.graph().observed().effect_gaps {
        let mut met = false;
        match &gap.effect {
            GapEffect::Edges { sources } => {
                for module in sources.iter().map(|name| name.as_str()) {
                    if reads(Some(module)).edges {
                        met = true;
                        doubts.insert(Doubt::Edges(module.to_owned()));
                    }
                }
            }
            GapEffect::Modules { modules } => {
                for module in modules.iter().map(|name| name.as_str()) {
                    if reads(Some(module)).any() {
                        met = true;
                        doubts.insert(Doubt::Code(module.to_owned()));
                    }
                }
            }
            GapEffect::EveryModule => {
                if reads(None).any() {
                    met = true;
                    doubts.insert(Doubt::EveryModule);
                }
            }
        }
        if met {
            ids.push(gap.id.clone());
        }
    }
    (!ids.is_empty()).then(|| Scoped {
        ids,
        doubts: doubts.into_iter().collect(),
    })
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
        // The files and their module names, the components and the contract: each effect
        // leaves them known.
        Rule::RootLayout(_)
        | Rule::CompleteAssignment(_)
        | Rule::LayerOrder(_)
        | Rule::AllowedDependency(_) => ReadSet::NONE,
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
                    model.selects(name)
                        && (sources.matches(name) || unowned(name))
                        && !exempt(name)
                }),
                code: rule.target_symbol().is_some(),
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
        },
        // A publication route can go through any module.
        Rule::InterfaceBoundary(_) => ReadSet {
            edges: owned,
            code: true,
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
            }
        }
        // AD-550 reads the written types of each module, and a type name through its imports.
        Rule::BoundaryTypes(_) => ReadSet::BOTH,
        // A kind that no slice decides: its slice states what it reads here (fail closed).
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::SourceOwnership(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_) => ReadSet::BOTH,
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
