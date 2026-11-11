// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the tree reads from one contract: its record IDs, its provenance paths, the declarations
//! that an inside must not hold, and the copy with IDs in the scope of a parent. Each function is
//! one Python function of `ir/codec_inside.py` or `ir/target_graph.py`.

use std::collections::BTreeSet;

use crate::document::Contract;
use crate::model::{ItemId, RuleHead};
use crate::model_declarations::Declarations;
use crate::model_uml::Target;
use crate::rule::Rule;

/// Python `scope_key`: the key of a component in the scope of its parent.
pub(crate) fn scope_key(parent: &str, label: &str) -> String {
    if parent.is_empty() {
        label.to_owned()
    } else {
        format!("{parent}:{label}")
    }
}

fn texts<'a>(ids: impl Iterator<Item = &'a ItemId> + 'a) -> impl Iterator<Item = String> + 'a {
    ids.map(|id| id.0.clone())
}

/// Python `_contract_record_ids`: the IDs that two contracts of one tree must not share.
pub(crate) fn record_ids(contract: &Contract) -> BTreeSet<String> {
    let mut ids: BTreeSet<String> =
        texts(contract.components.iter().map(|item| &item.id)).collect();
    ids.extend(contract.rules.iter().map(|rule| head(rule).id.0.clone()));
    let Some(declarations) = &contract.declarations else {
        return ids;
    };
    ids.extend(texts(declarations.capabilities.iter().map(|item| &item.id)));
    ids.extend(texts(
        declarations.review_scopes.iter().map(|item| &item.id),
    ));
    ids.extend(texts(
        declarations.public_commands.iter().map(|item| &item.id),
    ));
    ids.extend(texts(declarations.paths.iter().map(|item| &item.id)));
    ids.extend(texts(declarations.spot_owners.iter().map(|item| &item.id)));
    if let Some(target) = &declarations.uml {
        ids.extend(texts(target.entities.iter().map(|item| &item.id)));
        ids.extend(texts(target.relationships.iter().map(|item| &item.id)));
    }
    ids
}

fn head(rule: &Rule) -> &RuleHead {
    crate::rule::head_of(rule)
}

/// Python `contract_provenance_paths`: each repository path that the contract cites.
pub(crate) fn provenance_paths(contract: &Contract) -> BTreeSet<String> {
    let mut lists: Vec<&Vec<String>> = contract.components.iter().map(|c| &c.provenance).collect();
    lists.extend(contract.rules.iter().map(|rule| &head(rule).provenance));
    if let Some(declarations) = &contract.declarations {
        declaration_provenance(declarations, &mut lists);
    }
    lists.into_iter().flatten().cloned().collect()
}

fn declaration_provenance<'a>(declarations: &'a Declarations, lists: &mut Vec<&'a Vec<String>>) {
    let d = declarations;
    lists.extend(d.capabilities.iter().map(|item| &item.provenance));
    lists.extend(d.review_scopes.iter().map(|item| &item.provenance));
    lists.extend(d.public_commands.iter().map(|item| &item.provenance));
    lists.extend(d.paths.iter().map(|item| &item.provenance));
    lists.extend(d.spot_owners.iter().map(|item| &item.provenance));
    lists.extend(d.measurement_budgets.iter().map(|item| &item.provenance));
    lists.extend(
        d.facade_budgets
            .iter()
            .flatten()
            .map(|item| &item.provenance),
    );
    lists.extend(
        d.coupling_budgets
            .iter()
            .flatten()
            .map(|item| &item.provenance),
    );
    if let Some(target) = &d.uml {
        lists.extend(target.entities.iter().map(|item| &item.provenance));
        lists.extend(target.relationships.iter().map(|item| &item.provenance));
        lists.extend(target.scopes.iter().map(|item| &item.provenance));
    }
    lists.push(&d.public_api_provenance);
    lists.push(&d.context_roots_provenance);
}

/// Python `_unsupported_inside_declaration_fields`: the declarations that only a root holds.
pub(crate) fn unsupported_fields(contract: &Contract) -> Vec<&'static str> {
    let Some(d) = &contract.declarations else {
        return Vec::new();
    };
    let held = |values: Option<usize>| values.is_some_and(|count| count > 0);
    let fields = [
        ("capabilities", Some(d.capabilities.len())),
        ("review_scopes", Some(d.review_scopes.len())),
        ("public_api", Some(d.public_api.len())),
        ("public_api_provenance", Some(d.public_api_provenance.len())),
        ("public_commands", Some(d.public_commands.len())),
        ("context_roots", Some(d.context_roots.len())),
        (
            "context_roots_provenance",
            Some(d.context_roots_provenance.len()),
        ),
        ("paths", Some(d.paths.len())),
        ("spot_owners", Some(d.spot_owners.len())),
        ("compat", Some(d.compat.len())),
        ("measurement_budgets", Some(d.measurement_budgets.len())),
        ("facade_budgets", d.facade_budgets.as_ref().map(Vec::len)),
        (
            "coupling_budgets",
            d.coupling_budgets.as_ref().map(Vec::len),
        ),
    ];
    fields
        .into_iter()
        .filter(|(_, count)| held(*count))
        .map(|(name, _)| name)
        .collect()
}

fn scoped_id(prefix: &str, id: &ItemId) -> ItemId {
    ItemId(format!("{prefix}:{}", id.0))
}

/// Python `f"{prefix}:{value}" if value else None`: an empty ID has no scope.
fn scoped_option(prefix: &str, id: Option<&ItemId>) -> Option<ItemId> {
    id.filter(|value| !value.0.is_empty())
        .map(|value| scoped_id(prefix, value))
}

/// Python `scoped_target`: the UML Target with each ID in the scope of the parent.
fn scoped_target(target: &Target, prefix: &str) -> Target {
    let mut scoped = target.clone();
    for entity in &mut scoped.entities {
        entity.id = scoped_id(prefix, &entity.id);
        entity.parent_id = scoped_option(prefix, entity.parent_id.as_ref());
    }
    for edge in &mut scoped.relationships {
        edge.id = scoped_id(prefix, &edge.id);
        edge.source_id = scoped_id(prefix, &edge.source_id);
        edge.target_id = scoped_option(prefix, edge.target_id.as_ref());
    }
    for scope in &mut scoped.scopes {
        scope.scope_id = scoped_id(prefix, &scope.scope_id);
    }
    scoped
}

/// Python `_scoped_inside_contract`: the IDs of components, rules and the UML Target in the scope
/// of the parent. The digest stays the digest of the bytes.
pub(crate) fn scoped_contract(parent_id: &str, contract: &Contract) -> Contract {
    let mut scoped = contract.clone();
    for component in &mut scoped.components {
        component.id = scoped_id(parent_id, &component.id);
    }
    for rule in &mut scoped.rules {
        let head = crate::policy::heads::head_mut(rule);
        head.id = scoped_id(parent_id, &head.id);
    }
    if let Some(declarations) = &mut scoped.declarations {
        declarations.uml = declarations
            .uml
            .as_ref()
            .map(|target| scoped_target(target, parent_id));
    }
    scoped
}
