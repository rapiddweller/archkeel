// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The CPython shape of the ruff tree: the class name of each node and `ast.iter_child_nodes` in
//! the order of `_fields` of the interpreter in the request, and `ast.walk` (AD-377).
//!
//! The Python collector reads its tree with `ast.walk` and `ast.iter_child_nodes`, and the order
//! of a walk decides the order of some lists in its records. Ruff has a different shape: an `elif`
//! is a clause and not an `If` in `orelse`, a decorator wraps its expression, an f-string has
//! parts and not the merged `Constant` values of a `JoinedStr`, and a context or an operator is a
//! field and not a node. `Node` hides these differences. A walk has no recursion.

use std::collections::VecDeque;

mod children;
pub(crate) mod fstring;
mod node;

pub(crate) use children::child_nodes;
pub(crate) use fstring::Piece;
pub(crate) use node::{bool_op, cmp_op, operator, unary_op, Node};

/// `ast.walk`: the nodes in breadth-first order, the root first.
pub(crate) fn walk<'a>(root: Node<'a>, minor: archkeel_facts::pyminor::PyMinor) -> Walk<'a> {
    Walk {
        pending: VecDeque::from([root]),
        minor,
    }
}

pub(crate) struct Walk<'a> {
    pending: VecDeque<Node<'a>>,
    minor: archkeel_facts::pyminor::PyMinor,
}

impl<'a> Iterator for Walk<'a> {
    type Item = Node<'a>;

    fn next(&mut self) -> Option<Node<'a>> {
        let node = self.pending.pop_front()?;
        self.pending.extend(child_nodes(&node, self.minor));
        Some(node)
    }
}

#[cfg(test)]
#[path = "pyast_tests.rs"]
mod tests;
