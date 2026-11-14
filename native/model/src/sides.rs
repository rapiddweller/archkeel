// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a rule says about components (AD-484): the components on its two sides and its
//! direction, read from the contract. A page draws the rule on the component map from it, so it
//! does not parse rule text. The shape decides nothing and holds no verdict.
//!
//! A selector selects a component when the component holds a package or a module that lies
//! below the selector, or the selector lies below a package of the component, or the names are
//! the same. A rule kind without a side that names components has the direction `None` and
//! empty sides.

use archkeel_contract::{kind_of, Component, Contract, Rule, RuleKind};

use crate::ownership::in_scope;
use crate::selection::dependency_sides;

/// How a rule relates its two sides.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    /// No dependency from the source side to the target side.
    Forbids,
    /// A dependency from the source side to the target side is allowed.
    Allows,
    /// Each component can depend only on the components that it requires.
    Requires,
    /// The members depend on none of their siblings.
    Isolates,
    /// The components depend only in the order of their layers.
    Orders,
    /// The components have no cycle between them.
    Acyclic,
    /// The rule names no side of components.
    None,
}

impl Direction {
    /// The word of the frame.
    pub fn word(self) -> &'static str {
        const WORDS: [&str; 7] = [
            "forbids", "allows", "requires", "isolates", "orders", "acyclic", "none",
        ];
        WORDS.get(self as usize).copied().unwrap_or("none")
    }
}

/// The shape of one rule: its kind, its direction and the component ids of its two sides, in
/// contract order. `source` and `target` can be the same set.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Shape {
    pub kind: RuleKind,
    pub direction: Direction,
    pub source: Vec<String>,
    pub target: Vec<String>,
}

fn holds(component: &Component, selector: &str) -> bool {
    component
        .exact_modules()
        .iter()
        .any(|module| in_scope(module.as_text(), selector))
        || component.packages().iter().any(|package| {
            in_scope(package.as_text(), selector) || in_scope(selector, package.as_text())
        })
}

fn ids<'c>(components: impl Iterator<Item = &'c Component>) -> Vec<String> {
    components
        .map(|component| component.id().as_text().to_owned())
        .collect()
}

fn named(
    contract: &Contract,
    labels: Option<&Vec<archkeel_contract::ComponentLabel>>,
) -> Vec<String> {
    ids(contract
        .components()
        .iter()
        .filter(|component| labels.is_none_or(|labels| labels.contains(component.label()))))
}

fn selected(contract: &Contract, selector: &str) -> Vec<String> {
    ids(contract
        .components()
        .iter()
        .filter(|component| holds(component, selector)))
}

/// The shape of a rule of the contract.
pub fn shape(contract: &Contract, rule: &Rule) -> Shape {
    let kind = kind_of(rule);
    let (direction, source, target) = match rule {
        Rule::ForbiddenDependency(rule) => {
            let components = contract.components();
            let [from, to] = dependency_sides(rule, components);
            let side = |selection: &crate::selection::Selection<'_>| {
                ids(components.iter().filter(|component| {
                    component
                        .packages()
                        .iter()
                        .map(|package| package.as_text())
                        .chain(
                            component
                                .exact_modules()
                                .iter()
                                .map(|module| module.as_text()),
                        )
                        .any(|name| selection.matches(name))
                }))
            };
            (Direction::Forbids, side(&from), side(&to))
        }
        Rule::AllowedDependency(rule) => (
            Direction::Allows,
            selected(contract, rule.source().as_text()),
            selected(contract, rule.target().as_text()),
        ),
        Rule::CompleteRequires(_) => {
            let sources: Vec<&Component> = contract
                .components()
                .iter()
                .filter(|component| component.requires().iter().flatten().next().is_some())
                .collect();
            let targets = contract.components().iter().filter(|component| {
                sources.iter().any(|source| {
                    source
                        .requires()
                        .iter()
                        .flatten()
                        .any(|entry| entry.component() == component.label())
                })
            });
            (
                Direction::Requires,
                ids(sources.iter().copied()),
                ids(targets),
            )
        }
        Rule::SiblingIsolation(rule) => {
            let members: Vec<String> = contract
                .components()
                .iter()
                .filter(|component| {
                    rule.members()
                        .iter()
                        .any(|member| holds(component, member.as_text()))
                })
                .map(|component| component.id().as_text().to_owned())
                .collect();
            (Direction::Isolates, members.clone(), members)
        }
        Rule::LayerOrder(rule) => {
            let members = ids(crate::selection::layer_components(contract, rule).into_iter());
            (Direction::Orders, members.clone(), members)
        }
        Rule::NoComponentCycles(rule) => {
            let members = named(contract, rule.components().as_ref());
            (Direction::Acyclic, members.clone(), members)
        }
        _ => (Direction::None, Vec::new(), Vec::new()),
    };
    Shape {
        kind,
        direction,
        source,
        target,
    }
}
