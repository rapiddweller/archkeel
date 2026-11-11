// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declared_graph` of `ir/target_graph.py`: the checks that Python runs when a contract declares
//! a UML Target. The graph itself is not kept; only its errors are.

use sha2::{Digest, Sha256};

use crate::error::{invalid, Parsed};
use crate::graph_check::{validate, Graph};
use crate::model::{Component, DecidedBy, ItemId};
use crate::model_declarations::Declarations;
use crate::model_uml::{
    Entity, EntityKind, GraphSchemaVersion, PresenceKind, Relationship, RelationshipKind,
    ResolutionKind, Target, Visibility, VisibilityBasis, VisibilityKind,
};
use crate::rule::Rule;
use crate::words::spelling;

fn hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Python `repr` of a text, for the texts of a contract.
fn python_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut written = String::from(quote);
    for character in text.chars() {
        match character {
            '\\' => written.push_str("\\\\"),
            '\t' => written.push_str("\\t"),
            '\n' => written.push_str("\\n"),
            '\r' => written.push_str("\\r"),
            other if other == quote => {
                written.push('\\');
                written.push(other);
            }
            other if u32::from(other) < 0x20 || (0x7f..0xa1).contains(&u32::from(other)) => {
                written.push_str(&format!("\\x{:02x}", u32::from(other)));
            }
            other => written.push(other),
        }
    }
    written.push(quote);
    written
}

/// Python `str` of a tuple of texts.
fn python_tuple(values: &[String]) -> String {
    let items: Vec<String> = values.iter().map(|value| python_repr(value)).collect();
    match items.as_slice() {
        [] => "()".to_owned(),
        [one] => format!("({one},)"),
        _ => format!("({})", items.join(", ")),
    }
}

/// `stable_id`: a prefix and 16 hex characters of the SHA-256 of the parts.
fn stable_id(prefix: &str, parts: &[String]) -> ItemId {
    ItemId(format!(
        "{prefix}-{}",
        &hex(parts.join("\u{1f}").as_bytes())[..16]
    ))
}

/// `public_api_id`.
fn public_api_id(selector: &str) -> ItemId {
    ItemId(format!("API-{}", &hex(selector.as_bytes())[..16]))
}

fn sorted(values: &[String]) -> Vec<String> {
    let mut values = values.to_vec();
    values.sort();
    values
}

fn plain_entity(id: ItemId, kind: EntityKind, name: String, language: String) -> Entity {
    Entity {
        id,
        kind,
        qualified_name: name,
        language,
        parent_id: None,
        visibility: Visibility {
            kind: VisibilityKind::Unknown,
            basis: VisibilityBasis::Unknown,
            spelling: None,
        },
        signature: None,
        annotation: None,
        modifiers: Vec::new(),
        presence: PresenceKind::Planned,
        responsibilities: Vec::new(),
        evidence_ids: Vec::new(),
        provenance: Vec::new(),
        record_ids: Vec::new(),
        definition_contexts: Vec::new(),
        initializer: None,
        file_path: None,
    }
}

/// The component of the contract as a planned component entity.
fn owner(component: &Component) -> Entity {
    let name = component
        .namespace
        .as_ref()
        .map_or_else(|| component.label.0.clone(), |package| package.0.clone());
    let mut entity = plain_entity(
        component.id.clone(),
        EntityKind::Component,
        name,
        "architecture".to_owned(),
    );
    entity.responsibilities = sorted(&component.responsibilities);
    entity.provenance = sorted(&component.provenance);
    entity
}

/// `component_permissions`: one `requires` relationship for each entry of each component.
fn requirements(components: &[Component]) -> Vec<Relationship> {
    let mut edges = Vec::new();
    for component in components {
        let mut seen: Vec<(String, Vec<String>, String, Option<DecidedBy>)> = Vec::new();
        for entry in component.requires.iter().flatten() {
            let target = components
                .iter()
                .find(|other| other.label == entry.component);
            let Some(target) = target else { continue };
            let through = sorted(&wrap_texts(&entry.through));
            let decided_by = entry.decided_by.or(component.decided_by);
            let key = (
                entry.component.0.clone(),
                through.clone(),
                entry.rationale.clone(),
                decided_by,
            );
            let occurrence = seen.iter().filter(|item| **item == key).count();
            seen.push(key);
            let decider = decided_by.map_or_else(|| "None".to_owned(), |by| spelling(&by));
            let parts = [
                component.id.0.clone(),
                target.id.0.clone(),
                python_tuple(&through),
                entry.rationale.clone(),
                decider,
                occurrence.to_string(),
            ];
            edges.push(Relationship {
                id: stable_id("TARGET-REQUIRES", &parts),
                kind: RelationshipKind::Requires,
                source_id: component.id.clone(),
                target_id: Some(target.id.clone()),
                resolution: ResolutionKind::NotApplicable,
                candidate_ids: Vec::new(),
                expression: None,
                evidence_ids: Vec::new(),
                provenance: sorted(&component.provenance),
                record_ids: Vec::new(),
                candidate_count: None,
                candidates_truncated: false,
                reason: Some(entry.rationale.clone()),
                through,
                decided_by,
            });
        }
    }
    edges
}

