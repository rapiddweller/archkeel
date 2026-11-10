// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The layout of the named nodes of a file: their document order, their parents, the end of each
//! subtree and the flags that a node takes from its parent. The walk records it on the way down
//! and up, so the script facts (`script_scope.rs`) need no second traversal of the tree.

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

use tree_sitter::{Node, TreeCursor};

use crate::kinds::K;
use crate::members::Cx;

/// The functions that a return statement belongs to: the four kinds that a wrapper can be.
pub fn is_function_like(kind: K) -> bool {
    matches!(
        kind,
        K::FunctionDeclaration | K::FunctionExpression | K::ArrowFunction | K::MethodDefinition
    )
}

/// A hasher for the ids of nodes, which are addresses: the bits above the alignment are mixed into
/// the low bits that a table indexes by. The default hasher is slower and has no use for the
/// protection that it gives against chosen keys: the ids are not chosen by the input.
#[derive(Default)]
pub struct IdHasher(u64);

impl Hasher for IdHasher {
    fn finish(&self) -> u64 {
        self.0 ^ self.0.wrapping_shr(29)
    }

    fn write(&mut self, bytes: &[u8]) {
        for byte in bytes {
            self.0 = (self.0 ^ u64::from(*byte)).wrapping_mul(0x0100_0000_01b3);
        }
    }

    fn write_usize(&mut self, value: usize) {
        self.0 = u64::try_from(value)
            .unwrap_or(u64::MAX)
            .wrapping_mul(0x9e37_79b9_7f4a_7c15);
    }
}

/// A map by the id of a node.
pub type IdMap<V> = HashMap<usize, V, BuildHasherDefault<IdHasher>>;

/// The position of the parent of the root, and of a node that is not recorded.
pub(crate) const NONE: u32 = u32::MAX;

/// The flags of a node (`Tree::flag`): inside a repair, inside a type, inside a function.
pub(crate) const IN_ERROR: u8 = 1;
pub(crate) const IN_TYPE: u8 = 2;
pub(crate) const IN_FUNCTION: u8 = 4;
/// The node is, or lies inside, a scope that is not statically known (set by `index_scopes`).
pub(crate) const IN_AMBIGUOUS: u8 = 8;

/// `_TYPE_PARENTS`: a node below one of these kinds is part of a type.
fn is_type_parent(kind: K) -> bool {
    matches!(
        kind,
        K::TypeAnnotation
            | K::TypeArguments
            | K::TypeQuery
            | K::TypeAliasDeclaration
            | K::TypeParameter
            | K::ExtendsTypeClause
            | K::ImplementsClause
    )
}

/// The named nodes in document order, with what a pass over them needs.
#[derive(Default)]
pub struct Layout<'t> {
    pub(crate) nodes: Vec<Node<'t>>,
    /// The position of each node by its id.
    pub(crate) position: IdMap<usize>,
    /// The position of the parent of each node, or `NONE`.
    pub(crate) parents: Vec<u32>,
    /// The position after the last node of the subtree of each node.
    pub(crate) ends: Vec<u32>,
    /// `IN_ERROR`, `IN_TYPE` and `IN_FUNCTION` of each node.
    pub(crate) flags: Vec<u8>,
}

impl<'t> Layout<'t> {
    /// Enter a node whose parent was recorded at `parent` (`NONE` for the root, or for a parent
    /// that was not recorded). Only a named node of a recorded parent is recorded. Returns the
    /// position of the node, or `NONE`; hand it to `leave`.
    pub fn enter(&mut self, cx: &Cx, node: Node<'t>, named: bool, parent: Option<u32>) -> u32 {
        let up = match parent {
            Some(NONE) => return NONE,
            Some(at) => at,
            None => NONE,
        };
        if !named {
            return NONE;
        }
        let at = u32::try_from(self.nodes.len()).unwrap_or(NONE);
        let flags = self.flags_below(cx, node, up);
        self.position.insert(node.id(), self.nodes.len());
        self.nodes.push(node);
        self.parents.push(up);
        self.ends.push(0);
        self.flags.push(flags);
        at
    }

    /// The node at `at` is left: its subtree ends here.
    pub fn leave(&mut self, at: u32) {
        let end = u32::try_from(self.nodes.len()).unwrap_or(NONE);
        if let Some(slot) = self.ends.get_mut(at as usize) {
            *slot = end;
        }
    }

    /// The flags that a node has when its parent is recorded at `up`: those of the parent, and
    /// what the parent adds for its children. A parent comes before its children, so its flags
    /// are known.
    fn flags_below(&self, cx: &Cx, node: Node<'t>, up: u32) -> u8 {
        let (Some(parent), Some(own)) = (
            self.nodes.get(up as usize).filter(|_| up != NONE),
            self.flags.get(up as usize),
        ) else {
            return 0;
        };
        let kind = cx.k(*parent);
        let mut flags = *own;
        if parent.is_error() {
            flags |= IN_ERROR;
        }
        let cast = matches!(kind, K::AsExpression | K::SatisfiesExpression);
        if is_type_parent(kind) || (cast && node.start_byte() > parent.start_byte()) {
            flags |= IN_TYPE;
        }
        if is_function_like(kind) {
            flags |= IN_FUNCTION;
        }
        flags
    }

    /// Leave the nodes that are done and move the cursor to the next node; `false` at the end.
    fn next_node(&mut self, cursor: &mut TreeCursor<'t>, open: &mut Vec<u32>) -> bool {
        loop {
            self.leave(open.pop().unwrap_or(NONE));
            if cursor.goto_next_sibling() {
                return true;
            }
            if !cursor.goto_parent() {
                return false;
            }
        }
    }

    /// The layout of a tree that no walk has visited: one pass with a cursor, so a tree that is
    /// nested 30 000 levels deep does not overflow the call stack.
    pub fn of(cx: &Cx, root: Node<'t>) -> Self {
        let mut layout = Self::default();
        let mut open: Vec<u32> = Vec::new();
        let mut cursor: TreeCursor<'t> = root.walk();
        loop {
            let node = cursor.node();
            let parent = open.last().copied();
            open.push(layout.enter(cx, node, cx.kinds.info(node).named, parent));
            if cursor.goto_first_child() {
                continue;
            }
            if !layout.next_node(&mut cursor, &mut open) {
                return layout;
            }
        }
    }
}

#[cfg(test)]
#[path = "layout_tests.rs"]
mod tests;
