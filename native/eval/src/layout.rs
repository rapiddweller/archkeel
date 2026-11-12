// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `root_layout`: each direct child of `root` (a package or a module) is an allowed child.
//!
//! Reference engine: `check/evaluation/rules.py` `_root_layout_violations` (the violations) and
//! `_rule_evaluation_facts_for_rule` (the receipt: the modules below `root`).

use std::collections::{BTreeSet, HashMap};

use archkeel_contract::RootLayout;
use archkeel_model::{in_scope, Model, Reason};

use crate::violation::Violation;

/// The violations of the rule and whether it selects a module (its receipt), or the reason that
/// a child has no record to cite.
pub(crate) fn check(
    id: &str,
    rule: &RootLayout,
    model: &Model,
) -> Result<(Vec<Violation>, bool), Reason> {
    let root = rule.root().as_text();
    let depth = root.split('.').count() + 1;
    let names = model
        .graph()
        .packages()
        .iter()
        .map(|(_, package)| package.name())
        .chain(
            model
                .graph()
                .modules()
                .iter()
                .map(|(_, module)| module.name()),
        );
    // The reference engine sorts the children as `str`: by code point, as `BTreeSet` does.
    let children: BTreeSet<&str> = names
        .filter(|name| *name != root && in_scope(name, root) && name.split('.').count() == depth)
        .collect();
    let records = child_records(model.graph().modules().iter().map(|(id, module)| {
        let package = model.graph().packages().get(module.package());
        (
            id,
            module.name(),
            package.map_or("", |package| package.name()),
        )
    }));
    // An allowed child matches by its whole name, never by a prefix.
    let allowed: Vec<&str> = rule
        .allowed_children()
        .iter()
        .map(|child| child.as_text())
        .collect();
    let mut violations = Vec::new();
    for child in children
        .into_iter()
        .filter(|child| !allowed.contains(child))
    {
        let record = cite(child, &records)?;
        let row = model
            .graph()
            .modules()
            .get(record)
            .ok_or_else(|| Reason::UncitedChild(child.to_owned()))?;
        violations.push(Violation::not_allowed(
            id, root, child, &allowed, record, row,
        ));
    }
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    let selected = model
        .graph()
        .modules()
        .iter()
        .any(|(_, module)| in_scope(module.name(), root));
    Ok((violations, selected))
}

/// The record that cites a child. The reference engine stops (`KeyError`) for a child without
/// one, so the core answers UNKNOWN with the name of the child.
pub(crate) fn cite<I: Copy>(child: &str, records: &HashMap<&str, I>) -> Result<I, Reason> {
    records
        .get(child)
        .copied()
        .ok_or_else(|| Reason::UncitedChild(child.to_owned()))
}

/// The module record that cites a child name: the last module of that name, else the first
/// module of that package. `modules` gives each module with its name and its package name.
pub(crate) fn child_records<'a, I: Copy>(
    modules: impl IntoIterator<Item = (I, &'a str, &'a str)>,
) -> HashMap<&'a str, I> {
    let mut by_name: HashMap<&str, I> = HashMap::new();
    let mut by_package: HashMap<&str, I> = HashMap::new();
    for (id, name, package) in modules {
        by_package.entry(package).or_insert(id);
        by_name.insert(name, id);
    }
    by_package.extend(by_name);
    by_package
}
