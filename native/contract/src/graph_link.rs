// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_link_references` of `ir/target_graph.py`: a referenced Target entity is linked to its one
//! planned definition and leaves the graph.

use crate::error::{invalid, Parsed};
use crate::graph_check::Graph;
use crate::model::ItemId;
use crate::model_uml::{Entity, PresenceKind, VisibilityBasis, VisibilityKind};

/// A reference carries only its identity, its owner and its provenance.
fn bare_reference(entity: &Entity) -> bool {
    entity.visibility.kind == VisibilityKind::Unknown
        && entity.visibility.basis == VisibilityBasis::Unknown
        && entity.visibility.spelling.is_none()
        && entity.signature.is_none()
        && entity.annotation.is_none()
        && entity.modifiers.is_empty()
        && entity.responsibilities.is_empty()
        && entity.evidence_ids.is_empty()
        && entity.record_ids.is_empty()
        && entity.definition_contexts.is_empty()
        && entity.initializer.is_none()
        && entity.file_path.is_none()
}

/// The (reference id, definition index) pairs of the graph.
fn aliases(graph: &Graph) -> Parsed<Vec<(ItemId, usize)>> {
    let mut found = Vec::new();
    for entity in &graph.entities {
        if entity.presence != PresenceKind::Referenced {
            continue;
        }
        let matches: Vec<usize> = graph
            .entities
            .iter()
            .enumerate()
            .filter(|(_, other)| {
                other.presence == PresenceKind::Planned
                    && other.language == entity.language
                    && other.kind == entity.kind
                    && other.qualified_name == entity.qualified_name
            })
            .map(|(index, _)| index)
            .collect();
        match matches.as_slice() {
            [] => continue,
            [definition] => {
                if !bare_reference(entity) {
                    return Err(invalid("Target reference carries definition constraints"));
                }
                found.push((entity.id.clone(), *definition));
            }
            _ => return Err(invalid("ambiguous Target reference")),
        }
    }
    Ok(found)
}

/// Link the references of the graph. Returns whether the graph changed.
pub(crate) fn link(graph: &mut Graph) -> Parsed<bool> {
    let pairs = aliases(graph)?;
    if pairs.is_empty() {
        return Ok(false);
    }
    let alias_of = |id: &ItemId| pairs.iter().find(|(alias, _)| alias == id);
    if graph
        .scopes
        .iter()
        .any(|scope| alias_of(&scope.scope_id).is_some())
    {
        return Err(invalid("Target reference cannot own a completeness scope"));
    }
    let identity = |id: &ItemId| -> ItemId {
        alias_of(id).map_or_else(|| id.clone(), |(_, index)| definition_id(graph, *index))
    };
    for entity in &graph.entities {
        let (Some((_, index)), Some(parent)) = (alias_of(&entity.id), &entity.parent_id) else {
            continue;
        };
        let definition_parent = graph
            .entities
            .get(*index)
            .and_then(|item| item.parent_id.as_ref());
        if definition_parent.is_none_or(|owner| identity(parent) != identity(owner)) {
            return Err(invalid("Target reference owner differs"));
        }
    }
    let mut provenance: Vec<Vec<String>> = graph
        .entities
        .iter()
        .map(|item| item.provenance.clone())
        .collect();
    for (alias, index) in &pairs {
        let extra = graph
            .entities
            .iter()
            .find(|item| item.id == *alias)
            .map(|item| item.provenance.clone())
            .unwrap_or_default();
        if let Some(paths) = provenance.get_mut(*index) {
            paths.extend(extra);
        }
    }
    let entities = graph
        .entities
        .iter()
        .zip(provenance)
        .filter(|(entity, _)| alias_of(&entity.id).is_none())
        .map(|(entity, mut paths)| {
            paths.sort();
            paths.dedup();
            let mut linked = entity.clone();
            linked.parent_id = entity.parent_id.as_ref().map(&identity);
            linked.provenance = paths;
            linked
        })
        .collect();
    let relationships = graph
        .relationships
        .iter()
        .map(|edge| {
            let mut linked = edge.clone();
            linked.source_id = identity(&edge.source_id);
            linked.target_id = edge.target_id.as_ref().map(&identity);
            linked.candidate_ids = edge.candidate_ids.iter().map(&identity).collect();
            linked
        })
        .collect();
    graph.entities = entities;
    graph.relationships = relationships;
    Ok(true)
}

fn definition_id(graph: &Graph, index: usize) -> ItemId {
    graph
        .entities
        .get(index)
        .map_or_else(|| ItemId(String::new()), |entity| entity.id.clone())
}
