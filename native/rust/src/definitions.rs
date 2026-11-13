// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that the scan reads of a file (AD-351, slice 5b-4a): their form, name,
//! visibility and holder. `scan_definitions.rs` fills them and `symbols.rs` writes the records.

use crate::site::Site;

/// The form of a definition. A `mod` is a file fact, and `impl Trait for T` has no definition.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Form {
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
pub(crate) enum Access {
    Public,
    /// `pub(crate)`, `pub(super)`, `pub(in path)` and an unexported `macro_rules!`: the spelling.
    Package(String),
    Private,
}

/// What holds a definition.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Owner {
    Module,
    /// An inherent `impl`: the name of its type when it is one plain name. The type must be a
    /// definition of the same module and scope, or the members are not read.
    Impl(Option<String>),
    Trait(String),
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Definition {
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
pub(crate) enum Holder {
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
pub(crate) struct ImplBlock {
    /// The segments of the type path, or `None` when the type is not a plain path.
    pub path: Option<Vec<String>>,
    /// The inline modules of the file that enclose the block.
    pub scope: Vec<String>,
    /// Each `fn` and `const` of the block, with its visibility as written.
    pub members: Vec<Member>,
    /// The block has no type or const parameter, its type has no type or const argument, and no
    /// attribute that can change it: its members are the members of the one type that it names.
    pub exact: bool,
}

/// The `self` parameter of a method as written: `self`, `&self` or `&mut self` (with any lifetime
/// and `mut`). A typed `self: X` is no kind: the scan does not read types.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SelfKind {
    Value,
    Shared,
    Unique,
}

/// A method call whose receiver is the plain `self` of a method of an `impl` block, or a path
/// `Self::m` in such a block (AD-383): the path of the type of the block, the inline modules that
/// enclose the block, and the kind of the `self` parameter of the method (`None` for a path).
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct OnSelf {
    pub path: Vec<String>,
    pub scope: Vec<String>,
    pub kind: Option<SelfKind>,
}

/// A member of an inherent `impl` block. Only a `fn` with a `self` parameter can be called as
/// `x.m()`; any other member needs a path.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Member {
    pub name: String,
    pub access: Access,
    pub receiver: bool,
    /// The kind of the `self` parameter, or `None` when it is typed, absent, or an attribute
    /// other than an inert one is on the member.
    pub kind: Option<SelfKind>,
    /// The parameters besides `self`.
    pub arity: usize,
}

/// A method call `x.m(..)` or `x.m::<..>(..)`, or a path `T::m` into another crate: the name, the
/// place and the enclosing inline modules. A path can reach a member without a `self` parameter.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct MethodCall {
    pub name: String,
    pub site: Site,
    pub scope: Vec<String>,
    pub path: bool,
    /// The arguments of `x.m(..)`, or `None` when the scan does not know them (a macro, a path).
    pub arity: Option<usize>,
    /// The receiver is the plain `self` of a method of an `impl` block with an exact type.
    pub on_self: Option<OnSelf>,
}
