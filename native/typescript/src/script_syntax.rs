// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state that the producers of the script facts share, and the writes and publications of a
//! script (`_script_globals`).

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::definitions::{Definition, Scopes};
use crate::kinds::{F, K};
use crate::script_index::DeclIndex;
use crate::script_refs::References;
use crate::script_scope::{is_function_like, is_receiver_scope, is_root, Tree, Wrapper, NONE};
use crate::script_types::{ScriptGlobal, Write};
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
    /// The declarations of literals that a use can change or hand on (AD-500), built on first use.
    pub(crate) data_taint: std::cell::OnceCell<HashSet<usize>>,
}

/// The writes and publications that `_script_globals` finds while it reads the nodes in order.
#[derive(Default)]
struct Found {
    publications: Vec<ScriptGlobal>,
    writes: Vec<Write>,
    /// Each `this` with the span of the function or class that it belongs to.
    receivers: Vec<(Option<Span>, Span)>,
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
            wrappers,
            data_taint: std::cell::OnceCell::new(),
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

    /// What the node adds to the writes and publications of the file.
    fn visit(&self, node: Node<'t>, roots: &HashSet<&str>, found: &mut Found) {
        let tree = self.tree;
        let kind = tree.k(node);
        let opaque = tree.opaque_writes(node, &self.callables);
        found
            .writes
            .extend(opaque.into_iter().map(|span| (None, span)));
        if kind == K::This {
            let owner = tree
                .ancestors(node)
                .find(|ancestor| is_receiver_scope(tree.k(*ancestor)));
            found
                .receivers
                .push((owner.map(|owner| tree.span(owner)), tree.span(node)));
            if tree.script_escape(node) {
                found.writes.push((None, tree.span(node)));
            }
        }
        let name = matches!(kind, K::Identifier | K::ShorthandPropertyIdentifier)
            && roots.contains(tree.text(node).as_str());
        if name && !tree.declaration_name(node) && tree.script_escape(node) {
            found.writes.push((None, tree.span(node)));
        }
        if !self.module_syntax {
            found.writes.extend(tree.declaration_write(node));
        }
    }

    /// The assignment that `node` makes to `target`: a write, and maybe a publication.
    fn assign(&self, node: Node<'t>, target: Node<'t>, found: &mut Found) {
        let tree = self.tree;
        let wrapper = self.wrapper_of(node);
        let alias = |name: &str| self.is_alias(wrapper, name);
        found.writes.push(tree.target_write(node, target, &alias));
        let path = tree.static_path(target);
        if path.first().is_some_and(|first| alias(first)) {
            let published = self.assignment_publication(node, target, wrapper);
            found.publications.extend(published);
        }
    }

    /// `_script_globals`: the publications of the file and the writes that a script may make.
    pub(crate) fn globals(&self) -> (Vec<ScriptGlobal>, Vec<Write>) {
        let tree = self.tree;
        let mut found = Found::default();
        let wrapper_calls: HashSet<usize> = self.wrappers.values().map(|w| w.call.id()).collect();
        let mut roots: HashSet<&str> = crate::source_input::WALK_ROOTS.into_iter().collect();
        roots.extend(
            self.wrappers
                .values()
                .flat_map(|w| w.aliases.iter())
                .map(String::as_str),
        );
        let mut targets = self.targets.iter().peekable();
        for node in tree.nodes.iter().copied() {
            self.visit(node, &roots, &mut found);
            while let Some((_, target)) = targets.next_if(|(owner, _)| owner.id() == node.id()) {
                self.assign(node, *target, &mut found);
            }
            found.writes.extend(tree.call_writes(node, &wrapper_calls));
            let call = self.wrappers.get(&node.id()).map(|info| info.call);
            let returned = call.and_then(|call| self.return_publication(node, call));
            if let Some(publication) = returned {
                found
                    .writes
                    .push((Some(publication.name.clone()), publication.span.clone()));
                found.publications.push(publication);
            }
        }
        let published: HashSet<&Span> = found
            .publications
            .iter()
            .flat_map(|item| item.members.iter().map(|(_, _, span)| span))
            .collect();
        let open = |owner: &Option<Span>| owner.as_ref().is_none_or(|o| published.contains(o));
        let writes = found
            .receivers
            .iter()
            .filter(|(owner, _)| open(owner))
            .map(|(_, span)| (None, span.clone()))
            .collect::<Vec<_>>();
        found.writes.extend(writes);
        (found.publications, unique(found.writes))
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
