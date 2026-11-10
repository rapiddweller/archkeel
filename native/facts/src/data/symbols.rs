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
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] base_roots: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] bases: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] class_body_control_flow: Option<bool>,
        [wire] class_header_static: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] class_kind: Option<ClassKind>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] class_members: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] declared_in_all: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [wire] decorators: Vec<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] default_instance_result: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] definition_contexts: Option<Vec<DefinitionContext>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] enum_members: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] fields: Option<Vec<Field>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] frozen_object: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] generic_bases: Option<Vec<GenericBase>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] generic_parameters: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] guard_boolean_members: Option<Vec<GuardBooleanMember>>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] instance_member_scope_evidence_id: Nullable<EvidenceId>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] instance_member_writes: Option<Vec<String>>,
        [read] lexical_parent_id: Option<FactId>,
        [read] member_inventories: Vec<MemberInventory>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] mixin_capable: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] namespace_bound: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] overload_signature: Option<bool>,
        [wire] package: PackageName,
        [read] parent: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] property_members: Option<Vec<String>>,
        [read] qualified_name: String,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] signature_complete: Option<bool>,
        [wire] source_binding_unique: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_class_header_static: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] source_file: Option<String>,
        [wire] source_member_binding_static: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_member_owner_static: Option<bool>,
        [read] symbol_category: SymbolCategory,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] typed_dict_header_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A function or a method and its signature.
    pub struct CallableData {
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] accessor_kind: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] annotation: Nullable<String>,
        [optional "async"] #[serde(rename = "async", default, skip_serializing_if = "Option::is_none")] is_async: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] class_header_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] contextmanager_signature: Option<ContextmanagerSignature>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] declared_in_all: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [wire] decorators: Vec<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] definition_contexts: Option<Vec<DefinitionContext>>,
        [read] lexical_parent_id: Option<FactId>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] method_kind: Option<MethodKind>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] namespace_bound: Option<bool>,
        [wire] overload_signature: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] overloaded: Option<bool>,
        [wire] package: PackageName,
        [read] parameters: Vec<Parameter>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] parameters_contained: Option<bool>,
        [read] parent: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] property_binding: Option<PropertyBinding>,
        [read] qualified_name: String,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] receiver_parameter: Nullable<String>,
        [read] returns: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] shape: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] shape_nodes: Option<i64>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] signature_complete: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] signature_decorators_proven: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_binding_static: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] source_binding_unique: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] source_file: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_final_method_binding: Option<bool>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] source_member_binding_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] stored_field_writes: Option<Vec<StoredFieldWrite>>,
        [read] symbol_category: SymbolCategory,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A constant, a type alias or another named binding of a value.
    pub struct ValueData {
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] alias: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] annotation: Nullable<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] class_header_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] constant: Nullable<Literal>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] decorators: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] definition_contexts: Option<Vec<DefinitionContext>>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] initializer: Nullable<String>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] lexical_parent_id: Nullable<FactId>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] modifiers: Option<Vec<String>>,
        [read] module: ModuleName,
        [read] name: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] overload_signature: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] package: Option<PackageName>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] parameters: Option<Vec<Parameter>>,
        [read] parent: Option<String>,
        [read] qualified_name: String,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] record_kind: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] returns: Nullable<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] signature_complete: Option<bool>,
        [read] source_binding_unique: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_file: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_member_binding_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] symbol_category: Option<SymbolCategory>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] visibility: Option<Visibility>,
        [read] visibility_detail: VisibilityDetail,
    }
}
