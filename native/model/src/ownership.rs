// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The owner of each module (slice S1).
//!
//! Python: `ir/facts.py` `in_scope`, `ir/dependency.py` `module_in_ownership`, `ir/ownership.py`
//! `sole`, `ir/model.py` `ArchitectureContract.component_for` and `package_owners`, and
//! `check/evaluation/rules.py` `_modules_for_rule_source`. A module has an owner only when
//! exactly one component claims it: no claim and two claims (a nested package of two components,
//! or one module named twice) both leave it without an owner, so it stays visible to
//! `complete_assignment`.

use std::collections::HashMap;

use archkeel_contract::Component;

use crate::ids::{ComponentId, ModuleId, Table};
use crate::modules::Module;

/// True when `name` is `scope` or a dotted descendant of it (no partial segment).
pub fn in_scope(name: &str, scope: &str) -> bool {
    name.strip_prefix(scope)
        .is_some_and(|rest| rest.is_empty() || rest.starts_with('.'))
}

/// True when a component claims a module: one of its exact modules, or below one of its packages.
pub fn claims(component: &Component, module: &str) -> bool {
    component
        .exact_modules()
        .iter()
        .any(|exact| exact.as_text() == module)
        || component
            .packages()
            .iter()
            .any(|package| in_scope(module, package.as_text()))
}

/// The one claimant, or `None` for zero or many.
fn sole<T: Copy>(mut claims: impl Iterator<Item = T>) -> Option<T> {
    let first = claims.next()?;
    claims.next().is_none().then_some(first)
}

/// The owner of each module, by module id.
pub(crate) fn owners(
    components: &Table<ComponentId, Component>,
    modules: &Table<ModuleId, Module>,
) -> Vec<Option<ComponentId>> {
    modules
        .iter()
        .map(|(_, module)| owner_of(components, module.name()))
        .collect()
}

/// The one component that claims a module name, or `None` when zero or many claim it.
pub(crate) fn owner_of(
    components: &Table<ComponentId, Component>,
    module: &str,
) -> Option<ComponentId> {
    sole(
        components
            .iter()
            .filter(|(_, component)| claims(component, module))
            .map(|(id, _)| id),
    )
}

/// The modules that a rule `source` selects: all the modules of the component that declares
/// `source` as one of its packages, else the modules below `source`.
pub(crate) fn source_modules(
    components: &Table<ComponentId, Component>,
    modules: &Table<ModuleId, Module>,
    source: &str,
) -> Vec<ModuleId> {
    // `package_owners`: package to label, the last component wins; `ownership_by_label`: label
    // to its ownership, the last component of a label wins.
    let mut by_package: HashMap<&str, &str> = HashMap::new();
    let mut by_label: HashMap<&str, &Component> = HashMap::new();
    for (_, component) in components.iter() {
        let label = component.label().as_text();
        for package in component.packages() {
            by_package.insert(package.as_text(), label);
        }
        by_label.insert(label, component);
    }
    let owner = by_package
        .get(source)
        .and_then(|label| by_label.get(label))
        .copied();
    modules
        .iter()
        .filter(|(_, module)| match owner {
            Some(component) => claims(component, module.name()),
            None => in_scope(module.name(), source),
        })
        .map(|(id, _)| id)
        .collect()
}
