// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The written type of one position of a signature, as a closed tree (AD-550).
//!
//! The tree names no language. A collector reads its own annotation syntax and writes the same
//! few forms: a scalar, a type that holds anything, a collection, a union, a name with the binding
//! that the collector proved, and the forms that it cannot read. The model decides a boundary rule
//! from the tree and never parses a text.
//!
//! A tree states what is *written*. A name that the collector proves (a builtin that no statement
//! hides, a name that one plain statement of the module binds) carries its qualified `target`;
//! any other name carries the cause that stopped the proof. The tree never states what a name
//! *means* beyond that binding: an alias, a user generic and a type outside the scan are decided
//! by the model from the records, or are a named gap.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

closed! {
    /// How a collection type reads its element types.
    pub enum Family {
        /// Elements in order or in a set: `list`, `tuple`, `Sequence`, `Iterable`.
        Sequence = "sequence",
        /// Keys and values: `dict`, `Mapping`.
        Mapping = "mapping",
    }
}

closed! {
    /// Why a form of a type expression is not read.
    pub enum Unreadable {
        /// A call, a number, a lambda or another form that is no type expression.
        NotATypeForm = "not_a_type_form",
        /// The collector cannot write the text of the form.
        TextUnwritable = "text_unwritable",
        /// The expression is nested deeper than the collector reads.
        TooDeep = "too_deep",
    }
}

closed! {
    /// Why the collector does not prove the binding of a name.
    pub enum Unproven {
        /// A star import in the module can bind any name.
        StarImport = "star_import",
        /// A name of the enclosing class body or a type parameter hides the name.
        Hidden = "hidden",
        /// Another statement binds the name too, or the statement is not directly in the module
        /// body (`if`, `try`, `for`, `with`).
        NotSole = "not_sole",
        /// The one plain binder is an import that the collector does not follow: a name under
        /// `TYPE_CHECKING`, a module of the scan that it cannot name.
        UnreadImport = "unread_import",
        /// No statement of the module binds the name and it is no builtin.
        Unbound = "unbound",
        /// A chain of attributes that is not one name of one plain module import.
        Dotted = "dotted",
    }
}

/// What a name is bound to when the module runs.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "binding", rename_all = "snake_case", deny_unknown_fields)]
pub enum Binding {
    /// A builtin of the language that no statement of the module hides. `target` is the name in
    /// the namespace of the builtins.
    Builtin { target: String },
    /// One plain statement of the module body binds the name: a class, a function or a value.
    /// `target` is the qualified name in this module.
    Defined { target: String },
    /// One plain import binds the name. `target` is the qualified name that the import reads: a
    /// name of another module, or an attribute of one module object.
    Imported { target: String },
    /// The collector does not prove the binding.
    Unproven { cause: Unproven },
}

/// The written type of one position.
///
/// `text` is the text of the node in the form that the reference collector writes for it, the text
/// that an exact exception of a rule matches.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "shape", rename_all = "snake_case", deny_unknown_fields)]
pub enum TypeShape {
    /// No type is written.
    Unannotated {},
    /// The type of the one value that means "nothing".
    Nothing {},
    /// A scalar of the language that holds no named data and is not hidden: `int`, `str`.
    Primitive { text: String, name: String },
    /// A type that holds anything: `object`, `Any`. The binding is proven.
    Dynamic { text: String, name: String },
    /// A collection of the language or its standard library, by proven binding. `args` empty is
    /// the bare name. `open_end` is a tuple of any length of one element type (`tuple[X, ...]`).
    Collection {
        text: String,
        family: Family,
        name: String,
        args: Vec<TypeShape>,
        open_end: bool,
    },
    /// One of several types, flattened: `X | Y`, `Union[X, Y]`, `Optional[X]` (`X` and nothing).
    Union { text: String, arms: Vec<TypeShape> },
    /// Constant values as a type. `plain`: each value is a string, a number, a boolean, bytes or
    /// the nothing value.
    Literal { text: String, plain: bool },
    /// A type with metadata that does not change it: the inner type decides.
    Annotated { text: String, inner: Box<TypeShape> },
    /// A name, with its binding.
    Named { text: String, binding: Binding },
    /// A name applied to arguments that the collector does not model: a user generic.
    Applied {
        text: String,
        head: Box<TypeShape>,
        args: Vec<TypeShape>,
    },
    /// A type written as a string: the collector does not resolve it.
    Forward { text: String },
    /// A form that the collector does not read.
    Unreadable { text: String, cause: Unreadable },
}

impl TypeShape {
    /// The text of the node: what an exact exception of a rule matches. A missing annotation and
    /// the nothing value have the text that Python writes for them.
    pub fn text(&self) -> &str {
        match self {
            TypeShape::Unannotated {} => "",
            TypeShape::Nothing {} => "None",
            TypeShape::Primitive { text, .. }
            | TypeShape::Dynamic { text, .. }
            | TypeShape::Collection { text, .. }
            | TypeShape::Union { text, .. }
            | TypeShape::Literal { text, .. }
            | TypeShape::Annotated { text, .. }
            | TypeShape::Named { text, .. }
            | TypeShape::Applied { text, .. }
            | TypeShape::Forward { text }
            | TypeShape::Unreadable { text, .. } => text,
        }
    }
}

#[cfg(test)]
#[path = "type_shape_tests.rs"]
mod tests;
