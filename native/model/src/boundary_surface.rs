// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The public surface that a `boundary_types` rule reads (AD-550): the entries of the `public`
//! lists below the `source` of the rule, the names that each entry covers, and the definitions
//! that some component declares.
//!
//! A facade module covers the names of its literal export list and nothing else. A module with
//! no literal list is a named gap: a decorated function has no record, so a list built from the
//! records could pass it by.

use std::collections::HashSet;

use archkeel_contract::BoundaryTypes;

use crate::boundary_facts::{BoundaryFacts, Origin};
use crate::boundary_judge::{GapCause, GapRow};
use crate::model::Model;
use crate::ownership::in_scope;

/// One entry of a `public` list.
pub(crate) struct PublicEntry {
    pub(crate) text: String,
    pub(crate) module: String,
    pub(crate) name: Option<String>,
}

/// True for a name that a facade covers: no leading underscore (`facade_covers`).
fn covered_name(name: &str) -> bool {
    !name.starts_with('_')
}

/// The entries of every `public` list, or only those that the rule reads: below its `source`, and
/// not exempt by `allowed_sources` or `exact_sources`.
pub(crate) fn entries(model: &Model, only: Option<&BoundaryTypes>) -> Vec<PublicEntry> {
    let all = model
        .contract()
        .components()
        .iter()
        .flat_map(|component| component.public().iter().flatten())
        .map(|entry| entry_of(entry.as_text()));
    all.filter(|entry| only.is_none_or(|rule| reads(rule, &entry.module)))
        .collect()
}

fn entry_of(text: &str) -> PublicEntry {
    let (module, name) = match text.split_once(':') {
        Some((module, name)) => (module, Some(name.to_owned())),
        None => (text, None),
    };
    PublicEntry {
        text: text.to_owned(),
        module: module.to_owned(),
        name,
    }
}

/// True when the rule reads the facade module: below its source and not exempt.
fn reads(rule: &BoundaryTypes, module: &str) -> bool {
    let allowed = rule
        .allowed_sources()
        .iter()
        .any(|allowed| in_scope(module, allowed.as_text()));
    let exact = rule
        .exact_sources()
        .iter()
        .any(|exact| exact.as_text() == module);
    in_scope(module, rule.source().as_text()) && !allowed && !exact
}

/// The names that an entry covers, or the gap that stops the list.
pub(crate) fn names(model: &Model, entry: &PublicEntry) -> Result<Vec<String>, GapRow> {
    let gap = |cause: GapCause, text: &str| GapRow {
        subject: entry.text.clone(),
        cause,
        text: text.to_owned(),
    };
    let found = model
        .graph()
        .modules()
        .iter()
        .find(|(_, module)| module.name() == entry.module);
    let Some((_, module)) = found else {
        let text = "the module of the entry is not scanned";
        return Err(gap(GapCause::UnresolvedFacadeEntry, text));
    };
    if let Some(name) = &entry.name {
        return Ok(Some(name.clone())
            .filter(|name| covered_name(name))
            .into_iter()
            .collect());
    }
    if module.exports_literal() {
        let exports = module.exports().iter().filter(|name| covered_name(name));
        return Ok(exports.cloned().collect());
    }
    Err(gap(
        GapCause::DynamicExports,
        "the module states no literal list of exports",
    ))
}

/// The definitions that each component declares: the origin of each covered name.
pub(crate) fn declared(model: &Model, facts: &BoundaryFacts) -> HashSet<String> {
    let mut found = HashSet::new();
    for entry in entries(model, None) {
        let Ok(covered) = names(model, &entry) else {
            continue;
        };
        let origins = covered.iter().map(|name| facts.origin(&entry.module, name));
        for origin in origins {
            match origin {
                Origin::Defined(qualified, _) => {
                    found.insert(qualified.to_owned());
                }
                // A class that a standard decorator keeps a class (AD-782).
                Origin::Missing { qualified, .. } if facts.wrapped(&qualified).is_some() => {
                    found.insert(qualified);
                }
                _ => {}
            }
        }
    }
    found
}
