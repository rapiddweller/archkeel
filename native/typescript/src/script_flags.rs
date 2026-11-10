// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The flags of the nodes of a file, and the chains that one pass answers for all of them.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::{is_function_like, Tree, IN_ERROR, IN_FUNCTION, IN_TYPE, NONE};

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

impl<'a, 't> Tree<'a, 't> {
    /// The flags of the nodes that hold for a node when they hold for its parent: each is read
    /// from the parent, so the file costs one pass and not the depth for each question. A parent
    /// comes before its children in the document order, so its flags are known.
    pub(crate) fn with_flags(mut self) -> Self {
        let mut flags: Vec<u8> = Vec::with_capacity(self.nodes.len());
        for (node, above) in self.nodes.iter().zip(self.parents.iter()) {
            let parent = self.nodes.get(*above as usize);
            let Some(parent) = parent.filter(|_| *above != NONE) else {
                flags.push(0);
                continue;
            };
            let up = flags.get(*above as usize).copied().unwrap_or(0);
            let kind = self.k(*parent);
            let mut own = up;
            if parent.is_error() {
                own |= IN_ERROR;
            }
            let cast = matches!(kind, K::AsExpression | K::SatisfiesExpression);
            if is_type_parent(kind) || (cast && node.start_byte() > parent.start_byte()) {
                own |= IN_TYPE;
            }
            if is_function_like(self.k(*parent)) {
                own |= IN_FUNCTION;
            }
            flags.push(own);
        }
        self.flags = flags;
        self
    }

    /// For each position, the position of the nearest node above it that `pick` accepts, or `NONE`. A parent comes before its
    /// children in the document order, so the answer of a node is read from its parent.
    pub fn nearest_above(&self, pick: impl Fn(Node<'t>) -> bool) -> Vec<u32> {
        let mut found: Vec<u32> = Vec::with_capacity(self.nodes.len());
        for above in &self.parents {
            let parent = self.nodes.get(*above as usize).filter(|_| *above != NONE);
            let answer = match parent {
                Some(parent) if pick(*parent) => *above,
                Some(_) => found.get(*above as usize).copied().unwrap_or(NONE),
                None => NONE,
            };
            found.push(answer);
        }
        found
    }

    /// The node is, through members, subscripts and parentheses, the function of a call or the
    /// constructor of a `new`. The answer of a node is the answer of the node above it, so the
    /// answers of a chain of n subscripts cost n and not n squared.
    pub fn leads_to_call(&self, node: Node<'t>) -> bool {
        let mut memo = self.memo.borrow_mut();
        if memo.calls.len() != self.nodes.len() {
            memo.calls = vec![0; self.nodes.len()];
        }
        let mut chain: Vec<usize> = Vec::new();
        let mut current = node;
        let answer = loop {
            let Some(at) = self.pos(current) else {
                break false;
            };
            match memo.calls.get(at) {
                Some(1) => break false,
                Some(2) => break true,
                _ => {}
            }
            chain.push(at);
            let Some(parent) = self.parent(current) else {
                break false;
            };
            let kind = self.k(parent);
            let carries = (matches!(kind, K::MemberExpression | K::SubscriptExpression)
                && self.is_field_of_parent(current, F::Object))
                || kind == K::ParenthesizedExpression;
            if !carries {
                let called = self.is_field_of_parent(current, F::Function)
                    || self.is_field_of_parent(current, F::Constructor);
                break matches!(kind, K::CallExpression | K::NewExpression) && called;
            }
            current = parent;
        };
        let mark: u8 = if answer { 2 } else { 1 };
        for at in chain {
            if let Some(slot) = memo.calls.get_mut(at) {
                *slot = mark;
            }
        }
        answer
    }

    /// Whether a flag holds for the node.
    pub(crate) fn flag(&self, node: Node, bit: u8) -> bool {
        let at = self.pos(node);
        at.and_then(|at| self.flags.get(at))
            .is_some_and(|flags| flags & bit != 0)
    }
}
