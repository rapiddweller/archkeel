// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `parse_target` of `ir/graph_codec.py`: the UML Target of `declarations.uml`. The readers of that
//! codec differ from the contract readers: an absent key takes its default, and `null` is an error
//! where a default exists.

use serde::de::DeserializeOwned;

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::{wrap_all, DecidedBy, ItemId};
use crate::model_uml::{
    DefinitionBranchKind, DefinitionContext, DefinitionContextKind, Entity, EntityKind,
    GraphSchemaVersion, Parameter, ParameterKind, PresenceKind, Relationship, ResolutionKind,
    Signature, Target, TargetScope, Visibility, VisibilityBasis, VisibilityKind,
};
use crate::read::{count, fields, given, nonempty, present, repeats};
use crate::words::value_of;

/// `_array`.
fn array<'a>(raw: &'a Json, label: &str) -> Parsed<&'a [Json]> {
    match raw {
        Json::Array(items) => Ok(items),
        _ => Err(invalid(format!("{label} must be an array"))),
    }
}

/// `_array(item.get(key, ()))`: an absent key is empty, `null` is an error.
fn listed<'a>(item: &'a Object, key: &str) -> Parsed<&'a [Json]> {
    field(item, key).map_or(Ok(&[][..]), |raw| array(raw, key))
}

/// `_texts`: unique texts that are not empty; the array can be empty.
fn texts(raw: &Json, label: &str) -> Parsed<Vec<String>> {
    let values = array(raw, label)?
        .iter()
        .map(|value| nonempty(value, label))
        .collect::<Parsed<Vec<String>>>()?;
    if repeats(&values) {
        return Err(invalid(format!("{label} must be unique")));
    }
    Ok(values)
}

/// `_texts(item.get(key, ()))`.
fn listed_texts(item: &Object, key: &str, label: &str) -> Parsed<Vec<String>> {
    field(item, key).map_or(Ok(Vec::new()), |raw| texts(raw, label))
}

/// `_nullable(item.get(key))`.
fn nullable(item: &Object, key: &str, label: &str) -> Parsed<Option<String>> {
    given(item, key).map(|raw| nonempty(raw, label)).transpose()
}

/// A closed word: absent gives `default`; `null`, an empty text or an unknown word is an error.
fn word<T: DeserializeOwned>(
    item: &Object,
    key: &str,
    default: Option<T>,
    label: &str,
) -> Parsed<T> {
    let Some(raw) = field(item, key) else {
        return default.ok_or_else(|| invalid(format!("{label} is missing")));
    };
    let text: String = nonempty(raw, label)?;
    value_of(&text).ok_or_else(|| invalid(format!("{label} has an invalid vocabulary value")))
}

fn words<T: DeserializeOwned>(item: &Object, key: &str, label: &str) -> Parsed<Vec<T>> {
    listed_texts(item, key, label)?
        .iter()
        .map(|text| value_of(text).ok_or_else(|| invalid(format!("{label} has an invalid value"))))
        .collect()
}

fn boolean(item: &Object, key: &str, label: &str) -> Parsed<bool> {
    match field(item, key) {
        None => Ok(false),
        Some(Json::Bool(value)) => Ok(*value),
        Some(_) => Err(invalid(format!("{label} must be boolean"))),
    }
}

fn ids(values: Vec<String>) -> Vec<ItemId> {
    wrap_all(values)
}

fn visibility(item: &Object) -> Parsed<Visibility> {
    let Some(raw) = field(item, "visibility") else {
        return Ok(Visibility {
            kind: VisibilityKind::Unknown,
            basis: VisibilityBasis::Unknown,
            spelling: None,
        });
    };
    let fields = fields(raw, &[], &["kind", "basis", "spelling"], "visibility")?;
    Ok(Visibility {
        kind: word(
            fields,
            "kind",
            Some(VisibilityKind::Unknown),
            "visibility.kind",
        )?,
        basis: word(
            fields,
            "basis",
            Some(VisibilityBasis::Unknown),
            "visibility.basis",
        )?,
        spelling: nullable(fields, "spelling", "visibility.spelling")?,
    })
}

