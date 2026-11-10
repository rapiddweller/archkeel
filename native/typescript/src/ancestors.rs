// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The path from the root to the node that the walk visits.
//!
//! `walk.rs` pushes an entry for each node. `definitions.rs` and `sites.rs` read the stack and the
//! flags to place a definition or a site.

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
/// The node is inside a type: a type construct above it, or the type of an `as` or `satisfies`.
pub const IN_TYPE: u8 = 32;
/// An ancestor is the left side of an assignment that publishes `window.x` or `globalThis.x`.
pub const IN_PUBLICATION: u8 = 64;
/// An ancestor is a `with` statement. The eight bits of the flag byte are now all used: a ninth
/// flag needs a `u16`.
pub const IN_WITH: u8 = 128;

/// What an ancestor adds to the names that a site shadows: a scope that is not a definition, and
/// the constructs that make the lexical scope of the site uncertain (`_active_scope_names`).
pub const HARD_AMBIGUOUS: u8 = 1;
/// A function expression or an arrow function lies between the site and its definition.
pub const CROSSED_FUNCTION: u8 = 2;
/// The same, and the function is not an immediately called wrapper of a script.
pub const CROSSED_PLAIN_FUNCTION: u8 = 4;

/// What the walk of the sites keeps for the children of a node.
#[derive(Clone, Copy, Default)]
pub struct Shadow {
    /// The last scope of the chain that hides names (`site_names.rs`).
    pub chain: Option<u32>,
    pub ambiguous: u8,
}

/// One node on the path from the root to the node that the walk visits.
pub struct Entry<'t> {
    pub node: Node<'t>,
    pub kind: K,
    /// The flags that the children of this node see.
    pub flags: u8,
    /// The position of this node in the layout, or `NONE` when it is not recorded.
    pub at: u32,
    /// The frame of the nearest scope, this node included.
    pub frame: u32,
    /// The frame of the nearest `var` scope, this node included.
    pub var_frame: u32,
    /// The nearest definition that holds this node, this node included.
    pub scope: Option<u32>,
    /// The decorators and comments among the named children seen so far that directly precede
    /// the next child.
    pub run: Vec<Node<'t>>,
    /// The scopes between a node below and its definition, this node included.
    pub shadow: Shadow,
    /// The node is the callee of a call or `new`, or a member of the callee (`_inside_site_callee`).
    pub callee: bool,
    /// An `arguments` node whose call has a wrapper of a script as its callee.
    pub wrapped_call: bool,
}
