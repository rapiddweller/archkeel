// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `ArchitectureGraph.validate` for a declared graph (`ir/architecture_graph.py`). Each failure is
//! a `ValueError` in Python, so the order of the checks here does not change the error kind.

use crate::error::{invalid, Parsed};
use crate::model::ItemId;
use crate::model_uml::{
    Entity, EntityKind, GraphSchemaVersion, ModifierKind, PresenceKind, Relationship,
    RelationshipKind, ResolutionKind, TargetScope,
};
use crate::names::has_text;
use crate::paths::normal_relative_path;
use crate::read::repeats;

/// The declared graph that `declared_graph` and `intent_graph` build.
pub(crate) struct Graph {
    pub(crate) version: GraphSchemaVersion,
    pub(crate) entities: Vec<Entity>,
    pub(crate) relationships: Vec<Relationship>,
    pub(crate) scopes: Vec<TargetScope>,
    /// The ids of the module inventory, the layout rules and the external scopes, in this order.
    pub(crate) physical_ids: Vec<ItemId>,
    /// The ids of the public API entries.
    pub(crate) api_ids: Vec<ItemId>,
    /// A public API entry exists and the API provenance is empty.
    pub(crate) api_without_provenance: bool,
    /// A component names one API entry as public and as planned.
    pub(crate) api_public_and_planned: bool,
}

fn fail<T>(message: &str) -> Parsed<T> {
    Err(invalid(message))
}

fn find<'a>(graph: &'a Graph, id: &ItemId) -> Option<&'a Entity> {
    graph.entities.iter().find(|entity| entity.id == *id)
}

fn classifier(kind: EntityKind) -> bool {
    matches!(
        kind,
        EntityKind::Class | EntityKind::Interface | EntityKind::Enum | EntityKind::Mixin
    )
}

fn referenced_symbol(entity: &Entity) -> bool {
    entity.kind == EntityKind::Symbol && entity.presence == PresenceKind::Referenced
}

/// `_validate_evidence` of a declared graph: no evidence reference and a provenance with text.
fn provenance(references: &[ItemId], paths: &[String]) -> Parsed<()> {
    if !references.is_empty() {
        return fail("unknown evidence reference");
    }
    if paths.is_empty() || paths.iter().any(|path| !has_text(path)) {
        return fail("Target needs independent provenance");
    }
    Ok(())
}

/// `validate` of a declared graph.
pub(crate) fn validate(graph: &Graph) -> Parsed<()> {
    let literal = graph
        .entities
        .iter()
        .any(|entity| entity.kind == EntityKind::EnumLiteral)
        || graph
            .scopes
            .iter()
            .any(|scope| scope.entity_kinds.contains(&EntityKind::EnumLiteral));
    if graph.version == GraphSchemaVersion::V1_0 && literal {
        return fail("enum literal needs graph schema_version 1.1.0");
    }
    let ids = record_ids(graph);
    if repeats(&ids) {
        return fail("duplicate graph identity");
    }
    graph
        .entities
        .iter()
        .try_for_each(|entity| entity_shape(graph, entity))?;
    planned_identities(graph)?;
    if graph.api_public_and_planned {
        return fail("a component API entry cannot be public and planned");
    }
    graph
        .relationships
        .iter()
        .try_for_each(|edge| relationship(graph, edge))?;
    scopes(graph)?;
    let mut seen = ids;
    for id in &graph.physical_ids {
        if id.0.is_empty() || seen.contains(&id) {
            return fail("duplicate or empty physical intent identity");
        }
        seen.push(id);
    }
    if graph.api_without_provenance {
        return fail("Target needs independent provenance");
    }
    for id in &graph.api_ids {
        if seen.contains(&id) {
            return fail("duplicate or empty public API identity");
        }
        seen.push(id);
    }
    Ok(())
}

