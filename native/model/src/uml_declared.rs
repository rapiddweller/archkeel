// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declared UML intent of a contract tree (AD-526): the target of each contract that has one.
//! `uml.rs` carries it in the row and `uml_tree.rs` compares it.

use archkeel_contract::Target;

/// The target of one contract of the tree: `mount` is the place of the inside contract in the walk
/// of the tree, and `None` for the root.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UmlPart {
    pub mount: Option<usize>,
    pub target: Target,
}

/// The declared intent of a tree: the target of each contract that has one, the root first.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UmlDeclared {
    pub parts: Vec<UmlPart>,
}

impl UmlDeclared {
    /// The number of entities, relationships and scopes of all parts.
    pub fn counts(&self) -> (usize, usize, usize) {
        self.parts.iter().fold((0, 0, 0), |sum, part| {
            (
                sum.0 + part.target.entities().len(),
                sum.1 + part.target.relationships().len(),
                sum.2 + part.target.scopes().len(),
            )
        })
    }
}
