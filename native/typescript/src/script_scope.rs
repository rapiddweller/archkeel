// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree of one file as the script facts read it (AD-340, PR 4.3a-4): the named nodes in
//! document order, the bindings of each scope (`_script_bindings`), the immediately called
//! wrappers of a script (`_script_wrapper`) and the questions that the producers of
//! `script_syntax.rs`, `script_writes.rs` and `script_alias.rs` ask again and again.
//!
//! Python answers these by climbing the parents and by walking a subtree for each question. Here
//! a subtree is a range of the document order, and a name is looked up in an index.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::layout::IN_AMBIGUOUS;
use crate::script_names::bound_scope;
use crate::script_tree::Tree;

/// `_SCRIPT_ROOTS`: the names of the browser global object.
pub(crate) fn is_root(name: &str) -> bool {
    crate::source_input::is_script_root(name.as_bytes())
}

/// `_SCRIPT_FUNCTIONS`.
pub(crate) fn is_function(kind: K) -> bool {
    matches!(
        kind,
        K::FunctionDeclaration
            | K::FunctionExpression
            | K::GeneratorFunctionDeclaration
            | K::GeneratorFunction
            | K::ArrowFunction
            | K::MethodDefinition
    )
}

/// `_SCRIPT_VAR_SCOPES`.
pub(crate) fn is_var_scope(kind: K) -> bool {
    is_function(kind) || matches!(kind, K::Program | K::ClassStaticBlock)
}

/// `_SCRIPT_SCOPES`.
pub(crate) fn is_scope(kind: K) -> bool {
    is_var_scope(kind)
        || matches!(
            kind,
            K::StatementBlock
                | K::CatchClause
                | K::ForInStatement
                | K::ForStatement
                | K::SwitchBody
                | K::Class
                | K::ClassDeclaration
                | K::ClassBody
        )
}

/// `_SCRIPT_RECEIVER_SCOPES`.
pub(crate) fn is_receiver_scope(kind: K) -> bool {
    (is_function(kind) && kind != K::ArrowFunction) || kind == K::ClassStaticBlock
}

/// `_SCRIPT_CALLABLE_VALUES`.
pub(crate) fn is_callable_value(kind: K) -> bool {
    is_function(kind) || matches!(kind, K::Class | K::ClassDeclaration)
}

impl<'a, 't> Tree<'a, 't> {
    pub(crate) fn in_ambiguous_scope(&self, node: Node<'t>) -> bool {
        self.parent(node)
            .is_some_and(|parent| self.flag(parent, IN_AMBIGUOUS))
    }

    /// `_script_free`: the root of the path of `target` is not bound by a scope above `node`.
    pub(crate) fn script_free(&self, target: Node<'t>, node: Node<'t>) -> bool {
        self.script_free_in(target, node, true)
    }

    /// `_script_free`, with or without the scopes that are not statically known (`ambiguous`).
    pub(crate) fn script_free_in(&self, target: Node<'t>, node: Node<'t>, ambiguous: bool) -> bool {
        if self.in_type(node) {
            return false;
        }
        let path = self.static_path(target);
        if let Some(parent) = self.parent(target) {
            if self.k(parent) == K::Pair && self.is_field_of_parent(target, F::Key) {
                return false;
            }
        }
        let Some(first) = path.first() else {
            return false;
        };
        let blocked_here = ambiguous && self.in_ambiguous_scope(node);
        !blocked_here && bound_scope(self, node, first).is_none()
    }
}

/// The scope that binds `name` at `node` exactly once.
pub(crate) fn sole_binding_scope<'t>(
    tree: &Tree<'_, 't>,
    node: Node<'t>,
    name: &str,
) -> Option<Node<'t>> {
    bound_scope(tree, node, name).filter(|scope| tree.count(*scope, name) == 1)
}
