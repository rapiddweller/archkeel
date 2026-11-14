// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol part of the comparison of a UML target (AD-512): the symbol entities and the
//! relationships other than `imports`.
//!
//! Reference engine: `check/uml_compare.py` `_matches`, `_entity`, `_containment` and
//! `_relationship` at release 4.0.1, with one stricter rule: the core proves no complete symbol,
//! call or reference inventory, so an absent symbol, call or reference is UNKNOWN, not FAIL. A
//! missing base is FAIL only when the run is complete and every base of the class and of each
//! class inside it is resolved (the base receipt of `_coverage`).

use archkeel_contract::{Entity, EntityKind, PresenceKind, Relationship, RelationshipKind};
use archkeel_contract::{ResolutionKind, Target};

use crate::symbols::{self, Symbols};
use crate::uml_facts::{entity, word, Assessed, Facts, UmlDiff};

const TYPE_ONLY: &[EntityKind] = &[EntityKind::Interface, EntityKind::TypeAlias];
const VALUE_ONLY: &[EntityKind] = &[
    EntityKind::Method,
    EntityKind::Function,
    EntityKind::Attribute,
    EntityKind::Constant,
    EntityKind::Binding,
    EntityKind::EnumLiteral,
];
const BASES: &[RelationshipKind] = &[
    RelationshipKind::Inherits,
    RelationshipKind::Realizes,
    RelationshipKind::MixesIn,
];

/// `_matches`: the observed entities that a target entity names, or the cause that the symbol
/// table cannot decide it.
pub(crate) fn matches<'s>(
    facts: &Facts<'s>,
    wanted: &Entity,
) -> Result<Vec<&'s symbols::Entity>, String> {
    let table = facts.symbols()?;
    if wanted.language() != facts.language {
        return Ok(Vec::new());
    }
    let kind = *wanted.kind();
    let namespace = matches!(kind, EntityKind::Module | EntityKind::Package);
    // A profile with a type and a value namespace keeps them apart.
    let excluded = match (facts.namespaces, TYPE_ONLY.contains(&kind)) {
        (true, true) => VALUE_ONLY,
        (true, false) if VALUE_ONLY.contains(&kind) => TYPE_ONLY,
        _ => &[],
    };
    let referenced = *wanted.presence() == PresenceKind::Referenced;
    let mut found: Vec<&symbols::Entity> = table
        .matching(wanted.qualified_name())
        .into_iter()
        .map(|index| &table.entities[index])
        .filter(|item| item.defined || referenced)
        .filter(|item| {
            if namespace {
                item.kind == kind
            } else {
                !matches!(item.kind, EntityKind::Module | EntityKind::Package)
            }
        })
        .filter(|item| !excluded.contains(&item.kind))
        .collect();
    let member = |kind: EntityKind| matches!(kind, EntityKind::Attribute | EntityKind::Binding);
    if kind == EntityKind::EnumLiteral {
        // A field or a value binding alone does not prove a member of an enum.
        found.retain(|item| !member(item.kind));
    } else if member(kind) && found.iter().any(|item| item.kind == kind) {
        found.retain(|item| item.kind == kind || !member(item.kind));
    }
    Ok(found)
}

/// `_entity` for a symbol entity.
pub(crate) fn assess(facts: &Facts<'_>, target: &Target, wanted: &Entity) -> Vec<Assessed> {
    let found = match matches(facts, wanted) {
        Ok(found) => found,
        Err(cause) => return vec![Assessed::Unknown(cause)],
    };
    if *wanted.presence() == PresenceKind::Referenced {
        return match found.as_slice() {
            [actual] => crate::uml_details::details(wanted, actual),
            _ => unknown("referenced endpoint without one definition"),
        };
    }
    let actual = match found.as_slice() {
        [] => return unknown("absent symbol: the symbol inventory is not complete"),
        [actual] => *actual,
        _ => return unknown("several definitions share a declared name"),
    };
    if actual.conditional {
        return unknown("definition under control flow");
    }
    if actual.kind != *wanted.kind() {
        return vec![Assessed::Fail(UmlDiff {
            subject: wanted.id().as_text().to_owned(),
            fact: format!("{} is a {}", actual.name, word(&actual.kind)),
            cause: "recorded entity kind differs",
            evidence: actual.evidence.clone(),
        })];
    }
    let mut result = vec![Assessed::Pass];
    result.extend(containment(facts, target, wanted, actual));
    result.extend(crate::uml_details::details(wanted, actual));
    result
}

