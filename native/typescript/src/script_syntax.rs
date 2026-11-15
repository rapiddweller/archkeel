// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state that the producers of the script facts share.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::definitions::{Definition, Scopes};
use crate::kinds::{F, K};
use crate::layout::{is_function_like, NONE};
use crate::script_index::DeclIndex;
use crate::script_refs::References;
use crate::script_scope::is_root;
use crate::script_tree::{Tree, Wrapper};
use crate::source::Span;
use crate::tree::nodes::named_children;
use crate::umd::Templates;

/// What the producers read, built once for a file.
pub(crate) struct Producer<'x, 'a, 't> {
    pub tree: &'x Tree<'a, 't>,
    pub wrappers: HashMap<usize, Wrapper<'t>>,
    pub callables: HashSet<(usize, String)>,
    /// Each node with each of the targets that it assigns, in document order.
    pub targets: Vec<(Node<'t>, Node<'t>)>,
    pub scopes: &'x Scopes,
    pub module_syntax: bool,
    pub templates: &'x Templates,
    pub index: DeclIndex<'t>,
    pub refs: References<'t>,
    /// The definitions by the span where they start.
    by_span: HashMap<&'x Span, Vec<&'x Definition>>,
    /// The function declarations of a body by name (`functions_named`), by the id of the body.
    bodies: RefCell<HashMap<usize, HashMap<String, Vec<Node<'t>>>>>,
    /// The return statements of each wrapper, by the id of the wrapper function.
    returns: HashMap<usize, Vec<Node<'t>>>,
    /// Whether the arguments of the call of each wrapper are free names, by the id of the wrapper.
    pub(crate) free_arguments: RefCell<HashMap<usize, bool>>,
    /// The nearest wrapper above each node, by the position of the node.
    wrapper_above: Vec<u32>,
    /// The names that were proved numeric (AD-535), by scope and name.
    pub(crate) numeric: crate::script_host::NumericNames,
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The definitions that start at a span, in order.
    pub(crate) fn definitions_at(&self, span: &Span) -> &[&'x Definition] {
        self.by_span.get(span).map_or(&[], Vec::as_slice)
    }

    pub(crate) fn new(
        tree: &'x Tree<'a, 't>,
        definitions: &'x [Definition],
        scopes: &'x Scopes,
        module_syntax: bool,
        templates: &'x Templates,
    ) -> Self {
        let wrappers: HashMap<usize, Wrapper<'t>> = tree
            .nodes
            .iter()
            .filter_map(|node| tree.wrapper(*node).map(|info| (node.id(), info)))
            .collect();
        let targets: Vec<(Node<'t>, Node<'t>)> = tree
            .nodes
            .iter()
            .flat_map(|node| tree.script_targets(*node).into_iter().map(|t| (*node, t)))
            .collect();
        let mut by_span: HashMap<&Span, Vec<&Definition>> = HashMap::new();
        for definition in definitions {
            by_span
                .entry(&definition.span)
                .or_default()
                .push(definition);
        }
        Self {
            tree,
            callables: tree.callable_bindings(),
            index: DeclIndex::new(tree, &targets),
            refs: References::new(tree, &targets),
            returns: wrapper_returns(tree, &wrappers),
            free_arguments: RefCell::new(HashMap::new()),
            wrapper_above: tree.nearest_above(|node| wrappers.contains_key(&node.id())),
            numeric: Default::default(),
            wrappers,
            by_span,
            bodies: RefCell::new(HashMap::new()),
            targets,
            scopes,
            module_syntax,
            templates,
        }
    }

    /// What `make` finds at each node of the file, in document order.
    pub(crate) fn collect_nodes<T>(&self, make: impl Fn(Node<'t>) -> Option<T>) -> Vec<T> {
        self.tree.nodes.iter().copied().filter_map(make).collect()
    }

    /// The nearest wrapper function above `node`.
    pub(crate) fn wrapper_of(&self, node: Node<'t>) -> Option<Node<'t>> {
        let at = self.tree.at(node);
        let above = self.wrapper_above.get(at).copied()?;
        (above != NONE)
            .then(|| self.tree.nodes.get(above as usize).copied())
            .flatten()
    }

    /// Whether a name is an alias of the global object for a node: a root, or a name that the
    /// wrapper above the node gives to a root.
    pub(crate) fn is_alias(&self, wrapper: Option<Node<'t>>, name: &str) -> bool {
        let info = wrapper.and_then(|node| self.wrappers.get(&node.id()));
        is_root(name) || info.is_some_and(|info| info.names.contains(name))
    }

    /// The function declarations among the statements of `body` that have the name, in order. The
    /// statements of a body are read once for all the objects that the body publishes.
    pub(crate) fn functions_named(&self, body: Node<'t>, name: &str) -> Vec<Node<'t>> {
        let mut cache = self.bodies.borrow_mut();
        let known = cache
            .entry(body.id())
            .or_insert_with(|| functions_by_name(self.tree, body));
        known.get(name).cloned().unwrap_or_default()
    }

    /// `_script_prior_returns`: the statements with a `return` before `node` in the wrapper.
    pub(crate) fn prior_returns(&self, node: Node<'t>, wrapper: Option<Node<'t>>) -> Vec<Node<'t>> {
        let Some(wrapper) = wrapper else {
            return Vec::new();
        };
        if self.tree.field(wrapper, F::Body).is_none() {
            return vec![node];
        }
        let list = self.returns.get(&wrapper.id());
        let before = |item: &&Node<'t>| item.start_byte() < node.start_byte();
        let statement = |item: &Node<'t>| self.tree.parent(*item).unwrap_or(*item);
        list.map_or_else(Vec::new, |list| {
            list.iter().filter(before).map(statement).collect()
        })
    }

    /// `_script_reaches`: no `return` comes before the node.
    pub(crate) fn reaches(&self, node: Node<'t>, wrapper: Option<Node<'t>>) -> bool {
        self.prior_returns(node, wrapper).is_empty()
    }
}

/// The return statements of each wrapper, by the id of the wrapper function.
fn wrapper_returns<'t>(
    tree: &Tree<'_, 't>,
    wrappers: &HashMap<usize, Wrapper<'t>>,
) -> HashMap<usize, Vec<Node<'t>>> {
    let mut returns: HashMap<usize, Vec<Node<'t>>> = HashMap::new();
    for node in tree.nodes.iter().copied() {
        if tree.k(node) != K::ReturnStatement {
            continue;
        }
        let owner = tree
            .ancestors(node)
            .find(|parent| is_function_like(tree.k(*parent)));
        if let Some(owner) = owner.filter(|owner| wrappers.contains_key(&owner.id())) {
            returns.entry(owner.id()).or_default().push(node);
        }
    }
    returns
}

/// The function declarations among the statements of `body`, by name, in order.
fn functions_by_name<'t>(tree: &Tree<'_, 't>, body: Node<'t>) -> HashMap<String, Vec<Node<'t>>> {
    let mut by_name: HashMap<String, Vec<Node<'t>>> = HashMap::new();
    for statement in named_children(body) {
        if tree.k(statement) != K::FunctionDeclaration {
            continue;
        }
        let name = tree.field(statement, F::Name).map(|found| tree.text(found));
        if let Some(name) = name {
            by_name.entry(name).or_default().push(statement);
        }
    }
    by_name
}

/// `dict.fromkeys(items)`: each item once, in the order of its first appearance.
pub(crate) fn unique<T: std::hash::Hash + Eq + Clone>(items: Vec<T>) -> Vec<T> {
    let mut seen = HashSet::new();
    items
        .into_iter()
        .filter(|item| seen.insert(item.clone()))
        .collect()
}