fn wrap_texts(values: &[crate::model::Selector]) -> Vec<String> {
    values.iter().map(|value| value.0.clone()).collect()
}

/// The checks of `intent_graph` before it builds the graph.
fn intent_checks(target: &Target) -> Parsed<()> {
    for entity in &target.entities {
        let planned = entity.presence == PresenceKind::Planned;
        if entity.kind == EntityKind::Component && !planned {
            return Err(invalid("UML component owners need planned intent"));
        }
        let independent = planned || entity.presence == PresenceKind::Referenced;
        if !independent || !entity.record_ids.is_empty() {
            return Err(invalid(
                "UML entities need independent planned or referenced intent",
            ));
        }
        if planned && entity.responsibilities.is_empty() {
            return Err(invalid("UML entities need a responsibility"));
        }
    }
    if target
        .relationships
        .iter()
        .any(|edge| !edge.record_ids.is_empty())
    {
        return Err(invalid("UML relationships cannot cite observed record IDs"));
    }
    if target
        .relationships
        .iter()
        .any(|edge| edge.kind == RelationshipKind::Requires)
    {
        return Err(invalid(
            "dependency permissions belong in component requires",
        ));
    }
    Ok(())
}

/// The ids of the module inventory, the layout rules and the external scopes.
fn physical_ids(declarations: &Declarations, rules: &[Rule]) -> Vec<ItemId> {
    let inventory = declarations.modules.as_ref().map(|_| {
        stable_id(
            "MODULE-TARGET-INVENTORY",
            &["architecture-contract.json".to_owned()],
        )
    });
    let layouts = rules.iter().filter_map(|rule| match rule {
        Rule::RootLayout(rule) => Some(rule.head.id.clone()),
        _ => None,
    });
    let externals = rules.iter().filter_map(|rule| match rule {
        Rule::ExternalDependencyScope(rule) => Some(rule.head.id.clone()),
        _ => None,
    });
    inventory
        .into_iter()
        .chain(layouts)
        .chain(externals)
        .collect()
}

/// `declared_graph`: build the declared graph of a contract with a UML Target and check it.
pub(crate) fn check_declared_graph(
    components: &[Component],
    rules: &[Rule],
    declarations: &Declarations,
    target: &Target,
) -> Parsed<()> {
    intent_checks(target)?;
    let lifecycle = components
        .iter()
        .any(|component| component.lifecycle.is_some());
    let layer = components.iter().any(|component| component.layer.is_some());
    let version = match (lifecycle, layer) {
        (true, _) => GraphSchemaVersion::V1_3,
        (false, true) => GraphSchemaVersion::V1_2,
        _ => target.schema_version,
    };
    let mut api: Vec<String> = declarations
        .public_api
        .iter()
        .map(|item| item.0.clone())
        .collect();
    api.sort();
    let mut graph = Graph {
        version,
        entities: components
            .iter()
            .map(owner)
            .chain(target.entities.iter().cloned())
            .collect(),
        relationships: target.relationships.clone(),
        scopes: target.scopes.clone(),
        physical_ids: physical_ids(declarations, rules),
        api_ids: api.iter().map(|selector| public_api_id(selector)).collect(),
        api_without_provenance: !api.is_empty() && declarations.public_api_provenance.is_empty(),
        api_public_and_planned: components.iter().any(|component| {
            let public = component.public.iter().flatten();
            public.into_iter().any(|entry| {
                component
                    .planned
                    .iter()
                    .flatten()
                    .any(|other| other == entry)
            })
        }),
    };
    validate(&graph)?;
    if crate::graph_link::link(&mut graph)? {
        validate(&graph)?;
    }
    let mut edges = requirements(components);
    edges.append(&mut graph.relationships);
    graph.relationships = edges;
    validate(&graph)
}
