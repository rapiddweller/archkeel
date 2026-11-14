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
use crate::scope::assignment_targets;
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
    /// `_static_path`: the names of `a`, `a.b` and `a.b.c`; empty for any other node.
    pub(crate) fn static_path(&self, node: Node<'t>) -> Vec<String> {
        // The members of the chain, outermost first; the base decides the rest.
        let mut names: Vec<String> = Vec::new();
        let mut at = node;
        loop {
            match self.k(at) {
                K::Identifier
                | K::PropertyIdentifier
                | K::ShorthandPropertyIdentifier
                | K::ShorthandPropertyIdentifierPattern => return self.base(names, at),
                K::MemberExpression => match self.member(at, &mut names) {
                    Some(receiver) => at = receiver,
                    None => return Vec::new(),
                },
                _ => return Vec::new(),
            }
        }
    }

    /// The path of a chain that ends at the name `at`.
    fn base(&self, mut names: Vec<String>, at: Node<'t>) -> Vec<String> {
        names.push(self.text(at));
        names.reverse();
        names
    }

    /// One member of a chain: its name is kept, and its receiver is the next node to read.
    fn member(&self, at: Node<'t>, names: &mut Vec<String>) -> Option<Node<'t>> {
        let receiver = self.field(at, F::Object)?;
        let name = self.field(at, F::Property)?;
        if self.k(name) != K::PropertyIdentifier {
            return None;
        }
        names.push(self.text(name));
        Some(receiver)
    }

    pub(crate) fn in_ambiguous_scope(&self, node: Node<'t>) -> bool {
        self.parent(node)
            .is_some_and(|parent| self.flag(parent, IN_AMBIGUOUS))
    }

    /// The scope that binds `name` at `node`: the readers of a write ask the scope module.
    pub(crate) fn binding_scope(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        self.bound_scope(node, name)
    }

    /// The scope that binds `name` at `node` exactly once.
    pub(crate) fn sole_binding_scope(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        self.bound_scope(node, name)
            .filter(|scope| self.count(*scope, name) == 1)
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
        !blocked_here && self.bound_scope(node, first).is_none()
    }

    /// `_declaration_name`.
    pub(crate) fn declaration_name(&self, node: Node<'t>) -> bool {
        let Some(parent) = self.parent(node) else {
            return false;
        };
        [F::Name, F::Pattern, F::Alias].into_iter().any(|field| {
            self.field(parent, field)
                .is_some_and(|found| found.id() == node.id())
        }) || self.k(parent) == K::NamespaceExport
            || (self.k(parent) == K::PairPattern
                && self
                    .field(parent, F::Key)
                    .is_some_and(|key| key.id() == node.id()))
    }

    /// `_script_assignment_targets`.
    pub(crate) fn script_targets(&self, node: Node<'t>) -> Vec<Node<'t>> {
        let kind = self.k(node);
        let left = match kind {
            K::AssignmentExpression | K::AugmentedAssignmentExpression | K::ForInStatement => {
                self.field(node, F::Left)
            }
            K::UpdateExpression => self.field(node, F::Argument),
            K::UnaryExpression if self.has_child_kind(node, K::Delete) => {
                self.field(node, F::Argument)
            }
            _ => None,
        };
        left.map_or_else(Vec::new, |pattern| assignment_targets(&self.cx, pattern))
    }
}
