// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python builtin names that the readers select by role: one table, one flag for each role.
//!
//! A builtin name is written once. A reader asks for the names of its role (`named`) or whether a
//! name has the role (`has`). The roles differ on purpose: each one is a fact that a proof reads,
//! and the doc of the role says which.

/// The role of a builtin name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Role(u16);

impl Role {
    /// A call of the name makes an instance of that type, never another object.
    pub(crate) const VALUE_CALL: Role = Role(1);
    /// An annotation or a default can read the name as a type or a value; a module that binds the
    /// name makes its text name something else.
    pub(crate) const ANNOTATION: Role = Role(1 << 1);
    /// A written type can name the class. Another builtin is a name with no proof.
    pub(crate) const WRITTEN_TYPE: Role = Role(1 << 2);
    /// The primitives among the builtin classes.
    pub(crate) const PRIMITIVE: Role = Role(1 << 3);
    /// A call gives a scalar, whatever the arguments are.
    pub(crate) const SCALAR_CALL: Role = Role(1 << 4);
    /// A call gives a container of its arguments.
    pub(crate) const CONTAINER_CALL: Role = Role(1 << 5);
    /// A module-level `def` of the name is not the builtin: the shared namespace exposure reads it.
    pub(crate) const NAME_CONTAINER: Role = Role(1 << 6);
    /// The builtin only reads the mapping that it receives.
    pub(crate) const MAPPING_READER: Role = Role(1 << 7);
}

use Role as R;

const fn roles(parts: &[Role]) -> u16 {
    let mut flags = 0;
    let mut index = 0;
    while index < parts.len() {
        flags |= parts[index].0;
        index += 1;
    }
    flags
}

/// The roles of the five scalar classes that a call makes and a written type names.
const SCALAR: u16 = roles(&[
    R::VALUE_CALL,
    R::ANNOTATION,
    R::WRITTEN_TYPE,
    R::PRIMITIVE,
    R::SCALAR_CALL,
]);
/// The roles of the five container classes.
const CONTAINER: u16 = roles(&[
    R::VALUE_CALL,
    R::ANNOTATION,
    R::WRITTEN_TYPE,
    R::CONTAINER_CALL,
]);

/// Each builtin name with its roles. The order of the rows is the order in which the annotation
/// readers list the names that a module shadows.
const TABLE: [(&str, u16); 23] = [
    ("int", SCALAR),
    ("str", SCALAR),
    ("float", SCALAR),
    ("bool", SCALAR),
    ("bytes", SCALAR),
    ("bytearray", roles(&[R::ANNOTATION])),
    (
        "complex",
        roles(&[R::ANNOTATION, R::WRITTEN_TYPE, R::PRIMITIVE, R::SCALAR_CALL]),
    ),
    (
        "list",
        CONTAINER | roles(&[R::NAME_CONTAINER, R::MAPPING_READER]),
    ),
    ("dict", CONTAINER | roles(&[R::MAPPING_READER])),
    (
        "set",
        CONTAINER | roles(&[R::NAME_CONTAINER, R::MAPPING_READER]),
    ),
    ("frozenset", CONTAINER | roles(&[R::NAME_CONTAINER])),
    (
        "tuple",
        CONTAINER | roles(&[R::NAME_CONTAINER, R::MAPPING_READER]),
    ),
    ("object", roles(&[R::ANNOTATION, R::WRITTEN_TYPE])),
    ("type", roles(&[R::ANNOTATION])),
    ("range", roles(&[R::ANNOTATION])),
    ("slice", roles(&[R::ANNOTATION])),
    ("memoryview", roles(&[R::ANNOTATION])),
    ("property", roles(&[R::ANNOTATION])),
    (
        "sorted",
        roles(&[R::CONTAINER_CALL, R::NAME_CONTAINER, R::MAPPING_READER]),
    ),
    (
        "len",
        roles(&[R::SCALAR_CALL, R::NAME_CONTAINER, R::MAPPING_READER]),
    ),
    ("repr", roles(&[R::SCALAR_CALL])),
    ("hash", roles(&[R::SCALAR_CALL])),
    ("ord", roles(&[R::SCALAR_CALL])),
];

/// The names that have the role, in the order of the table.
pub(crate) fn named(role: Role) -> impl Iterator<Item = &'static str> {
    TABLE
        .iter()
        .filter(move |(_, flags)| flags & role.0 != 0)
        .map(|(name, _)| *name)
}

/// True when the name has the role.
pub(crate) fn has(name: &str, role: Role) -> bool {
    named(role).any(|candidate| candidate == name)
}
