// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compare two contract trees as `validate --against` does (Python `_contract_changes`):
//! the widenings of the comparison contracts, the widenings of the declarations of each inside
//! scope, then the narrowings (AD-255). A rename is not recognised (M6b row 4).

use std::collections::BTreeMap;

use crate::document::Contract;
use crate::model::Selector;
use crate::model_declarations::{
    Capability, Command, Declarations, FlowPath, Lifetime, ModuleTarget, ReviewScope, SpotOwner,
};
use crate::model_uml::Target;
use crate::policy::change::{
    by_message, set_widenings, ChangeDirection, ChangeKind, ContractChange,
};
use crate::policy::pyrepr::word;
use crate::policy::reference::python_repr;
use crate::policy::tree::ContractTree;
use crate::policy::widen_components::{components_narrowings, components_widenings};
use crate::policy::widen_rules::{rules_narrowings, rules_widenings};

record!(
    pub(crate),
    /// The changes from an old to a new contract tree: the widenings first, then the narrowings.
    Comparison {
        changes: Vec<ContractChange>,
    }
);

impl Comparison {
    /// Whether a change permits more. Without a valid amendment, such a change fails the gate.
    pub fn widened(&self) -> bool {
        self.changes
            .iter()
            .any(|change| *change.direction() == ChangeDirection::Widened)
    }
}

/// Compare the old tree with the new tree.
pub fn compare_trees(before: &ContractTree, after: &ContractTree) -> Comparison {
    let mut changes = contract_widenings(before.comparison(), after.comparison());
    changes.extend(inside_widenings(before, after));
    let mut narrowed = components_narrowings(
        &before.comparison().components,
        &after.comparison().components,
    );
    narrowed.extend(rules_narrowings(
        &before.comparison().rules,
        &after.comparison().rules,
    ));
    changes.extend(by_message(narrowed));
    Comparison { changes }
}

/// Python `contract_widening_changes`.
fn contract_widenings(before: &Contract, after: &Contract) -> Vec<ContractChange> {
    let mut changes = components_widenings(&before.components, &after.components);
    changes.extend(rules_widenings(&before.rules, &after.rules));
    if before.schema != after.schema {
        let text = |value: &Option<String>| {
            value
                .as_deref()
                .map_or_else(|| "None".to_owned(), python_repr)
        };
        let message = format!(
            "contract.$schema changed from {} to {}",
            text(&before.schema),
            text(&after.schema)
        );
        changes.push(ContractChange::widened(
            ChangeKind::Changed,
            "contract",
            "$schema",
            message,
        ));
    }
    changes.extend(declaration_widenings(
        before.declarations.as_ref(),
        after.declarations.as_ref(),
    ));
    by_message(changes)
}

/// The declaration part of Python `contract_widening_changes`. An absent object is the empty
/// object.
fn declaration_widenings(
    before: Option<&Declarations>,
    after: Option<&Declarations>,
) -> Vec<ContractChange> {
    let budgets = |item: Option<&Declarations>| -> Vec<String> {
        item.map(|d| {
            d.measurement_budgets
                .iter()
                .map(|b| word(&b.name))
                .collect()
        })
        .unwrap_or_default()
    };
    let (was, now) = (budgets(before), budgets(after));
    let mut changes = set_widenings(
        "contract.declarations",
        "measurement_budgets",
        was.iter().map(String::as_str),
        now.iter().map(String::as_str),
        false,
    );
    changes.extend(ceilings("facade budget", facades(before), facades(after)));
    changes.extend(ceilings(
        "coupling budget",
        couplings(before),
        couplings(after),
    ));
    if !same_unenumerated(before, after) {
        let message = "contract.declarations changed in a way this comparison does not enumerate";
        changes.push(ContractChange::widened(
            ChangeKind::NotEnumerated,
            "contract.declarations",
            "declarations",
            message.to_owned(),
        ));
    }
    changes.extend(compat_widenings(before, after));
    changes
}

fn facades(item: Option<&Declarations>) -> BTreeMap<String, u64> {
    let budgets = item.and_then(|d| d.facade_budgets.as_ref());
    budgets
        .into_iter()
        .flatten()
        .map(|b| (b.component.0.clone(), b.max_names))
        .collect()
}

fn couplings(item: Option<&Declarations>) -> BTreeMap<String, u64> {
    let budgets = item.and_then(|d| d.coupling_budgets.as_ref());
    budgets
        .into_iter()
        .flatten()
        .map(|b| (format!("{} -> {}", b.source.0, b.target.0), b.max_names))
        .collect()
}

