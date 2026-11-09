// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The path from the root to the node that the walk visits.
//!
//! `walk.rs` pushes an entry for each node. `definitions.rs` reads the stack and the flags to place
//! a definition.

use tree_sitter::Node;

use crate::kinds::K;

/// An ancestor is a node the parser had to repair.
pub const ERROR_ABOVE: u8 = 1;
/// An ancestor is an `internal_module` (`namespace` or `module`).
pub const INSIDE_NAMESPACE: u8 = 2;
/// An ancestor is a statement block that is not the `body` of its parent.
pub const IN_UNMODELED_BLOCK: u8 = 4;
/// An ancestor is a function declaration, a method or an arrow function.
pub const IN_REBOUND_FUNCTION: u8 = 8;
/// An ancestor is a function, a class body or a namespace.
pub const IN_FUNCTION_LIKE: u8 = 16;

/// One node on the path from the root to the node that the walk visits.
pub struct Entry<'t> {
    pub node: Node<'t>,
    pub kind: K,
    /// The flags that the children of this node see.
    pub flags: u8,
    /// The frame of the nearest scope, this node included.
    pub frame: u32,
    /// The frame of the nearest `var` scope, this node included.
    pub var_frame: u32,
    /// The nearest definition that holds this node, this node included.
    pub scope: Option<u32>,
    /// The decorators and comments among the named children seen so far that directly precede
    /// the next child.
    pub run: Vec<Node<'t>>,
}
