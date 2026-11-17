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
    /// The written return type of a function (#1571); `Unknown` for any other form.
    pub ret: Written,
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

/// An `impl Trait for T` block at any depth (AD-516): the path of the outermost nominal type of
/// its self type after `&` (`None` for any other self type, a type parameter or a qualified
/// path), the path of its trait, the inline modules and the blocks (their ends) that enclose
/// it, and its place.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct TraitImpl {
    pub self_path: Option<Vec<String>>,
    pub trait_path: Option<Vec<String>>,
    pub scope: Vec<String>,
    pub blocks: Vec<(i64, i64)>,
    pub site: Site,
}

/// An item that a block declares, with the end of the block: a struct, enum or union (`nominal`),
/// any other item, or a `use` (`name` is `None`: it can bind any name).
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct BlockItem {
    pub name: Option<String>,
    pub end: (i64, i64),
    pub nominal: bool,
}

/// What the scan keeps for the pair gaps of trait impls in a third module (AD-516): the trait
/// impls, and the items of each block.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct OrphanFacts {
    pub impls: Vec<TraitImpl>,
    pub block_items: Vec<BlockItem>,
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
/// `Self::m` in such a block (AD-383), or a typed parameter of the `fn` (AD-524): the name of the
/// receiver (`self`, `Self` or the parameter), the path of its type, the inline modules that
/// enclose the item, and the kind of the receiver as written (`None` for a path).
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct OnSelf {
    pub name: String,
    pub path: Vec<String>,
    pub scope: Vec<String>,
    pub kind: Option<SelfKind>,
    /// The macros that the `fn` of a parameter calls and that are no silent macro of `std`: a
    /// path as written for a macro with a path, else its name (AD-524).
    pub macros: Vec<String>,
    /// Up to two named fields of the receiver.
    pub fields: Vec<String>,
}

/// One named field of a non-generic, exact struct.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Field {
    pub scope: Vec<String>,
    /// The plain path and the reference kind of the type (AD-383), or an empty path when the
    /// type is no plain path.
    pub path: Vec<String>,
    pub kind: SelfKind,
    pub access: Access,
    /// The type as written (#1571).
    pub written: Written,
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
    /// Only inert attributes are on the member: every configuration has it as written.
    pub inert: bool,
    /// The written return type (#1571): `Self` stays a path `Self`; a type parameter of the
    /// block or of the `fn`, `impl Trait` and an `async fn` are `Unknown`.
    pub ret: Written,
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
    /// The last name of the written type of a path `T::m` (`T`), or `None` when the scan does not
    /// know it (a method call, `Self::m`, a call in a macro body).
    pub owner: Option<String>,
    /// The receiver of a method call as the scan reads it (#1571), or `None`.
    pub chain: Option<Box<ReceiverChain>>,
}

/// A type as written (#1571): a relative path with the type arguments of its last segment
/// (lifetimes left out), a reference, or a slice or an array. Any other form is `Unknown`: a type
/// parameter, `impl Trait`, `dyn Trait`, a tuple, a qualified or absolute path, a macro.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Written {
    Path(Vec<String>, Vec<Written>),
    /// `&T` (`Shared`) or `&mut T` (`Unique`).
    Ref(SelfKind, Box<Written>),
    Slice(Box<Written>),
    Unknown,
}

/// Where the receiver of a method call starts (#1571).
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Root {
    /// A written type: `self` of an exact block, a typed parameter, local or closure parameter.
    Typed(Written),
    /// A literal: `str` (behind a reference), `char`, `bool`, `int` or `float`. No name hides it.
    Literal(&'static str),
    /// A call `f(..)`, `m::f(..)` or `T::f(..)` with its arguments: no name of the `fn` hides
    /// the first segment, and no macro call of the `fn` can add an item.
    Call(Vec<String>, usize),
    /// A struct literal `T { .. }` or a path `T::V` / a call `T::V(..)` (a variant), with the
    /// same proof as `Call`.
    Value(Vec<String>),
    /// The parameter of a closure that is the one argument of a std adapter (`map`, `filter`, ..)
    /// on the chain, or the variable of `for x in chain` (the adapter `for`).
    Element(Box<ReceiverChain>, String),
}

/// One step of a receiver chain.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Step {
    Field(String),
    /// A method call with its arguments.
    Call(String, usize),
    /// The `?` operator.
    Try,
    /// `&x` or `&mut x`.
    Borrow(SelfKind),
}

/// The receiver of a method call: a root and the steps that the scan reads (#1571).
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ReceiverChain {
    /// The root as written, for the evidence.
    pub name: String,
    pub root: Root,
    pub steps: Vec<Step>,
    /// The macros of the `fn` that are no silent macro of `std` (AD-524).
    pub macros: Vec<String>,
}
