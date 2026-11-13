// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declarations and the writes of each name of a file, by the scope that binds it, found once
//! (`_script_local_definition` and `_script_write_alias_path` read them).

use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::Tree;

/// A declaration of a name, by the scope that binds it: `(scope id, name)`.
pub(crate) type Key = (usize, String);

#[derive(Default)]
pub(crate) struct DeclIndex<'t> {
    /// The function declarations and the declarators that bind a name in a scope, in order.
    pub(crate) declared: HashMap<Key, Vec<Node<'t>>>,
    /// The declarators with a plain name, by the scope that binds it.
    pub(crate) variables: HashMap<Key, Vec<Node<'t>>>,
    /// The names that an assignment writes in the scope that binds them.
    pub(crate) written: HashSet<Key>,
}

impl<'t> DeclIndex<'t> {
    pub(crate) fn new(tree: &Tree<'_, 't>, targets: &[(Node<'t>, Node<'t>)]) -> Self {
        let mut found = Self::default();
        for node in tree.nodes.iter().copied() {
            found.declare(tree, node);
        }
        for (_, target) in targets {
            found.write(tree, *target);
        }
        found
    }

    /// A function declaration or a declarator: its name is bound in the scope that binds it.
    fn declare(&mut self, tree: &Tree<'_, 't>, node: Node<'t>) {
        let kind = tree.k(node);
        if !matches!(kind, K::FunctionDeclaration | K::VariableDeclarator) {
            return;
        }
        let Some(name) = tree.field(node, F::Name) else {
            return;
        };
        let spelling = tree.text(name);
        if let Some(scope) = tree.bound_scope(node, &spelling) {
            let key = (scope.id(), spelling.clone());
            self.declared.entry(key).or_default().push(node);
        }
        if kind != K::VariableDeclarator || tree.k(name) != K::Identifier {
            return;
        }
        if let Some(scope) = tree.bound_scope(name, &spelling) {
            let key = (scope.id(), spelling);
            self.variables.entry(key).or_default().push(node);
        }
    }

    /// An assignment to a plain name writes it in the scope that binds it.
    fn write(&mut self, tree: &Tree<'_, 't>, target: Node<'t>) {
        let path = tree.static_path(target);
        let [name] = path.as_slice() else {
            return;
        };
        if let Some(scope) = tree.bound_scope(target, name) {
            self.written.insert((scope.id(), name.clone()));
        }
    }
}
