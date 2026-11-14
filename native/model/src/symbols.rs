// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol table of a reply (AD-512): the modules, the symbols and their members as entities,
//! and the call, reference, base and construction sites as edges.
//!
//! Reference engine: `ir/source_graph.py` `_source_entities`, `_symbol`, `_attribute_entities`
//! and `_relationships` at release 4.0.1. The table names no language: the kinds are the entity
//! kinds of the contract. A record that 4.0.1 refuses (`ValueError`) makes the table broken, and
//! a broken table decides nothing (`Symbols::broken`).

use std::collections::HashMap;

use archkeel_contract::{EntityKind, ModifierKind, ParameterKind, RelationshipKind};
use archkeel_contract::{ResolutionKind, VisibilityBasis, VisibilityKind};
use archkeel_facts::data::{CallableData, ClassData, ValueData};
use archkeel_facts::nested::{DefinitionContext, Parameter, VisibilityDetail};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{ClassKind, MethodKind, Status, SymbolCategory};
use archkeel_facts::{FactData, Record, SymbolFact};

/// The visibility of an entity, as the record states it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Visibility {
    pub(crate) kind: VisibilityKind,
    pub(crate) basis: VisibilityBasis,
    pub(crate) spelling: Option<String>,
}

/// One parameter of an operation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Param {
    pub(crate) name: String,
    pub(crate) annotation: Option<String>,
    pub(crate) kind: ParameterKind,
    pub(crate) default: Option<String>,
    pub(crate) default_known: bool,
}

/// The recorded signature of an operation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Signature {
    pub(crate) parameters: Vec<Param>,
    pub(crate) returns: Option<String>,
}

/// One observed entity: a module, a symbol, a member, a binding or a referenced name.
#[derive(Clone, Debug)]
pub(crate) struct Entity {
    pub(crate) id: String,
    pub(crate) kind: EntityKind,
    pub(crate) name: String,
    /// The id of the lexical parent entity.
    pub(crate) parent: Option<String>,
    /// False for a name that a site refers to and no record defines.
    pub(crate) defined: bool,
    pub(crate) visibility: Visibility,
    pub(crate) signature: Option<Signature>,
    pub(crate) annotation: Option<String>,
    pub(crate) modifiers: Vec<ModifierKind>,
    /// The definition lies under control flow (`definition_contexts`).
    pub(crate) conditional: bool,
    pub(crate) initializer: Option<String>,
    pub(crate) evidence: Vec<String>,
}

/// One observed site: a directed edge between two entities.
#[derive(Clone, Debug)]
pub(crate) struct Edge {
    pub(crate) kind: RelationshipKind,
    pub(crate) source: String,
    /// The one target of a resolved site.
    pub(crate) target: Option<String>,
    pub(crate) resolution: ResolutionKind,
    pub(crate) evidence: Vec<String>,
}

/// The symbol table of one reply.
#[derive(Debug, Default)]
pub struct Symbols {
    pub(crate) entities: Vec<Entity>,
    pub(crate) edges: Vec<Edge>,
    /// The entities of each qualified name, in the order of the table.
    pub(crate) by_name: HashMap<String, Vec<usize>>,
    /// The entities that a site name resolves to (`by_name` of `_relationships`): each entity
    /// but the scope of a site without its declaration.
    pub(crate) lookup: HashMap<String, Vec<usize>>,
    pub(crate) by_id: HashMap<String, usize>,
    /// Each class and whether each of its bases is resolved (the base receipt of `_coverage`).
    pub(crate) bases: HashMap<String, bool>,
    /// Why 4.0.1 refuses these records, when it does.
    pub(crate) broken: Option<String>,
}

/// The id of the entity of a module.
pub(crate) fn module_id(name: &str) -> String {
    format!("module:{name}")
}

impl Symbols {
    /// Name a refusal of 4.0.1; the first one stays.
    pub(crate) fn refuse(&mut self, why: &str) {
        self.broken.get_or_insert_with(|| why.to_owned());
    }

    /// Add an entity to the table and to its name.
    pub(crate) fn push(&mut self, entity: Entity) {
        self.insert(entity, true);
    }

