// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the linked collector states about the standard library of its language (AD-782).
//!
//! The statements are no proof. The model reads them only when the contract declares the premise
//! `standard_library_unchanged` (AD-764): code outside the scan leaves the standard library
//! unchanged. Code of the repository that may change a name of the standard library is no part of
//! the premise: the collector lists such a name in `changed`, and the model gives a gap for it.
//! Wire replies carry none of this.

use std::collections::{BTreeMap, BTreeSet};

use crate::type_shape::TypeShape;
use crate::vocab::MethodKind;

/// The owner, name, type and evidence of the written members of a closed module.
pub type ProtocolMembers = Vec<(String, String, TypeShape, String)>;

/// The statements of one reply about the standard library.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct StandardFacts {
    /// True when the linked placeholder survey needs an unchanged standard library.
    pub placeholder_under_premise: bool,
    /// True when the linked Any inventory needs an unchanged standard library.
    pub any_annotation_under_premise: bool,
    /// The repository leaves the standard Protocol constructor unchanged.
    pub protocol_unchanged: bool,
    /// The linked member inventory and whether every class body was read, by module.
    pub protocol_members: BTreeMap<String, (bool, ProtocolMembers)>,
    /// Each type of the standard library that the collector names by its qualified name: a value
    /// type, a collection or a marker that holds no data. A name of the standard library that is
    /// not here stays a type outside the scan.
    pub types: BTreeSet<String>,
    /// Each name of `types` that code of the repository may change, with the reason in words.
    pub changed: BTreeMap<String, String>,
    /// Each definition of the scan whose decorators the collector models, by qualified name.
    pub wrapped: BTreeMap<String, Wrapped>,
    /// Each position of a written signature whose type reads a collection or a special form of
    /// the standard library by name (`typing.List`, `typing.Optional`), keyed
    /// `<qualified name>:<parameter or return>`, with those names (#1718). The shape of such a
    /// position is a collection or a union, so the model asks the premise for these names.
    pub positions: BTreeMap<String, BTreeSet<String>>,
}

/// One parameter of the form that a decorated definition exposes.
#[derive(Clone, Debug, PartialEq)]
pub struct WrappedSlot {
    /// The name of the parameter.
    pub name: String,
    /// The kind of the parameter, in the words of `Parameter::kind`.
    pub kind: String,
    /// The written type, if the collector reads it.
    pub shape: Option<TypeShape>,
}

/// What a decorated definition exposes after its decorators.
#[derive(Clone, Debug, PartialEq)]
pub enum Wrapped {
    /// A callable: its parameters in order and the type that a call gives.
    Callable {
        /// The method kind, for a definition in a class body.
        method: Option<MethodKind>,
        /// The parameters, the receiver first for an instance or class method.
        slots: Vec<WrappedSlot>,
        /// The type that a call gives.
        returns: TypeShape,
        /// The decorators, in the words of the collector, for the reason of a gap.
        decorators: Vec<String>,
        /// The evidence of the definition.
        evidence: Vec<String>,
    },
    /// A class whose decorator generates a constructor from its fields.
    Class {
        /// The parameters of the generated constructor, without the receiver; `None` when the
        /// decorator generates none.
        init: Option<Vec<WrappedSlot>>,
        /// The names that the class body binds, in order. Each method among them has a wrapped
        /// form of its own, or the model gives a gap for it.
        members: Vec<String>,
        /// The names that the class declares as fields.
        attributes: Vec<String>,
        /// The targets of the bases that the collector proves.
        bases: Vec<String>,
        /// The evidence of the definition.
        evidence: Vec<String>,
    },
    /// A decorator that the collector does not model for this definition, with the reason.
    Unread(String),
}
