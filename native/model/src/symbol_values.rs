// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The value bindings of call results and the construction sites of the symbol table (AD-502).
//!
//! Reference engine: `ir/source_graph.py` `_value_bindings`, `_reconcile_result_binding` and
//! `_construction_sites` at release 4.0.1. A construction gives one `creates` edge from the
//! caller and one `instance_of` edge from each bound value. Only a resolved construction of one
//! classifier that a plain name stores is a resolved edge.

use archkeel_contract::{EntityKind, RelationshipKind, ResolutionKind};
use archkeel_facts::data::CallData;
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::nested::{Construction, ResultBinding};
use archkeel_facts::vocab::Status;

use crate::symbols::resolution;
use crate::symbols::{evidence, Edge, Entity, Symbols};

/// `_value_bindings`: the binding entities of the results of one call, with their target kind.
pub(crate) fn bindings(
    table: &mut Symbols,
    source: &str,
    sites: &[ResultBinding],
    call: &[EvidenceId],
) -> Vec<(String, bool)> {
    let Some(owner) = table.get(source).map(|owner| owner.name.clone()) else {
        table.refuse("a result binding has no owner");
        return Vec::new();
    };
    let mut result = Vec::new();
    for site in sites {
        let valid = !site.evidence_ids.is_empty()
            && !site.id.as_str().is_empty()
            && !site.name.is_empty()
            && !site.initializer.is_empty()
            && matches!(
                site.target_kind.as_str(),
                "name" | "attribute" | "subscript"
            );
        if !valid {
            table.refuse("a result binding is not valid");
            continue;
        }
        let Some(value) = binding(table, source, &owner, site, call) else {
            table.refuse("a result binding conflicts with its definition");
            continue;
        };
        let id = value.id.clone();
        match table.by_id.get(&id).copied() {
            Some(index) => table.entities[index] = value,
            None => table.push(value),
        }
        result.push((id, site.target_kind == "name"));
    }
    result
}

/// The binding entity of one site, merged with a definition of the same id; `None` when they
/// conflict (`_reconcile_result_binding`).
fn binding(
    table: &Symbols,
    source: &str,
    owner: &str,
    site: &ResultBinding,
    call: &[EvidenceId],
) -> Option<Entity> {
    let mut name = format!("{owner}.{}", site.name);
    let mut annotation = site.annotation.clone();
    let mut conditional = !site.definition_contexts.is_empty();
    let mut found = evidence(call);
    found.extend(evidence(&site.evidence_ids));
    if let Some(previous) = table.get(site.id.as_str()) {
        let plain = previous.kind == EntityKind::Binding
            && previous.parent.as_deref() == Some(source)
            && previous.initializer.is_none();
        let same_name = if site.target_kind == "name" {
            previous.name.starts_with(&format!("{owner}."))
                && previous.name.rsplit('.').next() == Some(site.name.as_str())
        } else {
            previous.name == name
        };
        let same_annotation = match (&previous.annotation, &annotation) {
            (Some(old), Some(new)) => old == new,
            _ => true,
        };
        // 4.0.1 compares the two context lists; the table keeps only whether one exists.
        if !plain || !same_name || !same_annotation || (previous.conditional && conditional) {
            return None;
        }
        name.clone_from(&previous.name);
        annotation = annotation.or_else(|| previous.annotation.clone());
        conditional |= previous.conditional;
        found.extend(previous.evidence.iter().cloned());
    }
    found.sort();
    found.dedup();
    let mut value = Entity::named(
        site.id.as_str().to_owned(),
        EntityKind::Binding,
        &name,
        found,
    );
    value.parent = Some(source.to_owned());
    value.annotation = annotation;
    value.conditional = conditional;
    value.initializer = Some(site.initializer.clone());
    Some(value)
}

/// `_construction_sites`: the `creates` edge of the caller and the `instance_of` edge of each
/// bound value of one construction.
pub(crate) fn construction(
    table: &mut Symbols,
    (call, found): (&CallData, &Construction),
    (source, cited): (&str, &[EvidenceId]),
    bindings: &[(String, bool)],
) {
    let Some(status) = resolution(found.status) else {
        return table.refuse("a construction has no resolution status");
    };
    let unresolved = status == ResolutionKind::Unresolved;
    let within = found.targets.iter().all(|name| call.targets.contains(name));
    let resolved_call = call.status == Status::Resolved;
    let valid = unresolved == found.targets.is_empty()
        && !found.reason.is_empty()
        && within
        && (status != ResolutionKind::Resolved
            || (resolved_call && !found.candidates_truncated && found.targets.len() == 1));
    if !valid {
        return table.refuse("a construction conflicts with its call site");
    }
    let mut targets: Vec<String> = found
        .targets
        .iter()
        .flat_map(|name| table.resolving(name))
        .filter(|index| {
            matches!(
                table.entities[*index].kind,
                EntityKind::Class | EntityKind::Interface | EntityKind::Enum
            )
        })
        .map(|index| table.entities[index].id.clone())
        .collect();
    targets.sort();
    targets.dedup();
    if !unresolved && targets.is_empty() {
        return table.refuse("a construction has no classifier candidate");
    }
    let resolved =
        status == ResolutionKind::Resolved && targets.len() == 1 && !found.candidates_truncated;
    let mut relations = vec![(RelationshipKind::Creates, source.to_owned(), true)];
    relations.extend(
        bindings
            .iter()
            .map(|(id, stored)| (RelationshipKind::InstanceOf, id.clone(), *stored)),
    );
    for (kind, caller, stored) in relations {
        let proven = resolved && stored;
        table.edges.push(Edge {
            kind,
            source: caller,
            target: proven.then(|| targets[0].clone()),
            resolution: if proven {
                ResolutionKind::Resolved
            } else if unresolved {
                ResolutionKind::Unresolved
            } else {
                ResolutionKind::Partial
            },
            evidence: evidence(cited),
        });
    }
}
