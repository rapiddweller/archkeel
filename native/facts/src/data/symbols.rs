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
use crate::type_shape::TypeShape;
use crate::vocab::{ClassKind, MethodKind, SymbolCategory, Visibility};

facts_data! {
    /// A class, an interface, an enum or a mixin declaration.
    pub struct ClassData {
        /// The attributes that the class declares.
        [read] attribute_declarations: Vec<AttributeDeclaration>,
        /// The bases that the class names.
        [read] base_declarations: Vec<BaseDeclaration>,
        /// The root names of the bases.
        [read skip] base_roots: Option<Vec<String>>,
        /// The bases as written.
        [read skip] bases: Option<Vec<String>>,
        /// True when the body of the class has control flow.
        [read skip] class_body_control_flow: Option<bool>,
        /// True when the header of the class is read in full.
        [read] class_header_static: bool,
        /// The kind of the class.
        [read skip] class_kind: Option<ClassKind>,
        /// The names of the members of the class.
        [read skip] class_members: Option<Vec<String>>,
        /// True when `__all__` lists the name.
        [read skip] declared_in_all: Option<bool>,
        /// The evidence of the decorators.
        [wire skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        /// The decorators as written.
        [read] decorators: Vec<String>,
        /// True when a call of the class returns an instance.
        [read skip] default_instance_result: Option<bool>,
        /// The places where the definition is made.
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        /// The members of an enum class.
        [read skip] enum_members: Option<Vec<String>>,
        /// The fields of the class.
        [read skip] fields: Option<Vec<Field>>,
        /// True when the instances cannot change.
        [read skip] frozen_object: Option<bool>,
        /// The generic bases with their arguments.
        [read skip] generic_bases: Option<Vec<GenericBase>>,
        /// The type parameters of the class.
        [read skip] generic_parameters: Option<Vec<String>>,
        /// The boolean members that a guard reads.
        [read skip] guard_boolean_members: Option<Vec<GuardBooleanMember>>,
        /// The evidence of the scope of the instance members.
        [read absent] instance_member_scope_evidence_id: Nullable<EvidenceId>,
        /// The instance members that the class writes.
        [read skip] instance_member_writes: Option<Vec<String>>,
        /// The id of the symbol that holds it in the source text.
        [read required] lexical_parent_id: Option<FactId>,
        /// The inventories of the members, by kind.
        [read] member_inventories: Vec<MemberInventory>,
        /// True when the class can serve as a mixin.
        [read skip] mixin_capable: Option<bool>,
        /// The modifiers as written.
        [wire skip] modifiers: Option<Vec<String>>,
        /// The module that holds it.
        [read] module: ModuleName,
        /// The name as written.
        [read] name: String,
        /// True when the namespace binds the name.
        [read skip] namespace_bound: Option<bool>,
        /// True when the definition is an overload signature.
        [wire skip] overload_signature: Option<bool>,
        /// The package that holds the module.
        [read] package: PackageName,
        /// The qualified name of the parent symbol.
        [read required] parent: Option<String>,
        /// The names of the properties.
        [read skip] property_members: Option<Vec<String>>,
        /// The name with the names of its parents.
        [read] qualified_name: String,
        /// True when the collector reads the whole signature.
        [wire skip] signature_complete: Option<bool>,
        /// True when one statement binds the name in the source.
        [read] source_binding_unique: bool,
        /// True when the header of the class in the source is read in full.
        [read skip] source_class_header_static: Option<bool>,
        /// The file that holds the source.
        [wire skip] source_file: Option<String>,
        /// True when no statement rebinds the member.
        [read] source_member_binding_static: bool,
        /// True when no statement rebinds the owner of the members.
        [read skip] source_member_owner_static: Option<bool>,
        /// The category of the symbol.
        [read] symbol_category: SymbolCategory,
        /// True when the header of the typed dict is read in full.
        [read skip] typed_dict_header_static: Option<bool>,
        /// The visibility of the symbol.
        [read skip] visibility: Option<Visibility>,
        /// How the visibility is written and why it holds.
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A function or a method and its signature.
    pub struct CallableData {
        /// The kind of accessor, for a property method.
        [read skip] accessor_kind: Option<String>,
        /// The annotation as written.
        [read absent] annotation: Nullable<String>,
        /// True for an `async` function.
        [read skip "async"] is_async: Option<bool>,
        /// True when the header of the class is read in full.
        [wire skip] class_header_static: Option<bool>,
        /// The signature facts of a context manager factory.
        [read skip] contextmanager_signature: Option<ContextmanagerSignature>,
        /// True when `__all__` lists the name.
        [read skip] declared_in_all: Option<bool>,
        /// The evidence of the decorators.
        [wire skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        /// The decorators as written.
        [read] decorators: Vec<String>,
        /// The places where the definition is made.
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        /// The id of the symbol that holds it in the source text.
        [read required] lexical_parent_id: Option<FactId>,
        /// The kind of the method.
        [read skip] method_kind: Option<MethodKind>,
        /// The modifiers as written.
        [read skip] modifiers: Option<Vec<String>>,
        /// The module that holds it.
        [read] module: ModuleName,
        /// The name as written.
        [read] name: String,
        /// True when the namespace binds the name.
        [read skip] namespace_bound: Option<bool>,
        /// True when the definition is an overload signature.
        [read] overload_signature: bool,
        /// True when overloads exist.
        [read skip] overloaded: Option<bool>,
        /// The package that holds the module.
        [read] package: PackageName,
        /// The parameters in order.
        [read] parameters: Vec<Parameter>,
        /// True when the collector reads each parameter.
        [read skip] parameters_contained: Option<bool>,
        /// The qualified name of the parent symbol.
        [read required] parent: Option<String>,
        /// The binding that a property method makes.
        [read skip] property_binding: Option<PropertyBinding>,
        /// The name with the names of its parents.
        [read] qualified_name: String,
        /// The parameter that holds the receiver.
        [read absent] receiver_parameter: Nullable<String>,
        /// The return annotation as written.
        [read required] returns: Option<String>,
        /// The shape of the written return type.
        [read skip] returns_shape: Option<TypeShape>,
        /// The shape of the function body, as a digest text.
        [read skip] shape: Option<String>,
        /// The number of nodes in the shape.
        [read skip] shape_nodes: Option<i64>,
        /// True when the collector reads the whole signature.
        [read skip] signature_complete: Option<bool>,
        /// True when the decorators of the signature are proven.
        [read skip] signature_decorators_proven: Option<bool>,
        /// True when no statement rebinds the name.
        [read skip] source_binding_static: Option<bool>,
        /// True when one statement binds the name in the source.
        [read skip] source_binding_unique: Option<bool>,
        /// The file that holds the source.
        [wire skip] source_file: Option<String>,
        /// True when the method binding is final.
        [read skip] source_final_method_binding: Option<bool>,
        /// True when no statement rebinds the member.
        [read skip] source_member_binding_static: Option<bool>,
        /// The writes of parameters into fields.
        [read skip] stored_field_writes: Option<Vec<StoredFieldWrite>>,
        /// The category of the symbol.
        [read] symbol_category: SymbolCategory,
        /// The visibility of the symbol.
        [read skip] visibility: Option<Visibility>,
        /// How the visibility is written and why it holds.
        [read] visibility_detail: VisibilityDetail,
    }
}

facts_data! {
    /// A constant, a type alias or another named binding of a value.
    pub struct ValueData {
        /// The type that the alias names.
        [read skip] alias: Option<String>,
        /// The annotation as written.
        [read absent] annotation: Nullable<String>,
        /// True when the header of the class is read in full.
        [read skip] class_header_static: Option<bool>,
        /// The constant value, when it is one.
        [read absent] constant: Nullable<Literal>,
        /// The evidence of the decorators.
        [read skip] decorator_evidence_ids: Option<Vec<EvidenceId>>,
        /// The decorators as written.
        [read skip] decorators: Option<Vec<String>>,
        /// The places where the definition is made.
        [read skip] definition_contexts: Option<Vec<DefinitionContext>>,
        /// The expression that sets the value.
        [read absent] initializer: Nullable<String>,
        /// The id of the symbol that holds it in the source text.
        [read absent] lexical_parent_id: Nullable<FactId>,
        /// The modifiers as written.
        [read skip] modifiers: Option<Vec<String>>,
        /// The module that holds it.
        [read] module: ModuleName,
        /// The name as written.
        [read] name: String,
        /// True when the definition is an overload signature.
        [read skip] overload_signature: Option<bool>,
        /// The package that holds the module.
        [read skip] package: Option<PackageName>,
        /// The parameters, when the value is a callable type.
        [read skip] parameters: Option<Vec<Parameter>>,
        /// The qualified name of the parent symbol.
        [read required] parent: Option<String>,
        /// The name with the names of its parents.
        [read] qualified_name: String,
        /// The kind of the record.
        [read skip] record_kind: Option<String>,
        /// The return annotation as written.
        [read absent] returns: Nullable<String>,
        /// True when the collector reads the whole signature.
        [read skip] signature_complete: Option<bool>,
        /// True when one statement binds the name in the source.
        [read] source_binding_unique: bool,
        /// The file that holds the source.
        [read skip] source_file: Option<String>,
        /// True when no statement rebinds the member.
        [read skip] source_member_binding_static: Option<bool>,
        /// The category of the symbol.
        [read skip] symbol_category: Option<SymbolCategory>,
        /// The visibility of the symbol.
        [read skip] visibility: Option<Visibility>,
        /// How the visibility is written and why it holds.
        [read] visibility_detail: VisibilityDetail,
    }
}

/// The fields that each declaration shares: where it is, what it is called and how visible it is.
/// A producer that reads declarations without types (Rust) builds its data from this header.
#[derive(Clone, Debug)]
pub struct Declared {
    /// The module that holds it.
    pub module: ModuleName,
    /// The package that holds the module.
    pub package: PackageName,
    /// The name as written.
    pub name: String,
    /// The name with the names of its parents.
    pub qualified_name: String,
    /// The qualified name of the type or trait that holds the declaration.
    pub parent: Option<String>,
    /// The id of the symbol that holds it in the source text.
    pub lexical_parent_id: Option<FactId>,
    /// No other declaration of the file has the same qualified name.
    pub unique: bool,
    /// How the visibility is written and why it holds.
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
            returns_shape: None,
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