    /// Add an entity to the table; a site name resolves to it when `resolvable`.
    pub(crate) fn insert(&mut self, entity: Entity, resolvable: bool) {
        let index = self.entities.len();
        if resolvable {
            self.lookup
                .entry(entity.name.clone())
                .or_default()
                .push(index);
        }
        self.by_name
            .entry(entity.name.clone())
            .or_default()
            .push(index);
        self.by_id.insert(entity.id.clone(), index);
        self.entities.push(entity);
    }

    /// The ids of an entity and of each of its lexical parents (`_ancestors`).
    pub(crate) fn ancestors(&self, id: &str) -> Vec<String> {
        let mut result = Vec::new();
        let mut next = Some(id.to_owned());
        while let Some(current) = next {
            let Some(found) = self.get(&current) else {
                break;
            };
            if result.contains(&current) {
                break;
            }
            next = found.parent.clone();
            result.push(current);
        }
        result
    }

    /// The indexes of the entities that a site name `name` resolves to.
    pub(crate) fn resolving(&self, name: &str) -> Vec<usize> {
        self.lookup.get(name).cloned().unwrap_or_default()
    }

    /// The indexes of every entity named `name`.
    pub(crate) fn matching(&self, name: &str) -> Vec<usize> {
        self.by_name.get(name).cloned().unwrap_or_default()
    }

    /// The entity with the id `id`.
    pub(crate) fn get(&self, id: &str) -> Option<&Entity> {
        self.by_id.get(id).map(|index| &self.entities[*index])
    }

    /// The ids of the entities that a site name `name` resolves to.
    pub(crate) fn named(&self, name: &str) -> Vec<String> {
        self.lookup.get(name).map_or_else(Vec::new, |found| {
            found
                .iter()
                .map(|index| self.entities[*index].id.clone())
                .collect()
        })
    }

    /// The parent of a symbol without a lexical parent id: the one definition of its `parent`
    /// name, else its module.
    fn named_parent(
        &mut self,
        record: &Record<SymbolFact>,
        ids_of: &HashMap<&str, Vec<&str>>,
    ) -> Option<String> {
        let parents = parent_name(&record.data)
            .and_then(|name| ids_of.get(name))
            .map_or(&[][..], Vec::as_slice);
        if parents.len() > 1 {
            self.refuse("an ambiguous lexical parent has no definition id");
        }
        match parents.first() {
            Some(id) => Some((*id).to_owned()),
            None => record.data.fields().module.flatten().map(module_id),
        }
    }

    /// Add the entities of the symbol records.
    pub(crate) fn symbols(&mut self, records: &[Record<SymbolFact>]) {
        let mut ids_of: HashMap<&str, Vec<&str>> = HashMap::new();
        for record in records {
            if let Some(name) = record.data.fields().qualified_name {
                ids_of.entry(name).or_default().push(record.id.as_str());
            }
        }
        for record in records {
            let Some(mut entity) = symbol(record) else {
                self.refuse("a symbol record has no entity kind");
                continue;
            };
            let lexical = match &record.data {
                SymbolFact::Class(data) => data.lexical_parent_id.clone(),
                SymbolFact::Function(data) | SymbolFact::Method(data) => {
                    data.lexical_parent_id.clone()
                }
                _ => value(&record.data).and_then(|data| nullable(&data.lexical_parent_id)),
            };
            entity.parent = match lexical {
                Some(id) => Some(id.as_str().to_owned()),
                None => self.named_parent(record, &ids_of),
            };
            let members = match &record.data {
                SymbolFact::Class(data) => attributes(record, data, &entity),
                _ => Vec::new(),
            };
            self.push(entity);
            for member in members {
                self.push(member);
            }
        }
        // A module that the reply does not have is no parent (`module_ids.get`).
        for index in 0..self.entities.len() {
            let parent = self.entities[index].parent.clone();
            if parent.is_some_and(|id| id.starts_with("module:") && !self.by_id.contains_key(&id)) {
                self.entities[index].parent = None;
            }
        }
    }
}

impl Entity {
    /// A defined entity without metadata.
    pub(crate) fn named(id: String, kind: EntityKind, name: &str, evidence: Vec<String>) -> Self {
        Entity {
            id,
            kind,
            name: name.to_owned(),
            parent: None,
            defined: true,
            visibility: visibility(None, None),
            signature: None,
            annotation: None,
            modifiers: Vec::new(),
            conditional: false,
            initializer: None,
            evidence,
        }
    }
}

