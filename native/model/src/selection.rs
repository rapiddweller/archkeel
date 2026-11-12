// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sides of a dependency rule and the components of a `layer_order` rule (slices S4 and S5,
//! AD-378, AD-380). The subject check, the profile limits, the scope proof and the import
//! matchers read the same selection, so this module reads only the contract.
//!
//! Reference engine: `ir/dependency.py:111` `DependencySelector.select` with `component_pair`,
//! and `check/evaluation/rules.py:1990` `_layer_order_components`.

use std::collections::HashMap;

use archkeel_contract::{
    Component, ComponentLabel, Contract, ForbiddenDependency, LayerOrder, SelectorMatch, TargetKind,
};

use crate::ownership::in_scope;

/// The modules that one side of a dependency rule selects (`ModuleSelection`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Selection<'c> {
    packages: Vec<&'c str>,
    exact: Vec<&'c str>,
}

impl Selection<'_> {
    /// True when the side selects `module` (`module_in_ownership`).
    pub fn matches(&self, module: &str) -> bool {
        self.exact.contains(&module) || self.packages.iter().any(|p| in_scope(module, p))
    }
}

/// The source and the target side of a `forbidden_dependency` rule (`forbidden_dependency_scopes`,
/// `DependencySelector.select`): a whole-package module ban whose source and target each name a
/// package of exactly one component selects the whole ordered component pair; any other rule
/// selects its own names. The subject check and the matcher read the same sides.
pub fn dependency_sides<'a>(
    rule: &'a ForbiddenDependency,
    components: &'a [Component],
) -> [Selection<'a>; 2] {
    let source = rule.source().as_text();
    let target = rule.target().as_text();
    let whole = rule.target_symbol().is_none()
        && *rule.source_match() == SelectorMatch::Prefix
        && *rule.target_match() == SelectorMatch::Prefix
        && *rule.target_kind() == TargetKind::Module;
    if whole {
        // `component_pair`: one owner label each, by an exact package; the last component of a
        // label gives its modules.
        let owners_of = |name: &str| {
            let mut labels: Vec<&str> = components
                .iter()
                .filter(|component| component.packages().iter().any(|p| p.as_text() == name))
                .map(|component| component.label().as_text())
                .collect();
            labels.dedup();
            labels.sort_unstable();
            labels.dedup();
            labels
        };
        if let ([source_label], [target_label]) =
            (owners_of(source).as_slice(), owners_of(target).as_slice())
        {
            let by_label: HashMap<&str, &Component> = components
                .iter()
                .map(|component| (component.label().as_text(), component))
                .collect();
            if let (Some(source), Some(target)) =
                (by_label.get(source_label), by_label.get(target_label))
            {
                return [owned(source), owned(target)];
            }
        }
    }
    [
        literal(source, *rule.source_match()),
        literal(target, *rule.target_match()),
    ]
}

fn owned(component: &Component) -> Selection<'_> {
    Selection {
        packages: component.packages().iter().map(|p| p.as_text()).collect(),
        exact: component
            .exact_modules()
            .iter()
            .map(|p| p.as_text())
            .collect(),
    }
}

fn literal(name: &str, mode: SelectorMatch) -> Selection<'_> {
    match mode {
        SelectorMatch::Exact => Selection {
            packages: Vec::new(),
            exact: vec![name],
        },
        SelectorMatch::Prefix => Selection {
            packages: vec![name],
            exact: Vec::new(),
        },
    }
}

/// The components of a `layer_order` rule (`_layer_order_components`): the selected sources
/// and the components that they require, in contract order.
pub fn layer_components<'c>(contract: &'c Contract, rule: &LayerOrder) -> Vec<&'c Component> {
    let selected = |component: &Component| {
        rule.components()
            .as_ref()
            .is_none_or(|labels| labels.contains(component.label()))
    };
    let sources: Vec<&Component> = contract
        .components()
        .iter()
        .filter(|c| selected(c))
        .collect();
    let targets: Vec<&ComponentLabel> = sources
        .iter()
        .flat_map(|component| component.requires().iter().flatten())
        .map(|entry| entry.component())
        .collect();
    contract
        .components()
        .iter()
        .filter(|c| sources.iter().any(|s| s.id() == c.id()) || targets.contains(&c.label()))
        .collect()
}
