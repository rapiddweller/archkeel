// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declarations that a script makes: the members that each published object takes from local
//! definitions, the writes of the file and the paths that it writes (`_script_declarations`).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::{is_function, is_root};
use crate::script_syntax::{unique, Producer};
use crate::script_types::{Member, Write};
use crate::source::Span;
use crate::source_input::FRAME_ROOTS;

/// The path on the global object without its leading roots, so that `parent.self.f` writes `f`.
/// A frame root and `opener` are a window too: a write through them can replace a global that a
/// script of the project reads in that window.
fn global_path(path: impl IntoIterator<Item = String>) -> Vec<String> {
    let window =
        |name: &String| is_root(name) || FRAME_ROOTS.contains(&name.as_str()) || name == "opener";
    path.into_iter().skip_while(window).collect()
}

/// What `_script_declarations` returns.
pub(crate) struct Declarations {
    pub members: HashMap<Span, Vec<Member>>,
    pub writes: Vec<Write>,
    pub paths: Vec<Vec<String>>,
    pub top_level_paths: Vec<Vec<String>>,
}

/// What the producer finds while it reads the nodes in order.
#[derive(Default)]
struct Gathered<'t> {
    /// The objects that the file publishes, by the span of the assignment or of the binding.
    objects: Vec<(Span, Node<'t>)>,
    at: HashMap<Span, usize>,
    writes: Vec<Write>,
    paths: Vec<Vec<String>>,
    top_level: Vec<Vec<String>>,
}

impl<'t> Gathered<'t> {
    /// `objects[span] = object`: a later object of the same span replaces the earlier one.
    fn put(&mut self, span: Span, object: Node<'t>) {
        match self.at.get(&span) {
            Some(&index) => {
                if let Some(slot) = self.objects.get_mut(index) {
                    slot.1 = object;
                }
            }
            None => {
                self.at.insert(span.clone(), self.objects.len());
                self.objects.push((span, object));
            }
        }
    }
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The path that a target writes on the global object, or at the top level of the file.
    fn route_paths(&self, target: Node<'t>, route: &[String], found: &mut Gathered<'t>) {
        let tree = self.tree;
        let Some(first) = route.first() else {
            return;
        };
        if is_root(first) || tree.script_free_in(target, target, false) {
            found.paths.push(global_path(route.iter().cloned()));
            return;
        }
        let at_top = tree
            .bound_scope(target, first)
            .is_some_and(|scope| scope.id() == tree.root.id());
        if at_top {
            found.top_level.push(route.to_vec());
        }
    }

    /// The paths that an assignment target writes.
    fn write_paths(&self, node: Node<'t>, target: Node<'t>, found: &mut Gathered<'t>) {
        let tree = self.tree;
        let wrapper = self.wrapper_of(node);
        let alias = |name: &str| self.is_alias(wrapper, name);
        found.writes.push(tree.target_write(node, target, &alias));
        let route = tree.static_path(target);
        self.route_paths(target, &route, found);
        if route.len() > 1 {
            found
                .paths
                .extend(self.write_alias_path(target, &[], None, None));
        }
        found.paths.extend(self.this_path(target));
    }

    /// A `this` that can be the global object: not in a module file, which is strict, and not in a
    /// class, whose code is strict. A plain call of a function in a sloppy script gives that `this`.
    fn global_receiver(&self, this: Node<'t>) -> bool {
        let tree = self.tree;
        if self.module_syntax || tree.k(this) != K::This {
            return false;
        }
        let owner = tree.ancestors(this).find(|node| {
            let kind = tree.k(*node);
            matches!(kind, K::ClassBody | K::ClassStaticBlock)
                || (is_function(kind) && kind != K::ArrowFunction)
        });
        owner.is_none_or(|owner| {
            let kind = tree.k(owner);
            let method = kind == K::MethodDefinition
                && tree
                    .parent(owner)
                    .is_some_and(|body| tree.k(body) == K::ClassBody);
            !(method || matches!(kind, K::ClassBody | K::ClassStaticBlock))
        })
    }

    /// The path that a write target reaches from a `this` that can be the global object. A
    /// computed member directly on `this` can name any global.
    fn this_path(&self, target: Node<'t>) -> Option<Vec<String>> {
        let tree = self.tree;
        let mut names = Vec::new();
        let mut at = tree.unparenthesized(target);
        loop {
            match tree.k(at) {
                K::MemberExpression => {
                    let property = tree.field(at, F::Property)?;
                    names.push(tree.text(property));
                }
                K::SubscriptExpression => names.clear(),
                _ => break,
            }
            at = tree.unparenthesized(tree.field(at, F::Object)?);
        }
        if !self.global_receiver(at) {
            return None;
        }
        names.reverse();
        Some(global_path(names))
    }

    /// The unknown path `()` that a node gives: code that it runs, or a `this` that can be the
    /// global object and escapes.
    fn opaque_path(&self, node: Node<'t>) -> Option<Vec<String>> {
        let tree = self.tree;
        let escaped = self.global_receiver(node) && tree.script_escape(node);
        (escaped || tree.runs_code(node)).then(Vec::new)
    }

    /// The target of an assignment, unless the object that it writes into is a call.
    fn declared_target(&self, node: Node<'t>, target: Node<'t>, found: &mut Gathered<'t>) {
        let tree = self.tree;
        let mut receiver = target;
        while matches!(
            tree.k(receiver),
            K::MemberExpression | K::SubscriptExpression
        ) {
            match tree.field(receiver, F::Object) {
                Some(object) => receiver = object,
                None => break,
            }
        }
        if tree.k(receiver) != K::CallExpression {
            self.write_paths(node, target, found);
        }
    }

    /// The object that a node publishes: the right side of an assignment, or what a wrapper that
    /// the file calls once returns.
    fn published_object(&self, node: Node<'t>) -> Option<(Span, Node<'t>)> {
        let tree = self.tree;
        if tree.k(node) == K::AssignmentExpression {
            let value = tree.field(node, F::Right)?;
            return (tree.k(value) == K::Object).then(|| (tree.span(node), value));
        }
        let info = self.wrappers.get(&node.id())?;
        let body = tree.field(node, F::Body)?;
        let parent = tree.parent(info.call)?;
        let (_, value) = tree.only_returned_object(body)?;
        Some((tree.span(parent), value))
    }

    /// `_script_declarations`: the members that each published object takes from local
    /// definitions, the writes of the file, and the paths that it writes.
    pub(crate) fn declarations(&self) -> Declarations {
        let tree = self.tree;
        let mut found = Gathered::default();
        let mut targets = self.targets.iter().peekable();
        for node in tree.nodes.iter().copied() {
            found.writes.extend(tree.declaration_write(node));
            found.paths.extend(self.opaque_path(node));
            while let Some((_, target)) = targets.next_if(|(owner, _)| owner.id() == node.id()) {
                self.declared_target(node, *target, &mut found);
            }
            if let Some((span, object)) = self.published_object(node) {
                found.put(span, object);
            }
        }
        let members = found
            .objects
            .iter()
            .map(|(span, object)| (span.clone(), self.object_members(*object)))
            .collect();
        Declarations {
            members,
            writes: unique(found.writes),
            paths: unique(found.paths),
            top_level_paths: unique(found.top_level),
        }
    }
}
