// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The references of a file, found once (`_script_alias_calls`, `_script_factory_uses` and
//! `_script_factory_publication_escape` read them).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::K;
use crate::script_scope::{is_function, is_root, Tree};

/// The references of a file, found once: the identifiers by name, and where an identifier makes
/// the aliases of its scope unprovable.
#[derive(Default)]
pub struct References<'t> {
    by_name: HashMap<String, Vec<(usize, Node<'t>)>>,
    /// The positions of the identifiers that hold an escape or a repair.
    bad: Vec<usize>,
    /// The paths that an assignment writes, without the root of the global object.
    pub(crate) routes: Vec<Vec<String>>,
    /// The return statements of each function, by the id of the function.
    pub(crate) returns: HashMap<usize, Vec<Node<'t>>>,
}

impl<'t> References<'t> {
    pub fn new(tree: &Tree<'_, 't>, targets: &[(Node<'t>, Node<'t>)]) -> Self {
        let mut found = Self::default();
        for (at, node) in tree.nodes.iter().copied().enumerate() {
            match tree.k(node) {
                K::Identifier | K::ShorthandPropertyIdentifier => found.name(tree, at, node),
                K::ReturnStatement => found.returned(tree, node),
                _ => {}
            }
        }
        found.routes = targets
            .iter()
            .map(|(_, target)| route(tree, *target))
            .collect();
        found
    }

    /// An identifier: found by its name, and bad where it has an escape or a repair.
    fn name(&mut self, tree: &Tree<'_, 't>, at: usize, node: Node<'t>) {
        self.by_name
            .entry(tree.text(node))
            .or_default()
            .push((at, node));
        if !tree.cx.valid_unicode_member_name(node) || tree.in_error(node) {
            self.bad.push(at);
        }
    }

    /// A return statement belongs to the function above it.
    fn returned(&mut self, tree: &Tree<'_, 't>, node: Node<'t>) {
        let owner = tree
            .ancestors(node)
            .find(|parent| is_function(tree.k(*parent)));
        if let Some(owner) = owner {
            self.returns.entry(owner.id()).or_default().push(node);
        }
    }

    /// Whether an identifier in the range holds an escape or a repair.
    pub fn any_bad(&self, range: (usize, usize)) -> bool {
        let first = self.bad.partition_point(|at| *at < range.0);
        self.bad.get(first).is_some_and(|at| *at < range.1)
    }

    /// The references to `name` inside the range, in document order.
    pub fn named(&self, name: &str, range: (usize, usize)) -> impl Iterator<Item = Node<'t>> + '_ {
        let list: &[(usize, Node<'t>)] = self.by_name.get(name).map_or(&[], Vec::as_slice);
        let first = list.partition_point(|(at, _)| *at < range.0);
        list.iter()
            .skip(first)
            .take_while(move |(at, _)| *at < range.1)
            .map(|(_, node)| *node)
    }
}

/// The path that an assignment target writes, without the root of the global object.
fn route<'t>(tree: &Tree<'_, 't>, target: Node<'t>) -> Vec<String> {
    let route = tree.static_path(target);
    match route.first() {
        Some(first) if is_root(first) => route.iter().skip(1).cloned().collect(),
        _ => route,
    }
}
