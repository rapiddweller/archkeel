// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The fields that a check reads from a record by name, across kinds (AD-346).
//!
//! The data types differ per kind, and the Python checks read `source_module`, `owner` and
//! `targets` by name from each kind that has them. `Fields` is that cross-kind reading: it
//! borrows the typed values of one record, and a field that the kind does not have is `None`. A
//! reader needs no JSON round trip, and no field is read by a text key.

use crate::data::{
    BindingData, CallData, CallableData, ClassData, ConstructData, GapData, ImportData,
    NumericOperandData, PlaceholderData, PlainConstructData, ReferenceData, SelectorData,
    SignalData, SourceRoleData, UnusedBindingData, ValueData,
};
use crate::ids::{FactId, ModuleName, PackageName};
use crate::nested::{AttributeDeclaration, BaseDeclaration, MemberInventory};
use crate::nullable::Nullable;
use crate::vocab::{ResolutionDimension, Status};

/// A field that can be absent, `null` or a value: `None`, `Some(None)` or `Some(Some(value))`.
pub type Named<'a> = Option<Option<&'a str>>;

/// The fields of one record that the generic checks read. A field that the kind does not have, or
/// that holds `null` (except the two `Named` fields), is `None` or `false`.
#[derive(Debug, Default)]
pub struct Fields<'a> {
    /// The module of the source side.
    pub source_module: Named<'a>,
    /// The module that the record is about.
    pub module: Named<'a>,
    /// The symbol that owns the record.
    pub owner: Option<&'a str>,
    /// The scope of the source side.
    pub source_scope: Option<&'a str>,
    /// The qualified name of the symbol.
    pub qualified_name: Option<&'a str>,
    /// The scope that declares the symbol.
    pub declaration_scope: Option<&'a str>,
    /// The package of the source side.
    pub source_package: Option<&'a str>,
    /// The module of the target side.
    pub target_module: Option<&'a str>,
    /// The package of the target side.
    pub target_package: Option<&'a str>,
    /// The name of the construct.
    pub construct: Option<&'a str>,
    /// The file of the source side.
    pub source_file: Option<&'a str>,
    /// The expression as written.
    pub expression: Option<&'a str>,
    /// The proof state of the record.
    pub status: Option<Status>,
    /// The qualified names that the record resolves to.
    pub targets: Option<&'a [String]>,
    /// The dimension of the resolution that the record names.
    pub resolution_dimension: Option<&'a str>,
    /// The file of the record.
    pub file: Option<&'a str>,
    /// The id of the symbol that holds it in the source text.
    pub lexical_parent_id: Option<&'a str>,
    /// The base declarations of a class.
    pub base_declarations: Option<&'a [BaseDeclaration]>,
    /// The member inventories of a class.
    pub member_inventories: Option<&'a [MemberInventory]>,
    /// The attribute declarations of a class.
    pub attribute_declarations: Option<&'a [AttributeDeclaration]>,
    /// The fields below hold a value that a Python check proves. The store only sees that the
    /// field is set.
    pub call_binding: bool,
    /// True when the record carries call arguments.
    pub call_arguments: bool,
    /// True when the record carries a guarded effect.
    pub guarded_effect: bool,
    /// True when the record carries a context manager signature.
    pub contextmanager_signature: bool,
    /// True when the record carries guard boolean members.
    pub guard_boolean_members: bool,
    /// True when the record carries property members.
    pub property_members: bool,
    /// True when the record carries a local source binding.
    pub local_source_binding: bool,
    /// True when the record carries the id of its definition.
    pub declaration_definition_id: bool,
    /// True when the record carries the scope evidence of an instance member.
    pub instance_member_scope_evidence_id: bool,
    /// True when the record carries a receiver binding.
    pub receiver_binding: bool,
}

/// The data of one kind: it gives the `Fields` that the kind has.
pub(crate) trait Project {
    fn fields(&self) -> Fields<'_>;
}

/// A typed value as one `Fields` entry. The entry type picks the conversion.
trait Lens<'a, T> {
    fn lens(&'a self) -> T;
}

