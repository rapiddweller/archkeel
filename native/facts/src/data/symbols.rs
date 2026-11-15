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

/// A class, an interface, an enum or a mixin declaration.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClassData {
    pub attribute_declarations: Vec<AttributeDeclaration>,
    pub base_declarations: Vec<BaseDeclaration>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub base_roots: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub bases: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub class_body_control_flow: Option<bool>,
    pub class_header_static: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub class_kind: Option<ClassKind>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub class_members: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declared_in_all: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub decorator_evidence_ids: Option<Vec<EvidenceId>>,
    pub decorators: Vec<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub default_instance_result: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub definition_contexts: Option<Vec<DefinitionContext>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub enum_members: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub fields: Option<Vec<Field>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub frozen_object: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub generic_bases: Option<Vec<GenericBase>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub generic_parameters: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub guard_boolean_members: Option<Vec<GuardBooleanMember>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub instance_member_scope_evidence_id: Nullable<EvidenceId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub instance_member_writes: Option<Vec<String>>,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub lexical_parent_id: Option<FactId>,
    pub member_inventories: Vec<MemberInventory>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub mixin_capable: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub modifiers: Option<Vec<String>>,
    pub module: ModuleName,
    pub name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub namespace_bound: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub overload_signature: Option<bool>,
    pub package: PackageName,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub parent: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub property_members: Option<Vec<String>>,
    pub qualified_name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub signature_complete: Option<bool>,
    pub source_binding_unique: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_class_header_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_file: Option<String>,
    pub source_member_binding_static: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_member_owner_static: Option<bool>,
    pub symbol_category: SymbolCategory,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub typed_dict_header_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub visibility: Option<Visibility>,
    pub visibility_detail: VisibilityDetail,
}

/// A function or a method and its signature.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallableData {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub accessor_kind: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub annotation: Nullable<String>,
    #[serde(
        rename = "async",
        default,
        skip_serializing_if = "crate::skip::omitted"
    )]
    pub is_async: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub class_header_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub contextmanager_signature: Option<ContextmanagerSignature>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub declared_in_all: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub decorator_evidence_ids: Option<Vec<EvidenceId>>,
    pub decorators: Vec<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub definition_contexts: Option<Vec<DefinitionContext>>,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub lexical_parent_id: Option<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub method_kind: Option<MethodKind>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub modifiers: Option<Vec<String>>,
    pub module: ModuleName,
    pub name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub namespace_bound: Option<bool>,
    pub overload_signature: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub overloaded: Option<bool>,
    pub package: PackageName,
    pub parameters: Vec<Parameter>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub parameters_contained: Option<bool>,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub parent: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub property_binding: Option<PropertyBinding>,
    pub qualified_name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub receiver_parameter: Nullable<String>,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub returns: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub shape: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub shape_nodes: Option<i64>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub signature_complete: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub signature_decorators_proven: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_binding_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_binding_unique: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_file: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_final_method_binding: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_member_binding_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub stored_field_writes: Option<Vec<StoredFieldWrite>>,
    pub symbol_category: SymbolCategory,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub visibility: Option<Visibility>,
    pub visibility_detail: VisibilityDetail,
}

/// A constant, a type alias or another named binding of a value.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ValueData {
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub alias: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub annotation: Nullable<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub class_header_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub constant: Nullable<Literal>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub decorator_evidence_ids: Option<Vec<EvidenceId>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub decorators: Option<Vec<String>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub definition_contexts: Option<Vec<DefinitionContext>>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub initializer: Nullable<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub lexical_parent_id: Nullable<FactId>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub modifiers: Option<Vec<String>>,
    pub module: ModuleName,
    pub name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub overload_signature: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub package: Option<PackageName>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub parameters: Option<Vec<Parameter>>,
    #[serde(deserialize_with = "crate::nullable::required")]
    #[schemars(required)]
    pub parent: Option<String>,
    pub qualified_name: String,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub record_kind: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub returns: Nullable<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub signature_complete: Option<bool>,
    pub source_binding_unique: bool,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_file: Option<String>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub source_member_binding_static: Option<bool>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub symbol_category: Option<SymbolCategory>,
    #[serde(default, skip_serializing_if = "crate::skip::omitted")]
    pub visibility: Option<Visibility>,
    pub visibility_detail: VisibilityDetail,
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