fn record_ids(graph: &Graph) -> Vec<&ItemId> {
    let entities = graph.entities.iter().map(|entity| &entity.id);
    entities
        .chain(graph.relationships.iter().map(|edge| &edge.id))
        .collect()
}

/// The checks of one entity, in both loops of `_validate_entities`.
fn entity_shape(graph: &Graph, entity: &Entity) -> Parsed<()> {
    if entity.id.0.is_empty() || entity.qualified_name.is_empty() || entity.language.is_empty() {
        return fail("empty entity identity");
    }
    if let Some(path) = &entity.file_path {
        if entity.kind != EntityKind::Module || !normal_relative_path(path) {
            return fail("invalid module file path");
        }
    }
    if entity.kind == EntityKind::Component && entity.parent_id.is_some() {
        return fail("component containment belongs in component intent");
    }
    let parent = match &entity.parent_id {
        Some(id) => Some(find(graph, id).ok_or_else(|| invalid("unknown lexical parent"))?),
        None => None,
    };
    no_parent_cycle(graph, entity)?;
    let operation = matches!(entity.kind, EntityKind::Method | EntityKind::Function);
    if entity.signature.is_some() && !operation {
        return fail("signature on a non-operation");
    }
    let classifier_parent = parent.is_some_and(|owner| classifier(owner.kind));
    let planned = entity.presence == PresenceKind::Planned && entity.kind != EntityKind::Component;
    if planned && entity.kind == EntityKind::Attribute && !classifier_parent {
        return fail("planned attribute without a classifier");
    }
    if let (Some(signature), "python") = (&entity.signature, entity.language.as_str()) {
        let names: Vec<&String> = signature.parameters.iter().map(|item| &item.name).collect();
        if repeats(&names) {
            return fail("duplicate Python parameter name");
        }
    }
    if let Some(initializer) = &entity.initializer {
        if entity.kind != EntityKind::Binding || !has_text(initializer) {
            return fail("initializer needs a binding and non-empty source syntax");
        }
    }
    if entity.kind == EntityKind::Method && !classifier_parent {
        return fail("method without a classifier");
    }
    let enum_parent = parent.is_some_and(|owner| owner.kind == EntityKind::Enum);
    if entity.kind == EntityKind::EnumLiteral && (!enum_parent || !entity.modifiers.is_empty()) {
        return fail("enum literal needs an enumeration parent and no modifiers");
    }
    provenance(&entity.evidence_ids, &entity.provenance)?;
    if !entity.definition_contexts.is_empty() {
        return fail("definition contexts describe observed source declarations");
    }
    Ok(())
}

fn no_parent_cycle(graph: &Graph, entity: &Entity) -> Parsed<()> {
    let mut seen = vec![&entity.id];
    let mut parent = entity.parent_id.as_ref();
    while let Some(id) = parent {
        if seen.contains(&id) {
            return fail("lexical containment cycle");
        }
        seen.push(id);
        parent = find(graph, id).and_then(|owner| owner.parent_id.as_ref());
    }
    Ok(())
}

/// A planned entity that is not a component is unique by its name, kind, language, parent and
/// signature.
fn planned_identities(graph: &Graph) -> Parsed<()> {
    let planned: Vec<_> = graph
        .entities
        .iter()
        .filter(|entity| {
            entity.presence == PresenceKind::Planned && entity.kind != EntityKind::Component
        })
        .map(|entity| {
            (
                &entity.qualified_name,
                entity.kind,
                &entity.language,
                &entity.parent_id,
                &entity.signature,
            )
        })
        .collect();
    if repeats(&planned) {
        return fail("duplicate planned entity");
    }
    Ok(())
}