/// A closed contract value of a recorded word, or `None` for a word outside it.
pub(crate) fn parse<T: serde::de::DeserializeOwned>(word: &str) -> Option<T> {
    serde_json::from_value(serde_json::Value::String(word.to_owned())).ok()
}

pub(crate) fn nullable<T: Clone>(value: &Nullable<T>) -> Option<T> {
    match value {
        Nullable::Value(value) => Some(value.clone()),
        Nullable::Absent | Nullable::Null => None,
    }
}

/// `_visibility`: an unknown word is an unknown visibility, which decides nothing.
pub(crate) fn visibility(detail: Option<&VisibilityDetail>, spelling: Option<&str>) -> Visibility {
    match detail {
        None => Visibility {
            kind: VisibilityKind::Unknown,
            basis: VisibilityBasis::Unknown,
            spelling: spelling.map(str::to_owned),
        },
        Some(detail) => Visibility {
            kind: parse(&detail.kind).unwrap_or(VisibilityKind::Unknown),
            basis: parse(&detail.basis).unwrap_or(VisibilityBasis::Unknown),
            spelling: Some(detail.spelling.clone()),
        },
    }
}

pub(crate) fn evidence(ids: &[archkeel_facts::ids::EvidenceId]) -> Vec<String> {
    ids.iter().map(|id| id.as_str().to_owned()).collect()
}

/// The qualified name of the lexical parent that a record names.
fn parent_name(data: &SymbolFact) -> Option<&str> {
    match data {
        SymbolFact::Class(data) => data.parent.as_deref(),
        SymbolFact::Function(data) | SymbolFact::Method(data) => data.parent.as_deref(),
        other => value(other).and_then(|data| data.parent.as_deref()),
    }
}

fn value(data: &SymbolFact) -> Option<&ValueData> {
    match data {
        SymbolFact::Constant(data)
        | SymbolFact::TypeAlias(data)
        | SymbolFact::Binding(data)
        | SymbolFact::Alias(data)
        | SymbolFact::DynamicBinding(data)
        | SymbolFact::StaticConstant(data)
        | SymbolFact::Macro(data) => Some(data),
        SymbolFact::Class(_) | SymbolFact::Function(_) | SymbolFact::Method(_) => None,
    }
}

/// `_symbol`: the entity kind of a record, or `None` when 4.0.1 has no kind for it.
fn kind(record: &Record<SymbolFact>) -> Option<EntityKind> {
    let category = match &record.data {
        SymbolFact::Class(data) => Some(data.symbol_category),
        SymbolFact::Function(data) | SymbolFact::Method(data) => Some(data.symbol_category),
        other => value(other).and_then(|data| data.symbol_category),
    };
    let kind = match category {
        // The 4.0.1 graph has no macro kind.
        Some(SymbolCategory::Macro) => return None,
        Some(SymbolCategory::Class) => EntityKind::Class,
        Some(SymbolCategory::Constant) => EntityKind::Constant,
        Some(SymbolCategory::DynamicBinding) => EntityKind::Binding,
        Some(SymbolCategory::Function) => EntityKind::Function,
        Some(SymbolCategory::Method) => EntityKind::Method,
        Some(SymbolCategory::TypeAlias) => EntityKind::TypeAlias,
        None => match &record.data {
            SymbolFact::StaticConstant(_) => EntityKind::Constant,
            SymbolFact::DynamicBinding(_) => EntityKind::Binding,
            SymbolFact::Macro(_) => return None,
            other => parse(other.kind().as_str())?,
        },
    };
    let class_kind = match &record.data {
        SymbolFact::Class(data) => data.class_kind,
        _ => None,
    };
    Some(match (kind, class_kind) {
        (EntityKind::Class, Some(ClassKind::Protocol)) => EntityKind::Interface,
        (EntityKind::Class, Some(ClassKind::Enum)) => EntityKind::Enum,
        _ => kind,
    })
}

