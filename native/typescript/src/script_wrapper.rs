// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The wrappers of a script: a function that the script calls once at its top level
//! (`_script_wrapper`).

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::{is_root, Tree, Wrapper};
use crate::tree::nodes::named_children;

impl<'a, 't> Tree<'a, 't> {
    /// The object literal that a body returns, when one of its statements is the only `return` and
    /// returns just that object: the statement and the object.
    pub fn only_returned_object(&self, body: Node<'t>) -> Option<(Node<'t>, Node<'t>)> {
        let mut returns = named_children(body)
            .into_iter()
            .filter(|item| self.k(*item) == K::ReturnStatement);
        let only = returns.next().filter(|_| returns.next().is_none())?;
        let value = only
            .named_child(0)
            .filter(|_| only.named_child_count() == 1)?;
        (self.k(value) == K::Object).then_some((only, value))
    }

    /// Whether `_script_wrapper` finds a wrapper, without a copy of the names that it gives.
    pub fn is_wrapper(&self, node: Node<'t>) -> bool {
        if !matches!(self.k(node), K::FunctionExpression | K::ArrowFunction) {
            return false;
        }
        let known = self
            .memo
            .borrow()
            .wrappers
            .get(&node.id())
            .map(Option::is_some);
        known.unwrap_or_else(|| self.wrapper(node).is_some())
    }

    /// `_script_wrapper`: only a direct, synchronous function that the script calls once.
    pub fn wrapper(&self, node: Node<'t>) -> Option<Wrapper<'t>> {
        if !matches!(self.k(node), K::FunctionExpression | K::ArrowFunction) {
            return None;
        }
        if let Some(known) = self.memo.borrow().wrappers.get(&node.id()) {
            return known.clone();
        }
        let found = self.find_wrapper(node);
        self.memo
            .borrow_mut()
            .wrappers
            .insert(node.id(), found.clone());
        found
    }

    /// `_script_wrapper`, read from the tree.
    fn find_wrapper(&self, node: Node<'t>) -> Option<Wrapper<'t>> {
        if !matches!(self.k(node), K::FunctionExpression | K::ArrowFunction)
            || self.has_child_kind(node, K::Async)
        {
            return None;
        }
        let mut callee = node;
        while let Some(parent) = self.parent(callee) {
            if self.k(parent) != K::ParenthesizedExpression {
                break;
            }
            callee = parent;
        }
        let call = self.parent(callee)?;
        let called = self.field(call, F::Function);
        if self.k(call) != K::CallExpression || called.is_none_or(|f| f.id() != callee.id()) {
            return None;
        }
        let mut statement = self.parent(call)?;
        if self.k(statement) == K::VariableDeclarator {
            statement = self.parent(statement)?;
        }
        let top = matches!(
            self.k(statement),
            K::ExpressionStatement | K::VariableDeclaration | K::LexicalDeclaration
        ) && self
            .parent(statement)
            .is_some_and(|parent| self.k(parent) == K::Program);
        if !top {
            return None;
        }
        let (parameters, arguments) = (
            self.field(node, F::Parameters),
            self.field(call, F::Arguments),
        );
        let count = |list: Option<Node>| list.map_or(0, |list| list.named_child_count());
        if count(parameters) != count(arguments) {
            return None;
        }
        let params = parameters.map_or_else(Vec::new, named_children);
        let args = arguments.map_or_else(Vec::new, named_children);
        let mut aliases = Vec::new();
        for (param, arg) in params.iter().zip(args.iter()) {
            let pattern = self.field(*param, F::Pattern);
            let proven = self.k(*arg) == K::Identifier
                && is_root(&self.text(*arg))
                && self.k(*param) == K::RequiredParameter
                && pattern.is_some_and(|pattern| self.k(pattern) == K::Identifier);
            if !proven {
                return None;
            }
            if let Some(pattern) = pattern {
                aliases.push(self.text(pattern));
            }
        }
        let names = aliases.iter().cloned().collect();
        Some(Wrapper {
            call,
            aliases,
            names,
        })
    }
}