fn relationship(graph: &Graph, edge: &Relationship) -> Parsed<()> {
    let source =
        find(graph, &edge.source_id).ok_or_else(|| invalid("unknown relationship source"))?;
    let target = match &edge.target_id {
        Some(id) => Some(find(graph, id).ok_or_else(|| invalid("unknown relationship target"))?),
        None => None,
    };
    classifier_edge(edge.kind, source, target)?;
    permission(edge, source, target)?;
    let known = edge
        .candidate_ids
        .iter()
        .all(|id| find(graph, id).is_some());
    if repeats(&edge.candidate_ids) || !known {
        return fail("invalid relationship candidates");
    }
    let observed = edge.resolution != ResolutionKind::NotApplicable
        || !edge.candidate_ids.is_empty()
        || edge.candidate_count.is_some()
        || edge.candidates_truncated;
    if observed {
        return fail("Target does not assert observed resolution");
    }
    if target.is_none() {
        return fail("Target relationship needs a declared endpoint");
    }
    provenance(&edge.evidence_ids, &edge.provenance)
}

fn classifier_edge(kind: RelationshipKind, source: &Entity, target: Option<&Entity>) -> Parsed<()> {
    use RelationshipKind as R;
    if !matches!(kind, R::Inherits | R::Realizes | R::MixesIn) {
        return Ok(());
    }
    let endpoint = |entity: &Entity| classifier(entity.kind) || referenced_symbol(entity);
    if !endpoint(source) || target.is_some_and(|entity| !endpoint(entity)) {
        return fail("classifier relationship needs classifier endpoints");
    }
    let Some(target) = target.filter(|_| kind == R::MixesIn) else {
        return Ok(());
    };
    let class_source = matches!(source.kind, EntityKind::Class | EntityKind::Enum);
    if !class_source && !referenced_symbol(source) {
        return fail("mixes_in relationship needs a class or enum source");
    }
    let mixin_class =
        target.kind == EntityKind::Class && target.modifiers.contains(&ModifierKind::Mixin);
    if target.kind != EntityKind::Mixin && !mixin_class && !referenced_symbol(target) {
        return fail("mixes_in relationship needs a mixin-capable target");
    }
    Ok(())
}

/// `_validate_permission_metadata`.
fn permission(edge: &Relationship, source: &Entity, target: Option<&Entity>) -> Parsed<()> {
    if edge.kind != RelationshipKind::Requires {
        if !edge.through.is_empty() || edge.decided_by.is_some() {
            return fail("permission metadata belongs on requires relationships");
        }
        return Ok(());
    }
    let components = source.kind == EntityKind::Component
        && target.is_some_and(|entity| entity.kind == EntityKind::Component);
    let reason = edge.reason.as_deref().is_some_and(has_text);
    if !components || !reason || edge.expression.is_some() {
        return fail("dependency permission needs declared component endpoints and rationale");
    }
    if repeats(&edge.through) || edge.through.iter().any(|value| !has_text(&value.0)) {
        return fail("invalid dependency permission selector");
    }
    Ok(())
}

fn scopes(graph: &Graph) -> Parsed<()> {
    let mut seen: Vec<(&ItemId, String)> = Vec::new();
    for scope in &graph.scopes {
        if scope
            .relationship_kinds
            .contains(&RelationshipKind::Requires)
        {
            return fail("dependency permissions use existing Core rules, not UML completeness");
        }
        if find(graph, &scope.scope_id).is_none() {
            return fail("Target completeness needs a declared scope");
        }
        if !has_text(&scope.rationale) || scope.provenance.is_empty() {
            return fail("Target completeness needs rationale and provenance");
        }
        if scope.entity_kinds.is_empty() && scope.relationship_kinds.is_empty() {
            return fail("Target completeness needs an element or relationship kind");
        }
        let entity_words = scope.entity_kinds.iter().map(crate::words::spelling);
        let relationship_words = scope.relationship_kinds.iter().map(crate::words::spelling);
        for word in entity_words.chain(relationship_words) {
            let key = (&scope.scope_id, word);
            if seen.contains(&key) {
                return fail("duplicate Target completeness kind in a scope");
            }
            seen.push(key);
        }
        provenance(&[], &scope.provenance)?;
    }
    Ok(())
}
