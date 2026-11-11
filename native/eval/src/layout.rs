// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `root_layout`: each direct child of `root` (a package or a module) is an allowed child.
//!
//! Reference engine: `check/evaluation/rules.py` `_root_layout_violations` (the violations) and
//! `_rule_evaluation_facts_for_rule` (the receipt: the modules below `root`).

use std::collections::{BTreeSet, HashMap};

use archkeel_contract::RootLayout;
use archkeel_model::{in_scope, Model, ModuleId};

use crate::violation::Violation;

/// The violations of the rule, and whether it selects a module (its receipt).
pub(crate) fn check(id: &str, rule: &RootLayout, model: &Model) -> (Vec<Violation>, bool) {
    let root = rule.root().as_text();
    let depth = root.split('.').count() + 1;
    let names = model
        .packages()
        .iter()
        .map(|(_, package)| package.name())
        .chain(model.modules().iter().map(|(_, module)| module.name()));
    // The reference engine sorts the children as `str`: by code point, as `BTreeSet` does for UTF-8.
    let children: BTreeSet<&str> = names
        .filter(|name| *name != root && in_scope(name, root) && name.split('.').count() == depth)
        .collect();
    let records = child_records(model);
    let allowed: Vec<&str> = rule
        .allowed_children()
        .iter()
        .map(|child| child.as_text())
        .collect();
    let mut violations: Vec<Violation> = children
        .into_iter()
        .filter(|child| !allowed.contains(child))
        .filter_map(|child| {
            let record = records.get(child).copied()?;
            let row = model.modules().get(record)?;
            Some(Violation::not_allowed(
                id, root, child, &allowed, record, row,
            ))
        })
        .collect();
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    let selected = model
        .modules()
        .iter()
        .any(|(_, module)| in_scope(module.name(), root));
    (violations, selected)
}

/// The module record that cites a child name: the last module of that name, else the first
/// module of that package. Each package comes from a module, so a package record is never cited.
fn child_records(model: &Model) -> HashMap<&str, ModuleId> {
    let mut by_name: HashMap<&str, ModuleId> = HashMap::new();
    let mut by_package: HashMap<&str, ModuleId> = HashMap::new();
    for (id, module) in model.modules().iter() {
        if let Some(package) = model.packages().get(module.package()) {
            by_package.entry(package.name()).or_insert(id);
        }
        by_name.insert(module.name(), id);
    }
    by_package.extend(by_name);
    by_package
}
