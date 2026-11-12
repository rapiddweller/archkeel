// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scopes and the callables of `analyzer/dart/parse.py`: the scope list of `_sites`,
//! `_scope_name`, `_callable_decl_name`, `_callable_body`, `_callable_name` and
//! `_callable_context_for`.

use std::cmp::Reverse;
use std::collections::HashMap;

use tree_sitter::Node;

use super::contain::Sweep;
use crate::syntax::Context;
use crate::tree::{children, named, named_children, walk_with_path, Gap, Source, Work};

pub(crate) const SCOPE_KINDS: [&str; 3] = ["function_body", "function_expression_body", "block"];
const BODIES: [&str; 2] = ["function_body", "function_expression_body"];
const DECLARED: [&str; 2] = ["function_signature", "method_signature"];
const BODY_STOPS: [&str; 3] = [
    "function_signature",
    "method_signature",
    "function_expression",
];
pub(crate) const CONSTRUCTORS: [&str; 4] = [
    "constructor_signature",
    "constant_constructor_signature",
    "factory_constructor_signature",
    "redirecting_factory_constructor_signature",
];
const NAMED_CALLABLES: [&str; 7] = [
    "function_signature",
    "method_signature",
    "method_declaration",
    "function_declaration",
    "getter_signature",
    "setter_signature",
    "function_expression",
];

/// The fold of the scopes that contain a node: their count and the scope with the highest start,
/// the first one in walk order on a tie, as Python `max` keeps it.
pub(crate) type Active = (usize, Option<(usize, Reverse<usize>)>);

fn join_active(a: Active, b: Active) -> Active {
    (a.0.saturating_add(b.0), a.1.max(b.1))
}

fn join_count(a: usize, b: usize) -> usize {
    a.saturating_add(b)
}

/// The smallest callable body, the first one in walk order on a tie, as Python `min` keeps it.
fn join_smallest(a: Option<(usize, usize)>, b: Option<(usize, usize)>) -> Option<(usize, usize)> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, None) => a,
        (None, b) => b,
    }
}

/// One entry of the `scopes` tuple of `_sites`.
pub(crate) struct Scope<'t> {
    pub(crate) node: Node<'t>,
    pub(crate) name: Option<String>,
    /// The number of scopes that contain this scope, itself included.
    depth: usize,
}

/// The scopes of one tree, in walk order.
pub(crate) struct Scopes<'t> {
    pub(crate) list: Vec<Scope<'t>>,
    index: HashMap<usize, usize>,
    active: Sweep<Active>,
    /// `_callable_context_for` of each callable node: the result depends only on the node, and
    /// the fallback of `_callable_context` asks for the same node once for each node after it.
    contexts: HashMap<usize, Context>,
}