/// Python `_ceiling_widenings`: a raised or removed ceiling widens (AD-99).
fn ceilings(
    kind: &str,
    before: BTreeMap<String, u64>,
    after: BTreeMap<String, u64>,
) -> Vec<ContractChange> {
    let mut changes = Vec::new();
    for (subject, old) in before {
        match after.get(&subject) {
            None => {
                let message = format!("{kind} {subject} removed");
                changes.push(ContractChange::widened(
                    ChangeKind::Presence,
                    &subject,
                    "presence",
                    message,
                ));
            }
            Some(new) if *new > old => {
                let message = format!("{kind} {subject} raised from {old} to {new}");
                changes.push(ContractChange::widened(
                    ChangeKind::Raised,
                    &subject,
                    "max_names",
                    message,
                ));
            }
            Some(_) => {}
        }
    }
    changes
}

/// The declarations that no classifier compares field by field, as one comparable value.
type Unenumerated<'a> = (
    &'a [Capability],
    &'a [ReviewScope],
    &'a [Selector],
    &'a [String],
    &'a [Command],
    &'a [String],
    &'a [String],
    &'a [FlowPath],
    &'a [SpotOwner],
    Option<&'a Vec<ModuleTarget>>,
    Option<&'a Target>,
);

/// Python `_unenumerated(declarations)`: every field except the four that a classifier above
/// compares. The pattern names each field, so a new field of `Declarations` does not compile
/// without a decision. An absent object is `ContractDeclarations()`.
fn unenumerated(item: Option<&Declarations>) -> Unenumerated<'_> {
    let Some(Declarations {
        capabilities,
        review_scopes,
        public_api,
        public_api_provenance,
        public_commands,
        context_roots,
        context_roots_provenance,
        paths,
        spot_owners,
        compat: _,
        measurement_budgets: _,
        facade_budgets: _,
        coupling_budgets: _,
        modules,
        uml,
    }) = item
    else {
        return (&[], &[], &[], &[], &[], &[], &[], &[], &[], None, None);
    };
    (
        capabilities,
        review_scopes,
        public_api,
        public_api_provenance,
        public_commands,
        context_roots,
        context_roots_provenance,
        paths,
        spot_owners,
        modules.as_ref(),
        uml.as_ref(),
    )
}

/// Python `_unenumerated(before) == _unenumerated(after)`.
fn same_unenumerated(before: Option<&Declarations>, after: Option<&Declarations>) -> bool {
    unenumerated(before) == unenumerated(after)
}

/// The compatibility part of Python `contract_widening_changes`.
fn compat_widenings(
    before: Option<&Declarations>,
    after: Option<&Declarations>,
) -> Vec<ContractChange> {
    let by_module = |item: Option<&Declarations>| {
        let map: BTreeMap<String, (String, Lifetime)> = item
            .map(|d| {
                d.compat
                    .iter()
                    .map(|c| (c.module.0.clone(), (c.target.0.clone(), c.lifetime)))
                    .collect()
            })
            .unwrap_or_default();
        map
    };
    let (old, new) = (by_module(before), by_module(after));
    let mut changes = Vec::new();
    for (module, (target, lifetime)) in &new {
        let subject = format!("compat module {}", python_repr(module));
        let Some((old_target, old_lifetime)) = old.get(module) else {
            let message = format!("{subject} added");
            changes.push(ContractChange::widened(
                ChangeKind::Presence,
                &subject,
                "presence",
                message,
            ));
            continue;
        };
        if old_target != target {
            let message = format!(
                "{subject} changed from {} to {}",
                python_repr(old_target),
                python_repr(target)
            );
            changes.push(ContractChange::widened(
                ChangeKind::Changed,
                &subject,
                "target",
                message,
            ));
        }
        if old_lifetime != lifetime && *lifetime == Lifetime::Permanent {
            let message = format!("{subject} lifetime became permanent");
            changes.push(ContractChange::widened(
                ChangeKind::Permanent,
                &subject,
                "lifetime",
                message,
            ));
        }
    }
    changes
}

/// Python `_inside_declaration_widenings` without a rename: the declarations of each inside
/// scope, old scopes first, in the order of their mounts.
fn inside_widenings(before: &ContractTree, after: &ContractTree) -> Vec<ContractChange> {
    let declarations = |tree: &ContractTree| -> Vec<(String, Option<Declarations>)> {
        tree.mounts()
            .iter()
            .map(|mount| {
                (
                    mount.parent_id().clone(),
                    mount.contract().declarations.clone(),
                )
            })
            .collect()
    };
    let (old, new) = (declarations(before), declarations(after));
    let find = |list: &[(String, Option<Declarations>)], scope: &str| {
        list.iter()
            .find(|(key, _)| key == scope)
            .map(|(_, value)| value.clone())
    };
    let mut scopes: Vec<&String> = Vec::new();
    for (scope, _) in old.iter().chain(new.iter()) {
        if !scopes.contains(&scope) {
            scopes.push(scope);
        }
    }
    let mut changes = Vec::new();
    for scope in scopes {
        let was = find(&old, scope).flatten();
        let now = find(&new, scope).flatten();
        let found = by_message(declaration_widenings(was.as_ref(), now.as_ref()));
        changes.extend(found.into_iter().map(|change| change.inside(scope)));
    }
    changes
}
