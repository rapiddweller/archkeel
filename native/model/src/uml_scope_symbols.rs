// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol part of a closed scope of a UML target (AD-496): each defined symbol of a listed
//! kind and each resolved site of a listed kind inside the scope that the target does not list.
//!
//! Reference engine: `check/uml_compare.py` `_scope_assessments`, `_closed_relationship_assessments`
//! and `_within` at release 4.0.1. An unlisted element is FAIL. Without one, the scope stays
//! UNKNOWN: the core proves no complete symbol inventory (`uml_scope.rs`).

use archkeel_contract::{Entity, EntityKind, RelationshipKind, ResolutionKind, Target};

use crate::symbols::{self, Symbols};
use crate::uml_facts::{Facts, UmlDiff};
use crate::uml_symbols::matches;

/// The observed scope of a closed scope.
pub(crate) enum Observed {
    /// A package: the entities below its name.
    Prefix(String),
    /// A module or a symbol: the entities that have it as a lexical parent, by its id.
    Parent(String),
}

impl Observed {
    fn holds(&self, table: &Symbols, item: &symbols::Entity) -> bool {
        match self {
            Observed::Prefix(name) => item
                .name
                .strip_prefix(name.as_str())
                .is_some_and(|rest| rest.starts_with('.')),
            Observed::Parent(id) => *id != item.id && table.ancestors(&item.id).contains(id),
        }
    }
}

/// `_within` for the target: a package or component holds the names below it; another entity
/// holds its lexical children.
fn declared(target: &Target, scope: &Entity, item: &Entity) -> bool {
    if matches!(scope.kind(), EntityKind::Package | EntityKind::Component) {
        return item
            .qualified_name()
            .strip_prefix(scope.qualified_name())
            .is_some_and(|rest| rest.starts_with('.'));
    }
    let mut next = Some(item.id().as_text().to_owned());
    let mut seen = Vec::new();
    while let Some(id) = next {
        if id == scope.id().as_text() {
            return true;
        }
        if seen.contains(&id) {
            return false;
        }
        next = crate::uml_facts::entity(target, &id)
            .and_then(|found| found.parent_id().as_ref())
            .map(|parent| parent.as_text().to_owned());
        seen.push(id);
    }
    false
}

/// The unlisted symbols of the symbol kinds `kinds` in the scope.
pub(crate) fn extra_symbols(
    facts: &Facts<'_>,
    target: &Target,
    (scope, observed): (&Entity, &Observed),
    kinds: &[EntityKind],
) -> Result<Vec<UmlDiff>, String> {
    let table = facts.symbols()?;
    let listed: Vec<&Entity> = target
        .entities()
        .iter()
        .filter(|item| declared(target, scope, item))
        .collect();
    Ok(table
        .entities
        .iter()
        .filter(|item| item.defined && kinds.contains(&item.kind))
        .filter(|item| observed.holds(table, item))
        .filter(|item| {
            !listed
                .iter()
                .any(|entry| *entry.qualified_name() == item.name && *entry.kind() == item.kind)
        })
        .map(|item| UmlDiff {
            subject: scope.id().as_text().to_owned(),
            fact: item.name.clone(),
            cause: "closed scope holds an unlisted definition",
            evidence: item.evidence.clone(),
        })
        .collect())
}

/// The resolved sites of the kinds `kinds` from the scope that no relationship of the target
/// lists.
pub(crate) fn extra_sites(
    facts: &Facts<'_>,
    target: &Target,
    (scope, observed): (&Entity, &Observed),
    kinds: &[RelationshipKind],
) -> Result<Vec<UmlDiff>, String> {
    let table = facts.symbols()?;
    let ids = |id: &str| -> Vec<String> {
        crate::uml_facts::entity(target, id)
            .and_then(|item| matches(facts, item).ok())
            .map(|found| found.iter().map(|item| item.id.clone()).collect())
            .unwrap_or_default()
    };
    let expected: Vec<(RelationshipKind, Vec<String>, Vec<String>)> = target
        .relationships()
        .iter()
        .filter(|edge| {
            crate::uml_facts::entity(target, edge.source_id().as_text())
                .is_some_and(|source| declared(target, scope, source))
        })
        .filter_map(|edge| {
            let end = edge.target_id().as_ref()?;
            Some((
                *edge.kind(),
                ids(edge.source_id().as_text()),
                ids(end.as_text()),
            ))
        })
        .collect();
    let mut result = Vec::new();
    for site in &table.edges {
        let Some(end) = site.target.as_deref() else {
            continue;
        };
        let inside = table
            .get(&site.source)
            .is_some_and(|source| observed.holds(table, source) || observed.is_self(source));
        if !kinds.contains(&site.kind) || site.resolution != ResolutionKind::Resolved || !inside {
            continue;
        }
        let listed = expected.iter().any(|(kind, sources, targets)| {
            *kind == site.kind
                && sources.contains(&site.source)
                && targets.iter().any(|id| id == end)
        });
        if !listed {
            result.push(UmlDiff {
                subject: scope.id().as_text().to_owned(),
                fact: format!("{} {} -> {end}", word_of(site.kind), site.source),
                cause: "closed scope holds an unlisted relationship",
                evidence: site.evidence.clone(),
            });
        }
    }
    Ok(result)
}

impl Observed {
    /// True when `item` is the entity of the scope itself (`_ancestors` holds the entity).
    fn is_self(&self, item: &symbols::Entity) -> bool {
        matches!(self, Observed::Parent(id) if *id == item.id)
    }
}

fn word_of(kind: RelationshipKind) -> String {
    crate::uml_facts::word(&kind)
}