fn parameter(raw: &Json) -> Parsed<Parameter> {
    let item = fields(
        raw,
        &["name"],
        &["annotation", "kind", "default", "default_known"],
        "parameter",
    )?;
    let default = match given(item, "default") {
        None => None,
        Some(Json::Text(text)) => Some(text.clone()),
        Some(_) => return Err(invalid("parameter.default must be text or null")),
    };
    Ok(Parameter {
        name: nonempty(present(item, "name", "parameter")?, "parameter.name")?,
        annotation: nullable(item, "annotation", "parameter.annotation")?,
        kind: word(item, "kind", Some(ParameterKind::Unknown), "parameter.kind")?,
        default,
        default_known: boolean(item, "default_known", "parameter.default_known")?,
    })
}

fn signature(item: &Object) -> Parsed<Option<Signature>> {
    let Some(raw) = given(item, "signature") else {
        return Ok(None);
    };
    let fields = fields(raw, &[], &["parameters", "returns"], "signature")?;
    Ok(Some(Signature {
        parameters: listed(fields, "parameters")?
            .iter()
            .map(parameter)
            .collect::<Parsed<_>>()?,
        returns: nullable(fields, "returns", "signature.returns")?,
    }))
}

/// The branches that each definition context kind can have.
fn branch_allowed(kind: DefinitionContextKind, branch: DefinitionBranchKind) -> bool {
    use DefinitionBranchKind as B;
    use DefinitionContextKind as K;
    match kind {
        K::If | K::For | K::AsyncFor | K::While => matches!(branch, B::Body | B::Else),
        K::Try | K::TryStar => matches!(branch, B::Body | B::Else | B::Handler | B::Finally),
        K::With | K::AsyncWith => branch == B::Body,
        K::Match => branch == B::Case,
    }
}

fn definition_context(raw: &Json) -> Parsed<DefinitionContext> {
    let label = "definition context";
    let item = fields(raw, &["kind", "branch", "evidence_ids"], &[], label)?;
    let kind = word(item, "kind", None, "definition context.kind")?;
    let branch = word(item, "branch", None, "definition context.branch")?;
    let evidence = texts(
        present(item, "evidence_ids", label)?,
        "definition context.evidence_ids",
    )?;
    if !branch_allowed(kind, branch) {
        return Err(invalid("invalid definition context branch"));
    }
    Ok(DefinitionContext {
        kind,
        branch,
        evidence_ids: ids(evidence),
    })
}

const ENTITY_FIELDS: [&str; 13] = [
    "parent_id",
    "visibility",
    "signature",
    "annotation",
    "modifiers",
    "presence",
    "responsibilities",
    "evidence_ids",
    "provenance",
    "record_ids",
    "definition_contexts",
    "initializer",
    "file_path",
];

/// `parse_entity`.
pub(crate) fn entity(raw: &Json) -> Parsed<Entity> {
    let item = fields(
        raw,
        &["id", "kind", "qualified_name", "language"],
        &ENTITY_FIELDS,
        "entity",
    )?;
    let text_of = |key: &str| nonempty(present(item, key, "entity")?, &format!("entity.{key}"));
    Ok(Entity {
        id: ItemId(text_of("id")?),
        kind: word(item, "kind", None, "entity.kind")?,
        qualified_name: text_of("qualified_name")?,
        language: text_of("language")?,
        parent_id: nullable(item, "parent_id", "entity.parent_id")?.map(ItemId),
        visibility: visibility(item)?,
        signature: signature(item)?,
        annotation: nullable(item, "annotation", "entity.annotation")?,
        modifiers: words(item, "modifiers", "modifiers")?,
        presence: word(
            item,
            "presence",
            Some(PresenceKind::Unspecified),
            "entity.presence",
        )?,
        responsibilities: listed_texts(item, "responsibilities", "entity.responsibilities")?,
        evidence_ids: ids(listed_texts(item, "evidence_ids", "entity.evidence_ids")?),
        provenance: listed_texts(item, "provenance", "entity.provenance")?,
        record_ids: ids(listed_texts(item, "record_ids", "entity.record_ids")?),
        definition_contexts: listed(item, "definition_contexts")?
            .iter()
            .map(definition_context)
            .collect::<Parsed<_>>()?,
        initializer: nullable(item, "initializer", "entity.initializer")?,
        file_path: nullable(item, "file_path", "entity.file_path")?,
    })
}