impl<'a> Lens<'a, Option<&'a str>> for String {
    fn lens(&'a self) -> Option<&'a str> {
        Some(self)
    }
}

impl<'a> Lens<'a, Option<&'a str>> for Option<String> {
    fn lens(&'a self) -> Option<&'a str> {
        self.as_deref()
    }
}

macro_rules! text_ids {
    ($($id:ty),*) => {$(
        impl<'a> Lens<'a, Option<&'a str>> for $id {
            fn lens(&'a self) -> Option<&'a str> {
                Some(self.as_str())
            }
        }

        impl<'a> Lens<'a, Named<'a>> for $id {
            fn lens(&'a self) -> Named<'a> {
                Some(Some(self.as_str()))
            }
        }
    )*};
}

text_ids!(ModuleName, PackageName);

impl<'a> Lens<'a, Named<'a>> for Option<ModuleName> {
    fn lens(&'a self) -> Named<'a> {
        self.as_ref().map(|name| Some(name.as_str()))
    }
}

impl<'a> Lens<'a, Option<&'a str>> for Option<FactId> {
    fn lens(&'a self) -> Option<&'a str> {
        self.as_ref().map(FactId::as_str)
    }
}

impl<'a> Lens<'a, Option<&'a str>> for Nullable<FactId> {
    fn lens(&'a self) -> Option<&'a str> {
        match self {
            Nullable::Value(id) => Some(id.as_str()),
            Nullable::Absent | Nullable::Null => None,
        }
    }
}

impl<'a> Lens<'a, Option<&'a str>> for Option<ResolutionDimension> {
    fn lens(&'a self) -> Option<&'a str> {
        self.map(ResolutionDimension::as_str)
    }
}

impl<'a> Lens<'a, Option<Status>> for Status {
    fn lens(&'a self) -> Option<Status> {
        Some(*self)
    }
}

impl<'a, T> Lens<'a, Option<&'a [T]>> for Vec<T> {
    fn lens(&'a self) -> Option<&'a [T]> {
        Some(self)
    }
}

impl<'a, T> Lens<'a, bool> for Option<T> {
    fn lens(&'a self) -> bool {
        self.is_some()
    }
}

impl<'a, T> Lens<'a, bool> for Nullable<T> {
    fn lens(&'a self) -> bool {
        matches!(self, Nullable::Value(_))
    }
}

/// The `Fields` of each data type: the fields that the type has, by name.
macro_rules! project {
    ($($data:ident { $($field:ident),* })*) => {$(
        impl Project for $data {
            fn fields(&self) -> Fields<'_> {
                Fields { $($field: Lens::lens(&self.$field),)* ..Fields::default() }
            }
        }
    )*};
}

project! {
    ConstructData { construct, owner }
    PlainConstructData { construct, owner }
    PlaceholderData { construct, owner }
    SelectorData { construct, owner, status, receiver_binding }
    NumericOperandData { module, owner }
    SignalData { expression, owner, qualified_name }
    ImportData { source_module, source_package, target_module, target_package }
    GapData { module, source_module, resolution_dimension, file }
    CallData {
        expression, source_file, source_module, source_scope, status, targets,
        call_arguments, call_binding, guarded_effect
    }
    ReferenceData {
        declaration_scope, declaration_definition_id, expression, local_source_binding,
        source_file, source_module, source_scope, status, targets
    }
    SourceRoleData { expression, source_module, source_scope, status, targets }
    BindingData { module, source_module, source_scope }
    UnusedBindingData { module, owner }
    ClassData {
        attribute_declarations, base_declarations, guard_boolean_members,
        instance_member_scope_evidence_id, lexical_parent_id, member_inventories, module,
        property_members, qualified_name, source_file
    }
    CallableData {
        contextmanager_signature, lexical_parent_id, module, qualified_name, source_file
    }
    ValueData { lexical_parent_id, module, qualified_name, source_file }
}

#[cfg(test)]
#[path = "fields_tests.rs"]
mod tests;
