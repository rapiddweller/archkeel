// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The owner of each module (slice S1).
//!
//! Reference engine: `ir/facts.py` `in_scope`, `ir/dependency.py` `module_in_ownership`, `ir/ownership.py`
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

/// True when a `requires` entry of `source` for `target` has a symbol port.
pub(crate) fn symbol_port(source: &Component, target: &Component) -> bool {
    source.requires().iter().flatten().any(|entry| {
        entry.component() == target.label()
            && entry.through().iter().any(|p| p.as_text().contains(':'))
    })
}

/// True when a port of `source` can publish a type that an impl in `module` of `target` belongs to: `source` has
/// an entry for `target`, or a symbol port at `module` or above it. The core does not yet prove the publication
/// route, so a use of `module` alone proves no violation (AD-1136, #2069). No entry and no port: false.
pub(crate) fn may_publish(
    source: &Component,
    target: &Component,
    module: &str,
    (components, reexports): (&Table<ComponentId, Component>, &[(&str, &str)]),
) -> bool {
    let mut entries = source.requires().iter().flatten();
    entries.any(|e| e.component() == target.label())
        || symbol_port_above(source, module)
        || reexported(source, components, reexports, module)
}

fn symbol_port_above(source: &Component, module: &str) -> bool {
    let mut ports = source.requires().iter().flatten().flat_map(|e| e.through());
    ports.any(|port| {
        let at = port.as_text().split_once(':');
        at.is_some_and(|(published, _)| in_scope(module, published))
    })
}

/// True when a module of `reexports` (facade, target) that a port of `source` covers re-exports from `module`: the type of an impl in `module` can
/// reach `source` through that facade, so the dependency may be the one that the port allows (AD-1136, #2069).
fn reexported(
    source: &Component,
    components: &Table<ComponentId, Component>,
    reexports: &[(&str, &str)],
    module: &str,
) -> bool {
    let entries: Vec<_> = source.requires().iter().flatten().collect();
    let covers = |facade: &str| {
        let owner = owner_of(components, facade).and_then(|id| components.get(id));
        entries.iter().any(|e| {
            let ports = e.through();
            let named = owner.is_some_and(|o| o.label() == e.component());
            (ports.is_empty() && named)
                || ports.iter().any(|p| {
                    let at = p.as_text().split_once(':').map_or(p.as_text(), |(m, _)| m);
                    in_scope(facade, at)
                })
        })
    };
    // A facade can re-export through another facade: follow the chain until no module is added.
    let mut reached = vec![module];
    let mut next = 0;
    while let Some(&target) = reached.get(next) {
        next += 1;
        for (facade, _) in reexports.iter().filter(|(_, t)| *t == target) {
            if !reached.contains(facade) {
                reached.push(facade);
            }
        }
    }
    reached.iter().skip(1).any(|facade| covers(facade))
}

/// The one claimant, or `None` for zero or many.
fn sole<T: Copy>(mut claims: impl Iterator<Item = T>) -> Option<T> {
    let first = claims.next()?;
    claims.next().is_none().then_some(first)
}

/// The owner of each module of `held` that has exactly one owner. A mount reads only the
/// modules of its domain, so its table grows with the domain, not with the reply (AD-385).
pub(crate) fn owners<'m>(
    components: &Table<ComponentId, Component>,
    held: impl Iterator<Item = (ModuleId, &'m Module)>,
) -> HashMap<ModuleId, ComponentId> {
    held.filter_map(|(id, module)| owner_of(components, module.name()).map(|owner| (id, owner)))
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
