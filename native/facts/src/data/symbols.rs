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

/// The fields that each declaration shares: where it is, what it is called and how visible it is.
/// A producer that reads declarations without types (Rust) builds its data from this header.
#[derive(Clone, Debug)]
pub struct Declared {
    pub module: ModuleName,
    pub package: PackageName,
    pub name: String,
    pub qualified_name: String,
    /// The qualified name of the type or trait that holds the declaration.
    pub parent: Option<String>,
    pub lexical_parent_id: Option<FactId>,
    /// No other declaration of the file has the same qualified name.
    pub unique: bool,
    pub visibility: VisibilityDetail,
}

impl ClassData {
    /// A class-like declaration. The members and the bases are not read, so the lists are empty.
    pub fn declared(header: Declared, class_kind: ClassKind) -> Self {
        ClassData {
            attribute_declarations: Vec::new(),
            base_declarations: Vec::new(),
            base_roots: None,
            bases: None,
            class_body_control_flow: None,
            class_header_static: true,
            class_kind: Some(class_kind),
            class_members: None,
            declared_in_all: None,
            decorator_evidence_ids: None,
            decorators: Vec::new(),
            default_instance_result: None,
            definition_contexts: None,
            enum_members: None,
            fields: None,
            frozen_object: None,
            generic_bases: None,
            generic_parameters: None,
            guard_boolean_members: None,
            instance_member_scope_evidence_id: Nullable::Absent,
            instance_member_writes: None,
            lexical_parent_id: header.lexical_parent_id,
            member_inventories: Vec::new(),
            mixin_capable: None,
            modifiers: None,
            module: header.module,
            name: header.name,
            namespace_bound: None,
            overload_signature: None,
            package: header.package,
            parent: header.parent,
            property_members: None,
            qualified_name: header.qualified_name,
            signature_complete: None,
            source_binding_unique: header.unique,
            source_class_header_static: None,
            source_file: None,
            source_member_binding_static: true,
            source_member_owner_static: None,
            symbol_category: SymbolCategory::Class,
            typed_dict_header_static: None,
            visibility: None,
            visibility_detail: header.visibility,
        }
    }
}

impl CallableData {
    /// A function or a method whose parameters are not read: `signature_complete` is false.
    pub fn declared(header: Declared, method_kind: Option<MethodKind>) -> Self {
        let method = method_kind.is_some();
        CallableData {
            accessor_kind: None,
            annotation: Nullable::Absent,
            is_async: None,
            class_header_static: None,
            contextmanager_signature: None,
            declared_in_all: None,
            decorator_evidence_ids: None,
            decorators: Vec::new(),
            definition_contexts: None,
            lexical_parent_id: header.lexical_parent_id,
            method_kind,
            modifiers: None,
            module: header.module,
            name: header.name,
            namespace_bound: None,
            overload_signature: false,
            overloaded: None,
            package: header.package,
            parameters: Vec::new(),
            parameters_contained: None,
            parent: header.parent,
            property_binding: None,
            qualified_name: header.qualified_name,
            receiver_parameter: Nullable::Absent,
            returns: None,
            shape: None,
            shape_nodes: None,
            signature_complete: Some(false),
            signature_decorators_proven: None,
            source_binding_static: None,
            source_binding_unique: Some(header.unique),
            source_file: None,
            source_final_method_binding: None,
            source_member_binding_static: method.then_some(true),
            stored_field_writes: None,
            symbol_category: if method {
                SymbolCategory::Method
            } else {
                SymbolCategory::Function
            },
            visibility: None,
            visibility_detail: header.visibility,
        }
    }
}

impl ValueData {
    /// A constant, a static, a type alias or a macro. `category` is `None` for a static, which
    /// the host reads from the kind.
    pub fn declared(header: Declared, category: Option<SymbolCategory>) -> Self {
        ValueData {
            alias: None,
            annotation: Nullable::Absent,
            class_header_static: None,
            constant: Nullable::Absent,
            decorator_evidence_ids: None,
            decorators: None,
            definition_contexts: None,
            initializer: Nullable::Absent,
            lexical_parent_id: header
                .lexical_parent_id
                .map_or(Nullable::Null, Nullable::Value),
            modifiers: None,
            module: header.module,
            name: header.name,
            overload_signature: None,
            package: Some(header.package),
            parameters: None,
            parent: header.parent,
            qualified_name: header.qualified_name,
            record_kind: None,
            returns: Nullable::Absent,
            signature_complete: None,
            source_binding_unique: header.unique,
            source_file: None,
            source_member_binding_static: None,
            symbol_category: category,
            visibility: None,
            visibility_detail: header.visibility,
        }
    }
}