fn unknown(cause: &str) -> Vec<Assessed> {
    vec![Assessed::Unknown(cause.to_owned())]
}

/// `_containment`: the lexical parent of a matched entity.
fn containment(
    facts: &Facts<'_>,
    target: &Target,
    wanted: &Entity,
    actual: &symbols::Entity,
) -> Vec<Assessed> {
    let parent = wanted
        .parent_id()
        .as_ref()
        .and_then(|id| entity(target, id.as_text()));
    let Some(parent) = parent else {
        return Vec::new();
    };
    match parent.kind() {
        EntityKind::Component => return Vec::new(),
        EntityKind::Package if *wanted.kind() != EntityKind::Module => return Vec::new(),
        _ => {}
    }
    let found = matches(facts, parent).unwrap_or_default();
    let ([owner], Some(recorded)) = (found.as_slice(), actual.parent.as_deref()) else {
        return unknown("lexical parent cannot be identified");
    };
    if owner.id == recorded {
        return vec![Assessed::Pass];
    }
    vec![Assessed::Fail(UmlDiff {
        subject: wanted.id().as_text().to_owned(),
        fact: format!("{} lies in {recorded}", actual.name),
        cause: "lexical parent differs",
        evidence: actual.evidence.clone(),
    })]
}

/// `_relationship` for each kind but `imports`; `complete` is the scope proof of the run.
pub(crate) fn relationship(
    facts: &Facts<'_>,
    target: &Target,
    edge: &Relationship,
    complete: bool,
) -> Assessed {
    let kind = *edge.kind();
    let end = |id: &str| entity(target, id).map(|item| matches(facts, item));
    let source = end(edge.source_id().as_text());
    let found = edge.target_id().as_ref().and_then(|id| end(id.as_text()));
    let (Some(Ok(sources)), Some(Ok(targets))) = (source, found) else {
        return Assessed::Unknown("relationship endpoint cannot be identified".to_owned());
    };
    let ([from], [to]) = (sources.as_slice(), targets.as_slice()) else {
        return Assessed::Unknown(
            "relationship endpoints cannot be identified uniquely".to_owned(),
        );
    };
    if from.conditional || to.conditional {
        return Assessed::Unknown("relationship endpoint under control flow".to_owned());
    }
    let Ok(table) = facts.symbols() else {
        return Assessed::Unknown("relationship endpoint without symbol facts".to_owned());
    };
    let sites: Vec<_> = table
        .edges
        .iter()
        .filter(|site| site.kind == kind && site.source == from.id)
        .collect();
    let matched = sites.iter().any(|site| {
        site.resolution == ResolutionKind::Resolved && site.target.as_deref() == Some(&to.id)
    });
    if matched {
        return Assessed::Pass;
    }
    if sites
        .iter()
        .any(|site| site.resolution != ResolutionKind::Resolved)
    {
        return Assessed::Unknown(format!("unresolved {} site", word(&kind)));
    }
    if BASES.contains(&kind) && complete && bases_complete(table, &from.id) {
        return Assessed::Fail(UmlDiff {
            subject: edge.id().as_text().to_owned(),
            fact: format!("{} -> {}", from.name, to.name),
            cause: "declared base is absent",
            evidence: from.evidence.clone(),
        });
    }
    Assessed::Unknown(format!("{} inventory is not complete", word(&kind)))
}

/// The base receipt of a class: each base of the class and of each class inside it resolves.
fn bases_complete(table: &Symbols, class: &str) -> bool {
    table.bases.get(class) == Some(&true)
        && table.bases.iter().all(|(id, resolved)| {
            *resolved || id == class || !table.ancestors(id).iter().any(|item| item == class)
        })
}

#[cfg(test)]
#[path = "uml_symbols_tests.rs"]
mod tests;