const RELATIONSHIP_FIELDS: [&str; 12] = [
    "target_id",
    "resolution",
    "candidate_ids",
    "expression",
    "evidence_ids",
    "provenance",
    "record_ids",
    "candidate_count",
    "candidates_truncated",
    "reason",
    "through",
    "decided_by",
];

/// `parse_relationship`.
pub(crate) fn relationship(raw: &Json) -> Parsed<Relationship> {
    let label = "relationship";
    let item = fields(
        raw,
        &["id", "kind", "source_id"],
        &RELATIONSHIP_FIELDS,
        label,
    )?;
    let decided_by: Option<DecidedBy> = match given(item, "decided_by") {
        None => None,
        Some(_) => Some(word(item, "decided_by", None, "relationship.decided_by")?),
    };
    Ok(Relationship {
        id: ItemId(nonempty(present(item, "id", label)?, "relationship.id")?),
        kind: word(item, "kind", None, "relationship.kind")?,
        source_id: ItemId(nonempty(
            present(item, "source_id", label)?,
            "relationship.source_id",
        )?),
        target_id: nullable(item, "target_id", "relationship.target_id")?.map(ItemId),
        resolution: word(
            item,
            "resolution",
            Some(ResolutionKind::NotApplicable),
            "relationship.resolution",
        )?,
        candidate_ids: ids(listed_texts(
            item,
            "candidate_ids",
            "relationship.candidate_ids",
        )?),
        expression: nullable(item, "expression", "relationship.expression")?,
        evidence_ids: ids(listed_texts(
            item,
            "evidence_ids",
            "relationship.evidence_ids",
        )?),
        provenance: listed_texts(item, "provenance", "relationship.provenance")?,
        record_ids: ids(listed_texts(item, "record_ids", "relationship.record_ids")?),
        candidate_count: given(item, "candidate_count")
            .map(|raw| count(raw, "relationship.candidate_count"))
            .transpose()?,
        candidates_truncated: boolean(
            item,
            "candidates_truncated",
            "relationship.candidates_truncated",
        )?,
        reason: nullable(item, "reason", "relationship.reason")?,
        through: wrap_all(listed_texts(item, "through", "relationship.through")?),
        decided_by,
    })
}

fn scope(raw: &Json) -> Parsed<TargetScope> {
    let label = "target scope";
    let item = fields(
        raw,
        &["scope_id", "mode", "rationale", "provenance"],
        &["entity_kinds", "relationship_kinds"],
        label,
    )?;
    Ok(TargetScope {
        scope_id: ItemId(nonempty(present(item, "scope_id", label)?, "scope_id")?),
        mode: word(item, "mode", None, "mode")?,
        rationale: nonempty(present(item, "rationale", label)?, "rationale")?,
        provenance: texts(present(item, "provenance", label)?, "provenance")?,
        entity_kinds: words(item, "entity_kinds", "entity_kinds")?,
        relationship_kinds: words(item, "relationship_kinds", "relationship_kinds")?,
    })
}

/// `parse_target` and the version check of `TargetDefinition`.
pub(crate) fn target(raw: &Json) -> Parsed<Target> {
    let item = fields(
        raw,
        &["schema_version"],
        &["entities", "relationships", "scopes"],
        "uml",
    )?;
    let entities = listed(item, "entities")?
        .iter()
        .map(entity)
        .collect::<Parsed<Vec<_>>>()?;
    let relationships = listed(item, "relationships")?
        .iter()
        .map(relationship)
        .collect::<Parsed<Vec<_>>>()?;
    let scopes = listed(item, "scopes")?
        .iter()
        .map(scope)
        .collect::<Parsed<Vec<_>>>()?;
    let schema_version = word(item, "schema_version", None, "uml.schema_version")?;
    let literal = entities
        .iter()
        .any(|entity| entity.kind == EntityKind::EnumLiteral)
        || scopes
            .iter()
            .any(|scope| scope.entity_kinds.contains(&EntityKind::EnumLiteral));
    if schema_version == GraphSchemaVersion::V1_0 && literal {
        return Err(invalid("enum literal needs graph schema_version 1.1.0"));
    }
    Ok(Target {
        entities,
        relationships,
        scopes,
        schema_version,
    })
}

#[cfg(test)]
#[path = "uml_tests.rs"]
mod tests;
