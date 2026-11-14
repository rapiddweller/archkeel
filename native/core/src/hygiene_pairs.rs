// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The component pairs of the root contract and of the code (AD-458).
//!
//! Reference engine: `check/validation/closed_world.py` (`observed_component_edges`,
//! `target_component_edges`, `closed_world_diagnostics`) and `ir/decisions.py`
//! (`open_decision_summary`). A pair is decided only by a whole-package module rule whose source
//! and target each name a package of exactly one component label (`component_pair`).

use std::collections::{BTreeMap, BTreeSet};

use archkeel_contract::{
    Component, Contract, ForbiddenDependency, Rule, SelectorMatch, TargetKind,
};
use archkeel_model::{claims, Graph};

use crate::hygiene_graph::Pair;

/// One pair finding: the code, the subject and the claim.
pub(crate) type Finding = (&'static str, String, String);

/// The label of the one component that claims `module`, or `None` for zero or many.
fn owner<'c>(components: &'c [Component], module: &str) -> Option<&'c str> {
    let mut owners = components.iter().filter(|c| claims(c, module));
    match (owners.next(), owners.next()) {
        (Some(component), None) => Some(component.label().as_text()),
        _ => None,
    }
}

/// The component edges of the imports of the code (`observed_component_edges`).
pub(crate) fn observed(contract: &Contract, graph: &Graph) -> BTreeSet<Pair> {
    let components = contract.components();
    graph
        .imports()
        .iter()
        .filter_map(|import| {
            let source = owner(components, import.source_module())?;
            let target = owner(components, import.target_module())?;
            (source != target).then(|| (source.to_owned(), target.to_owned()))
        })
        .collect()
}

/// The pair that a whole-package rule decides (`component_pair`).
fn pair(components: &[Component], source: &str, target: &str) -> Option<Pair> {
    let labels = |name: &str| -> BTreeSet<&str> {
        components
            .iter()
            .filter(|c| c.packages().iter().any(|p| p.as_text() == name))
            .map(|c| c.label().as_text())
            .collect()
    };
    let (sources, targets) = (labels(source), labels(target));
    match (sources.iter().next(), targets.iter().next()) {
        (Some(s), Some(t)) if sources.len() == 1 && targets.len() == 1 => {
            Some(((*s).to_owned(), (*t).to_owned()))
        }
        _ => None,
    }
}

fn whole(rule: &ForbiddenDependency) -> bool {
    rule.target_symbol().is_none()
        && *rule.source_match() == SelectorMatch::Prefix
        && *rule.target_match() == SelectorMatch::Prefix
        && *rule.target_kind() == TargetKind::Module
}

/// The pairs that the forbidden and the allowed rules decide, with repeats, in rule order.
fn decided(contract: &Contract) -> (Vec<Pair>, Vec<Pair>) {
    let components = contract.components();
    let (mut forbidden, mut allowed) = (Vec::new(), Vec::new());
    for rule in contract.rules() {
        match rule {
            Rule::ForbiddenDependency(rule) if whole(rule) => {
                let found = pair(components, rule.source().as_text(), rule.target().as_text());
                forbidden.extend(found);
            }
            Rule::AllowedDependency(rule) => {
                let found = pair(components, rule.source().as_text(), rule.target().as_text());
                allowed.extend(found);
            }
            _ => {}
        }
    }
    (forbidden, allowed)
}

/// The pairs that the contract permits: each `requires` entry and each allowed pair
/// (`target_component_edges`).
pub(crate) fn permitted(contract: &Contract) -> BTreeSet<Pair> {
    let requires = contract.components().iter().flat_map(|component| {
        let source = component.label().as_text();
        component
            .requires()
            .iter()
            .flatten()
            .map(move |entry| (source.to_owned(), entry.component().as_text().to_owned()))
    });
    requires.chain(decided(contract).1).collect()
}

fn repeated(items: &[Pair]) -> BTreeSet<Pair> {
    let mut counts: BTreeMap<&Pair, usize> = BTreeMap::new();
    for item in items {
        *counts.entry(item).or_default() += 1;
    }
    counts
        .into_iter()
        .filter(|(_, count)| *count > 1)
        .map(|(item, _)| item.clone())
        .collect()
}

/// The closed-world findings of the root contract and the observed edges
/// (`closed_world_diagnostics`).
pub(crate) fn closed_world(contract: &Contract, observed: &BTreeSet<Pair>) -> Vec<Finding> {
    let (forbidden_items, allowed_items) = decided(contract);
    let forbidden: BTreeSet<Pair> = forbidden_items.iter().cloned().collect();
    let allowed: BTreeSet<Pair> = allowed_items.iter().cloned().collect();
    let mut found: Vec<Finding> = open(contract, &forbidden, &allowed).into_iter().collect();
    let groups = [
        (
            "closed_world.observed_forbidden",
            observed.intersection(&forbidden).cloned().collect(),
            "An observed component dependency is also forbidden.",
        ),
        (
            "closed_world.duplicate",
            repeated(&forbidden_items),
            "The component pair has duplicate forbidden_dependency rules.",
        ),
        (
            "closed_world.duplicate",
            repeated(&allowed_items),
            "The component pair has duplicate allowed_dependency rules.",
        ),
        (
            "decision.conflict",
            allowed
                .intersection(&forbidden)
                .cloned()
                .collect::<BTreeSet<_>>(),
            "The component pair has both an allowed_dependency and a forbidden_dependency rule.",
        ),
    ];
    for (code, pairs, claim) in groups {
        for (source, target) in pairs {
            found.push((code, format!("{source} -> {target}"), claim.to_owned()));
        }
    }
    found
}

/// The open decisions of a contract without `complete_requires`: each ordered pair of distinct
/// labels that no whole-package rule decides (`open_decision_summary`).
fn open(
    contract: &Contract,
    forbidden: &BTreeSet<Pair>,
    allowed: &BTreeSet<Pair>,
) -> Option<Finding> {
    if contract
        .rules()
        .iter()
        .any(|rule| matches!(rule, Rule::CompleteRequires(_)))
    {
        return None;
    }
    let labels: BTreeSet<&str> = contract
        .components()
        .iter()
        .map(|c| c.label().as_text())
        .collect();
    let decided = forbidden
        .union(allowed)
        .filter(|(s, t)| s != t && labels.contains(s.as_str()) && labels.contains(t.as_str()))
        .count();
    let count = labels
        .len()
        .saturating_mul(labels.len().saturating_sub(1))
        .saturating_sub(decided);
    (count > 0).then(|| {
        let plural = if count == 1 { "" } else { "s" };
        (
            "decision.open",
            format!("{count} open dependency decision{plural}"),
            "Component dependency directions remain undecided.".to_owned(),
        )
    })
}
