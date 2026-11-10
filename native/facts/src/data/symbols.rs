// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the symbols section.

use crate::ids::{EvidenceId, FactId, ModuleName, PackageName};
use crate::nested::{
    AttributeDeclaration, BaseDeclaration, ContextmanagerSignature, DefinitionContext, Field,
    GenericBase, GuardBooleanMember, MemberInventory, Parameter, PropertyBinding, StoredFieldWrite,
    VisibilityDetail,
};
use crate::nullable::{Literal, Nullable};
use crate::vocab::{ClassKind, MethodKind, SymbolCategory, Visibility};

facts_data! {
    /// A class, an interface, an enum or a mixin declaration.
    pub struct ClassData {
        [read] attribute_declarations: Vec<AttributeDeclaration>,
        [read] base_declarations: Vec<BaseDeclaration>,
        [read skip] base_roots: Option<Vec<String>>,
        [read skip] bases: Option<Vec<String>>,
        [read skip] class_body_control_flow: Option<bool>,
        [read] class_header_static: bool,
        [read skip] class_kind: Option<ClassKind>,
        [read skip] class_members: Option<Vec<String>>,
        [read skip] declared_in_all: Option<bool>,
        [wire skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [read] decorators: Vec<String>,
        [read skip] default_instance_result: Option<bool>,
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        [read skip] enum_members: Option<Vec<String>>,
        [read skip] fields: Option<Vec<Field>>,
        [read skip] frozen_object: Option<bool>,
        [read skip] generic_bases: Option<Vec<GenericBase>>,
        [read skip] generic_parameters: Option<Vec<String>>,
        [read skip] guard_boolean_members: Option<Vec<GuardBooleanMember>>,
        [read skip] instance_member_scope_evidence_id: Nullable<EvidenceId>,
        [read skip] instance_member_writes: Option<Vec<String>>,
        [read required] lexical_parent_id: Option<FactId>,
        [read] member_inventories: Vec<MemberInventory>,
        [read skip] mixin_capable: Option<bool>,
        [wire skip] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [read skip] namespace_bound: Option<bool>,
        [wire skip] overload_signature: Option<bool>,
        [read] package: PackageName,
        [read required] parent: Option<String>,
        [read skip] property_members: Option<Vec<String>>,
        [read] qualified_name: String,
        [wire skip] signature_complete: Option<bool>,
        [read] source_binding_unique: bool,
        [read skip] source_class_header_static: Option<bool>,
        [wire skip] source_file: Option<String>,
        [read] source_member_binding_static: bool,
        [read skip] source_member_owner_static: Option<bool>,
        [read] symbol_category: SymbolCategory,
        [read skip] typed_dict_header_static: Option<bool>,
        [read skip] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A function or a method and its signature.
    pub struct CallableData {
        [read skip] accessor_kind: Option<String>,
        [read skip] annotation: Nullable<String>,
        [read skip "async"] is_async: Option<bool>,
        [wire skip] class_header_static: Option<bool>,
        [read skip] contextmanager_signature: Option<ContextmanagerSignature>,
        [read skip] declared_in_all: Option<bool>,
        [wire skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [read] decorators: Vec<String>,
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        [read required] lexical_parent_id: Option<FactId>,
        [read skip] method_kind: Option<MethodKind>,
        [read skip] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [read skip] namespace_bound: Option<bool>,
        [read] overload_signature: bool,
        [read skip] overloaded: Option<bool>,
        [read] package: PackageName,
        [read] parameters: Vec<Parameter>,
        [read skip] parameters_contained: Option<bool>,
        [read required] parent: Option<String>,
        [read skip] property_binding: Option<PropertyBinding>,
        [read] qualified_name: String,
        [read skip] receiver_parameter: Nullable<String>,
        [read required] returns: Option<String>,
        [read skip] shape: Option<String>,
        [read skip] shape_nodes: Option<i64>,
        [read skip] signature_complete: Option<bool>,
        [read skip] signature_decorators_proven: Option<bool>,
        [read skip] source_binding_static: Option<bool>,
        [read skip] source_binding_unique: Option<bool>,
        [wire skip] source_file: Option<String>,
        [read skip] source_final_method_binding: Option<bool>,
        [read skip] source_member_binding_static: Option<bool>,
        [read skip] stored_field_writes: Option<Vec<StoredFieldWrite>>,
        [read] symbol_category: SymbolCategory,
        [read skip] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A constant, a type alias or another named binding of a value.
    pub struct ValueData {
        [read skip] alias: Option<String>,
        [read skip] annotation: Nullable<String>,
        [read skip] class_header_static: Option<bool>,
        [read skip] constant: Nullable<Literal>,
        [read skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [read skip] decorators: Option<Vec<String>>,
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        [read skip] initializer: Nullable<String>,
        [read skip] lexical_parent_id: Nullable<FactId>,
        [read skip] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [read skip] overload_signature: Option<bool>,
        [read skip] package: Option<PackageName>,
        [read skip] parameters: Option<Vec<Parameter>>,
        [read required] parent: Option<String>,
        [read] qualified_name: String,
        [read skip] record_kind: Option<String>,
        [read skip] returns: Nullable<String>,
        [read skip] signature_complete: Option<bool>,
        [read] source_binding_unique: bool,
        [read skip] source_file: Option<String>,
        [read skip] source_member_binding_static: Option<bool>,
        [read skip] symbol_category: Option<SymbolCategory>,
        [read skip] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}