fn symbol(record: &Record<SymbolFact>) -> Option<Entity> {
    let kind = kind(record)?;
    let fields = record.data.fields();
    let mut entity = Entity::named(
        record.id.as_str().to_owned(),
        kind,
        fields.qualified_name.unwrap_or_default(),
        evidence(&record.evidence_ids),
    );
    let (detail, contexts) = match &record.data {
        SymbolFact::Class(data) => class(&mut entity, data),
        SymbolFact::Function(data) | SymbolFact::Method(data) => callable(&mut entity, data),
        other => {
            let data = value(other)?;
            entity.annotation = nullable(&data.annotation);
            if kind == EntityKind::Binding {
                entity.initializer = nullable(&data.initializer);
            }
            (&data.visibility_detail, data.definition_contexts.as_ref())
        }
    };
    entity.visibility = visibility(Some(detail), None);
    entity.conditional = contexts.is_some_and(|found| !found.is_empty());
    Some(entity)
}

type Detail<'d> = (&'d VisibilityDetail, Option<&'d Vec<DefinitionContext>>);

fn class<'d>(entity: &mut Entity, data: &'d ClassData) -> Detail<'d> {
    if data.mixin_capable == Some(true) {
        entity.modifiers.push(ModifierKind::Mixin);
    }
    if data.frozen_object == Some(true) {
        entity.modifiers.push(ModifierKind::Frozen);
    }
    (&data.visibility_detail, data.definition_contexts.as_ref())
}

fn callable<'d>(entity: &mut Entity, data: &'d CallableData) -> Detail<'d> {
    if data.is_async == Some(true) {
        entity.modifiers.push(ModifierKind::Async);
    }
    match data.method_kind {
        Some(MethodKind::Static) => entity.modifiers.push(ModifierKind::Static),
        Some(MethodKind::Class) => entity.modifiers.push(ModifierKind::Class),
        _ => {}
    }
    entity.annotation = nullable(&data.annotation);
    if data.signature_complete != Some(false) {
        entity.signature = Some(Signature {
            parameters: data.parameters.iter().map(param).collect(),
            returns: data.returns.clone(),
        });
    }
    (&data.visibility_detail, data.definition_contexts.as_ref())
}

fn param(item: &Parameter) -> Param {
    let kind = parse(&item.kind).unwrap_or(ParameterKind::Unknown);
    let starred = matches!(kind, ParameterKind::Varargs | ParameterKind::Kwargs);
    Param {
        name: if starred {
            item.name.trim_start_matches('*').to_owned()
        } else {
            item.name.clone()
        },
        annotation: item.annotation.clone(),
        kind,
        default: item.default.clone(),
        default_known: item.default_known,
    }
}

/// `_attribute_entities`: the declared attributes of a class; a name of `enum_members` of an
/// enum is an enum literal.
fn attributes(record: &Record<SymbolFact>, data: &ClassData, owner: &Entity) -> Vec<Entity> {
    let literals: &[String] = match (owner.kind, &data.enum_members) {
        (EntityKind::Enum, Some(members)) => members,
        _ => &[],
    };
    data.attribute_declarations
        .iter()
        .map(|field| {
            let literal = literals.contains(&field.name);
            let mut found = evidence(&field.evidence_ids);
            if found.is_empty() {
                found = evidence(&record.evidence_ids);
            }
            let kind = if literal {
                EntityKind::EnumLiteral
            } else {
                EntityKind::Attribute
            };
            let name = format!("{}.{}", owner.name, field.name);
            let mut member =
                Entity::named(field.definition_id.as_str().to_owned(), kind, &name, found);
            member.parent = Some(owner.id.clone());
            member.visibility = visibility(Some(&field.visibility), None);
            member.annotation = field.annotation.clone();
            if field.is_static == Some(true) && !literal {
                member.modifiers.push(ModifierKind::Static);
            }
            member.conditional = owner.conditional;
            member
        })
        .collect()
}

/// The resolution of a recorded status, or `None` when 4.0.1 has none for it.
pub(crate) fn resolution(status: Status) -> Option<ResolutionKind> {
    match status {
        Status::Resolved => Some(ResolutionKind::Resolved),
        Status::PartiallyResolved => Some(ResolutionKind::Partial),
        Status::Unresolved => Some(ResolutionKind::Unresolved),
        Status::Unknown | Status::Decided => None,
    }
}
