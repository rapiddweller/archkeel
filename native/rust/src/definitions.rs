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
