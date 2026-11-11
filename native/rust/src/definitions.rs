// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that the scan reads of a file (AD-351, slice 5b-4a): their form, name,
//! visibility and holder. `scan_definitions.rs` fills them and `symbols.rs` writes the records.

use crate::site::Site;

/// The form of a definition. A `mod` is a file fact, and `impl Trait for T` has no definition.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Form {
    Function,
    Struct,
    Enum,
    Trait,
    Constant,
    Static,
    Alias,
    Macro,
}

/// How visible a definition is, as written.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Access {
    Public,
    /// `pub(crate)`, `pub(super)`, `pub(in path)` and an unexported `macro_rules!`: the spelling.
    Package(String),
    Private,
}

/// What holds a definition.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Owner {
    Module,
    /// An inherent `impl`: the name of its type when it is one plain name. The type must be a
    /// definition of the same module and scope, or the members are not read.
    Impl(Option<String>),
    Trait(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Definition {
    pub form: Form,
    pub name: String,
    /// The inline modules of the file that enclose the definition.
    pub scope: Vec<String>,
    pub access: Access,
    pub owner: Owner,
    pub site: Site,
    /// The variants of an enum.
    pub variants: Vec<String>,
    /// A function with a `self` parameter.
    pub receiver: bool,
    pub is_async: bool,
}

/// What the walk is inside: it decides which members are definitions.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum Holder {
    #[default]
    Module,
    Impl(Option<String>),
    Trait(String, Access),
    /// `impl Trait for T`: the trait declares the members, so the block defines nothing.
    TraitImpl,
}

/// An inherent `impl` block at any depth: the path of its type as written, and its members. A
/// method call elsewhere may reach a member, so the collector reads the block even in a function
/// body, where it defines nothing of the module (#953).
#[derive(Clone, Debug, PartialEq)]
pub struct ImplBlock {
    /// The segments of the type path, or `None` when the type is not a plain path.
    pub path: Option<Vec<String>>,
    /// The inline modules of the file that enclose the block.
    pub scope: Vec<String>,
    /// Each `fn` and `const` of the block, with its visibility as written.
    pub members: Vec<Member>,
}

/// A member of an inherent `impl` block. Only a `fn` with a `self` parameter can be called as
/// `x.m()`; any other member needs a path.
#[derive(Clone, Debug, PartialEq)]
pub struct Member {
    pub name: String,
    pub access: Access,
    pub receiver: bool,
    /// The parameters besides `self`.
    pub arity: usize,
}

/// A method call `x.m(..)` or `x.m::<..>(..)`, or a path `T::m` into another crate: the name, the
/// place and the enclosing inline modules. A path can reach a member without a `self` parameter.
#[derive(Clone, Debug, PartialEq)]
pub struct MethodCall {
    pub name: String,
    pub site: Site,
    pub scope: Vec<String>,
    pub path: bool,
    /// The arguments of `x.m(..)`, or `None` when the scan does not know them (a macro, a path).
    pub arity: Option<usize>,
}
