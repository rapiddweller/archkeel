// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of a symbol record: the fields of `_symbol_metadata` that every definition has, the data
//! type that each kind of definition adds them to (`ClassData`, `CallableData`, `ValueData`), and
//! what a class, an interface and an enum add (`_classifier_data`, `_attribute_declaration`,
//! `_base_record`).

use std::collections::HashMap;

use archkeel_facts::data::{CallableData, ClassData, ValueData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nested::{
    AttributeDeclaration, BaseDeclaration, MemberInventory, Parameter, VisibilityDetail,
};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{
    ClassKind, InventoryStatus, MemberKind, MethodKind, RelationshipKind, Status, SymbolCategory,
};

use crate::cited::Cited;
use crate::definitions::DefinitionKind;
use crate::members::{self, Base, Member, Visibility};
use crate::source::Span;
use crate::symbol_table::{Entry, SymbolTable};

/// The fields that every definition has.
pub(crate) struct Core {
    pub qualified_name: String,
    pub module: ModuleName,
    pub package: PackageName,
    pub name: String,
    pub parent: Option<String>,
    pub lexical_parent_id: Option<FactId>,
    pub visibility_detail: VisibilityDetail,
    pub symbol_category: SymbolCategory,
    pub source_binding_unique: bool,
    pub decorators: Vec<String>,
    pub decorator_evidence_ids: Vec<EvidenceId>,
    pub signature_complete: bool,
    pub overload_signature: bool,
}

/// What a class, an interface and an enum add (`_classifier_data`).
pub(crate) struct Classifier {
    pub class_kind: Option<ClassKind>,
    pub enum_members: Option<Vec<String>>,
    pub member_inventories: Vec<MemberInventory>,
    pub base_declarations: Vec<BaseDeclaration>,
    pub attribute_declarations: Vec<AttributeDeclaration>,
}

fn parameter(item: &members::Parameter) -> Parameter {
    Parameter {
        annotation: item.annotation.clone(),
        default: item.default.clone(),
        default_known: item.default.is_none() && !item.optional,
        kind: if item.rest { "varargs" } else { "positional" }.to_owned(),
        name: item.name.clone(),
    }
}

fn parameters(entry: &Entry) -> Vec<Parameter> {
    entry.definition.parameters.iter().map(parameter).collect()
}

fn nullable(value: &Option<String>) -> Nullable<String> {
    value.clone().map_or(Nullable::Null, Nullable::Value)
}

pub(crate) fn class_data(core: Core, more: Classifier) -> ClassData {
    ClassData {
        attribute_declarations: more.attribute_declarations,
        base_declarations: more.base_declarations,
        base_roots: None,
        bases: None,
        class_body_control_flow: None,
        class_header_static: true,
        class_kind: more.class_kind,
        class_members: None,
        declared_in_all: None,
        decorator_evidence_ids: Some(core.decorator_evidence_ids),
        decorators: core.decorators,
        default_instance_result: None,
        definition_contexts: None,
        enum_members: more.enum_members,
        fields: None,
        frozen_object: None,
        generic_bases: None,
        generic_parameters: None,
        guard_boolean_members: None,
        instance_member_scope_evidence_id: Nullable::Absent,
        instance_member_writes: None,
        lexical_parent_id: core.lexical_parent_id,
        member_inventories: more.member_inventories,
        mixin_capable: None,
        modifiers: None,
        module: core.module,
        name: core.name,
        namespace_bound: None,
        overload_signature: Some(core.overload_signature),
        package: core.package,
        parent: core.parent,
        property_members: None,
        qualified_name: core.qualified_name,
        signature_complete: Some(core.signature_complete),
        source_binding_unique: core.source_binding_unique,
        source_class_header_static: None,
        source_file: None,
        source_member_binding_static: true,
        source_member_owner_static: None,
        symbol_category: core.symbol_category,
        typed_dict_header_static: None,
        visibility: None,
        visibility_detail: core.visibility_detail,
    }
}

/// The data of a function or a method: `async` and `method_kind` only when they are true.
pub(crate) fn callable_data(core: Core, entry: &Entry) -> CallableData {
    let definition = entry.definition;
    let method_kind = match (definition.kind, definition.is_static) {
        (DefinitionKind::Method, true) => Some(MethodKind::Static),
        (DefinitionKind::Method, false) => Some(MethodKind::Instance),
        _ => None,
    };
    CallableData {
        accessor_kind: None,
        annotation: nullable(&definition.annotation),
        is_async: definition.is_async.then_some(true),
        class_header_static: Some(true),
        contextmanager_signature: None,
        declared_in_all: None,
        decorator_evidence_ids: Some(core.decorator_evidence_ids),
        decorators: core.decorators,
        definition_contexts: None,
        lexical_parent_id: core.lexical_parent_id,
        method_kind,
        modifiers: None,
        module: core.module,
        name: core.name,
        namespace_bound: None,
        overload_signature: core.overload_signature,
        overloaded: None,
        package: core.package,
        parameters: parameters(entry),
        parameters_contained: None,
        parent: core.parent,
        property_binding: None,
        qualified_name: core.qualified_name,
        receiver_parameter: Nullable::Absent,
        returns: definition.returns.clone(),
        shape: None,
        shape_nodes: None,
        signature_complete: Some(core.signature_complete),
        signature_decorators_proven: Some(definition.decorator_sources.is_empty()),
        source_binding_static: None,
        source_binding_unique: Some(core.source_binding_unique),
        source_file: None,
        source_final_method_binding: None,
        source_member_binding_static: Some(true),
        stored_field_writes: None,
        symbol_category: core.symbol_category,
        visibility: None,
        visibility_detail: core.visibility_detail,
    }
}

/// The data of a constant or a type alias.
pub(crate) fn value_data(core: Core, entry: &Entry) -> ValueData {
    let definition = entry.definition;
    ValueData {
        alias: None,
        annotation: nullable(&definition.annotation),
        class_header_static: Some(true),
        constant: Nullable::Absent,
        decorator_evidence_ids: Some(core.decorator_evidence_ids),
        decorators: Some(core.decorators),
        definition_contexts: None,
        initializer: Nullable::Absent,
        lexical_parent_id: core
            .lexical_parent_id
            .map_or(Nullable::Null, Nullable::Value),
        modifiers: None,
        module: core.module,
        name: core.name,
        overload_signature: Some(core.overload_signature),
        package: Some(core.package),
        parameters: Some(parameters(entry)),
        parent: core.parent,
        qualified_name: core.qualified_name,
        record_kind: None,
        returns: nullable(&definition.returns),
        signature_complete: Some(core.signature_complete),
        source_binding_unique: core.source_binding_unique,
        source_file: None,
        source_member_binding_static: Some(true),
        symbol_category: Some(core.symbol_category),
        visibility: None,
        visibility_detail: core.visibility_detail,
    }
}

/// `_classifier_data`.
pub(crate) fn classifier(
    table: &SymbolTable,
    methods: &Methods,
    cited: &mut Cited,
    entry: &Entry,
) -> Classifier {
    let definition = entry.definition;
    let class_kind = match definition.kind {
        DefinitionKind::Interface => Some(ClassKind::Protocol),
        DefinitionKind::Enum => Some(ClassKind::Enum),
        _ => None,
    };
    let attributes: Vec<AttributeDeclaration> = definition
        .members
        .iter()
        .map(|member| attribute(cited, entry, member))
        .collect();
    let attribute_ids: Vec<FactId> = attributes
        .iter()
        .map(|item| item.definition_id.clone())
        .collect();
    let enum_members = (definition.kind == DefinitionKind::Enum).then(|| {
        definition
            .members
            .iter()
            .map(|member| member.name.clone())
            .collect()
    });
    let within = match entry.parent {
        Some(parent) => format!("{parent}.{}", definition.name),
        None => definition.name.clone(),
    };
    let key = (
        entry.module.to_owned(),
        within,
        definition.span.line,
        definition.span.column,
    );
    let method_ids: Vec<FactId> = methods
        .get(&key)
        .map(|ids| ids.iter().map(FactId::new).collect())
        .unwrap_or_default();
    let complete = definition.members_complete && table.count(&entry.qualified) == 1;
    let inventory = |kind: MemberKind, definition_ids: Vec<FactId>| MemberInventory {
        definition_ids,
        kind,
        reason: (!complete).then(|| "computed or unsupported member syntax".to_owned()),
        schema_version: "1.0.0".to_owned(),
        status: if complete {
            InventoryStatus::Complete
        } else {
            InventoryStatus::Partial
        },
    };
    let member_inventories = vec![
        inventory(MemberKind::Attribute, attribute_ids),
        inventory(MemberKind::Method, method_ids),
    ];
    let base_declarations = definition
        .bases
        .iter()
        .map(|base| base_record(table, cited, entry, base))
        .collect();
    Classifier {
        class_kind,
        enum_members,
        member_inventories,
        base_declarations,
        attribute_declarations: attributes,
    }
}

/// `_attribute_declaration`.
fn attribute(cited: &mut Cited, entry: &Entry, member: &Member) -> AttributeDeclaration {
    let kind = member.visibility.unwrap_or(Visibility::Public).as_str();
    let id = stable_id(
        "TSATTR",
        &[
            Part::Text(entry.rel),
            Part::Number(member.span.line),
            Part::Number(member.span.column),
            Part::Text(&entry.qualified),
            Part::Text(&member.name),
        ],
    );
    let evidence = cited.cite(entry.rel, &member.span);
    let (names, spans) = decorators(cited, entry.rel, &member.decorator_sources);
    AttributeDeclaration {
        annotation: member.annotation.clone(),
        constant: archkeel_facts::nullable::Nullable::Absent,
        decorator_evidence_ids: Some(spans),
        decorators: Some(names),
        definition_id: FactId::new(id),
        evidence_ids: vec![EvidenceId::new(evidence)],
        literal_value: None,
        name: member.name.clone(),
        is_static: Some(member.is_static),
        visibility: VisibilityDetail {
            basis: "language".to_owned(),
            kind: kind.to_owned(),
            spelling: member.name.clone(),
        },
    }
}

/// `_base_record`.
fn base_record(
    table: &SymbolTable,
    cited: &mut Cited,
    entry: &Entry,
    base: &Base,
) -> BaseDeclaration {
    let qualified = format!("{}.{}", entry.module, base.name);
    let candidates = table.classifier_count(&qualified);
    let evidence = cited.cite(entry.rel, &base.span);
    let (status, reason) = match candidates {
        1 => (Status::Resolved, None),
        0 => (
            Status::Unresolved,
            Some("Base is not a unique local classifier"),
        ),
        _ => (
            Status::PartiallyResolved,
            Some("multiple classifier definition sites share the target name"),
        ),
    };
    let targets = if candidates > 0 {
        vec![qualified]
    } else {
        Vec::new()
    };
    let id = stable_id(
        "TSBASE",
        &[
            Part::Text(&entry.qualified),
            Part::Number(base.span.line),
            Part::Number(base.span.column),
            Part::Text(&base.name),
        ],
    );
    BaseDeclaration {
        candidate_count: i64::try_from(candidates).unwrap_or(i64::MAX),
        candidates_truncated: Some(false),
        evidence_ids: vec![EvidenceId::new(evidence)],
        expression: base.name.clone(),
        id: FactId::new(id),
        reason: reason.map(str::to_owned),
        relationship_kind: if base.realizes {
            RelationshipKind::Realizes
        } else {
            RelationshipKind::Inherits
        },
        status,
        targets,
    }
}

/// The methods of each class, by the module, the name that the methods give as their parent and
/// the position of the class: Python scans all definitions for each class.
pub(crate) type Methods = HashMap<(String, String, i64, i64), Vec<String>>;

/// The names and the evidence of the decorators of a definition or a member.
pub(crate) fn decorators(
    cited: &mut Cited,
    rel: &str,
    sources: &[(String, Span)],
) -> (Vec<String>, Vec<EvidenceId>) {
    let names = sources.iter().map(|(name, _)| name.clone()).collect();
    let evidence = sources
        .iter()
        .map(|(_, span)| EvidenceId::new(cited.cite(rel, span)))
        .collect();
    (names, evidence)
}