impl<'t> Scopes<'t> {
    /// The scopes of `root`: two walks and two sweeps, in place of the pairwise loops of Python.
    pub(crate) fn new(root: Node<'t>, source: &Source<'_>, work: &Work<'t>) -> Result<Self, Gap> {
        let mut callables: Vec<(Node<'t>, String)> = Vec::new();
        let mut nodes: Vec<Node<'t>> = Vec::new();
        walk_with_path(root, |node, path| {
            work.charge(1);
            if SCOPE_KINDS.contains(&node.kind()) {
                nodes.push(node);
            }
            if !DECLARED.contains(&node.kind()) {
                return true;
            }
            let body = callable_body(node, path.last().copied(), work);
            if let (Some(body), Some(name)) = (body, callable_decl_name(node)) {
                callables.push((body, source.text(name)));
            }
            true
        });
        let mut names = scope_names(&callables, &nodes)?;
        let mut at = 0usize;
        walk_with_path(root, |node, path| {
            work.charge(1);
            if !SCOPE_KINDS.contains(&node.kind()) {
                return true;
            }
            if let Some(slot) = names.get_mut(at).filter(|slot| slot.is_none()) {
                *slot = Some(callable_name(node, path, source, work));
            }
            at = at.saturating_add(1);
            true
        });
        let items = nodes
            .iter()
            .map(|node| (node.start_byte(), node.end_byte(), 1))
            .collect();
        let mut depths = Sweep::new(items, 0, join_count);
        let mut list = Vec::with_capacity(nodes.len());
        for (node, name) in nodes.iter().zip(names) {
            let depth = depths.query(node.start_byte(), node.end_byte());
            list.push(Scope {
                node: *node,
                name: name.ok_or(Gap("a scope has no name result"))?,
                depth: depth.ok_or(Gap("the scopes are not in the order of their start"))?,
            });
        }
        let index = list
            .iter()
            .enumerate()
            .map(|(k, scope)| (scope.node.id(), k))
            .collect();
        let items = list
            .iter()
            .enumerate()
            .map(|(k, scope)| {
                let start = scope.node.start_byte();
                (start, scope.node.end_byte(), (1, Some((start, Reverse(k)))))
            })
            .collect();
        let active = Sweep::new(items, (0, None), join_active);
        Ok(Self {
            list,
            index,
            active,
            contexts: HashMap::new(),
        })
    }

    /// The scopes that contain `node`: their count and the index of the innermost one. The nodes
    /// must come in walk order.
    pub(crate) fn active(&mut self, node: Node<'t>) -> Result<(usize, Option<usize>), Gap> {
        let (count, best) = self
            .active
            .query(node.start_byte(), node.end_byte())
            .ok_or(Gap("the nodes are not in the order of their start"))?;
        Ok((count, best.map(|(_, Reverse(k))| k)))
    }

    fn depth(&self, node: Node<'t>) -> Result<usize, Gap> {
        let k = self
            .index
            .get(&node.id())
            .ok_or(Gap("a body is not a scope"))?;
        self.list
            .get(*k)
            .map(|scope| scope.depth)
            .ok_or(Gap("a scope index is out of range"))
    }

    /// `_callable_context_for`. `ancestors` are the ancestors of `callable`, root first.
    pub(crate) fn context_for(
        &mut self,
        callable: Node<'t>,
        ancestors: &[Node<'t>],
        source: &Source<'_>,
        work: &Work<'t>,
    ) -> Result<Context, Gap> {
        if let Some(found) = self.contexts.get(&callable.id()) {
            return Ok(found.clone());
        }
        let found = self.compute_context(callable, ancestors, source, work)?;
        self.contexts.insert(callable.id(), found.clone());
        Ok(found)
    }

    fn compute_context(
        &self,
        callable: Node<'t>,
        ancestors: &[Node<'t>],
        source: &Source<'_>,
        work: &Work<'t>,
    ) -> Result<Context, Gap> {
        let (owner, owner_ancestors) = match ancestors.split_last() {
            Some((parent, rest)) if parent.kind() == "method_signature" => (*parent, rest),
            _ => (callable, ancestors),
        };
        let body = callable_body(owner, owner_ancestors.last().copied(), work);
        let mut scope = callable_name(callable, ancestors, source, work);
        if CONSTRUCTORS.contains(&callable.kind()) {
            let names: Vec<String> = named_children(callable)
                .into_iter()
                .filter(|child| child.kind() == "identifier")
                .map(|child| source.text(child))
                .collect();
            if !names.is_empty() {
                scope = Some(names.join("."));
            }
        }
        let Some(body) = body else {
            return Ok(Context {
                scope,
                span: Some(source.span(owner)),
                depth: 0,
            });
        };
        let mut scope_node = body;
        for child in children(body) {
            if SCOPE_KINDS.contains(&child.kind()) && child.start_byte() > scope_node.start_byte() {
                scope_node = child;
            }
        }
        Ok(Context {
            scope,
            span: Some(source.span(scope_node)),
            depth: self.depth(scope_node)?,
        })
    }
}

/// `_scope_name` for each scope: the name of the smallest callable body that contains it, or
/// `None` where Python calls `_callable_name`.
fn scope_names<'t>(
    callables: &[(Node<'t>, String)],
    nodes: &[Node<'t>],
) -> Result<Vec<Option<Option<String>>>, Gap> {
    let items = callables
        .iter()
        .enumerate()
        .map(|(j, (body, _))| {
            let size = body.end_byte().saturating_sub(body.start_byte());
            (body.start_byte(), body.end_byte(), Some((size, j)))
        })
        .collect();
    let mut sweep = Sweep::new(items, None, join_smallest);
    nodes
        .iter()
        .map(|node| {
            let found = sweep
                .query(node.start_byte(), node.end_byte())
                .ok_or(Gap("the scopes are not in the order of their start"))?;
            Ok(found
                .and_then(|(_, j)| callables.get(j))
                .map(|(_, name)| Some(name.clone())))
        })
        .collect()
}

/// `_callable_decl_name`.
pub(crate) fn callable_decl_name<'t>(node: Node<'t>) -> Option<Node<'t>> {
    named(node, "name").or_else(|| {
        let signature = named_children(node)
            .into_iter()
            .find(|child| child.kind() == "function_signature")?;
        named(signature, "name")
    })
}

/// `_callable_body`: the body after a signature. `parent` is the parent of `owner`.
pub(crate) fn callable_body<'t>(
    owner: Node<'t>,
    parent: Option<Node<'t>>,
    work: &Work<'t>,
) -> Option<Node<'t>> {
    if owner.kind() == "function_expression" {
        return named_children(owner)
            .into_iter()
            .find(|child| child.kind() == "function_expression_body");
    }
    let family = work.family(parent?);
    for sibling in family.after(owner)? {
        if BODIES.contains(&sibling.kind()) {
            return Some(*sibling);
        }
        if BODY_STOPS.contains(&sibling.kind()) {
            break;
        }
    }
    None
}

/// `_callable_name`: the name of the nearest named callable of `node` or of its ancestors.
pub(crate) fn callable_name<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
) -> Option<String> {
    let mut at = ancestors.len();
    let mut current = node;
    loop {
        work.charge(1);
        let parent = at
            .checked_sub(1)
            .and_then(|index| ancestors.get(index))
            .copied();
        if NAMED_CALLABLES.contains(&current.kind()) {
            if let Some(name) = named(current, "name") {
                return Some(source.text(name));
            }
        }
        if let Some(parent) = parent.filter(|_| BODIES.contains(&current.kind())) {
            if let Some(name) = signature_name_before(current, parent, source, work) {
                return Some(name);
            }
        }
        current = parent?;
        at = at.saturating_sub(1);
    }
}

/// The name of the nearest earlier signature sibling of a body that has a name.
fn signature_name_before<'t>(
    body: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Option<String> {
    let family = work.family(parent);
    let siblings = &family.nodes;
    // `index` is -1 when the body is missing, and `siblings[:-1]` drops the last sibling.
    let index = family
        .position(body)
        .unwrap_or_else(|| siblings.len().saturating_sub(1));
    siblings
        .get(..index)
        .unwrap_or_default()
        .iter()
        .rev()
        .filter(|signature| DECLARED.contains(&signature.kind()))
        .find_map(|signature| named(*signature, "name"))
        .map(|name| source.text(name))
}
