// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declarations that a script makes: the members that each published object takes from local
//! definitions, the writes of the file and the paths that it writes (`_script_declarations`).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_names::bound_scope;
use crate::script_scope::is_root;
use crate::script_syntax::{unique, Producer};
use crate::script_tree::Tree;
use crate::script_types::{key_form, Member, Write};
use crate::script_window::Written;
use crate::source::Span;

/// What `_script_declarations` returns.
pub(crate) struct Declarations {
    pub members: HashMap<Span, Vec<Member>>,
    pub writes: Vec<Write>,
    pub paths: Vec<Vec<String>>,
    pub top_level_paths: Vec<Vec<String>>,
    /// The writes of the one check (AD-460); the script writes take them too.
    pub checked: Vec<Write>,
    /// Some node writes an unknown name through an amplifier form (AD-540).
    pub amplified: bool,
    pub blockers: Vec<crate::script_types::Blocker>,
    pub amp_blockers: Vec<crate::script_types::Blocker>,
    /// An empty path that no blocker names.
    pub unlabelled_empty: bool,
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
    checked: Vec<Write>,
    /// A node of an amplifier form wrote an unknown name (AD-540).
    amplified: bool,
    blockers: Vec<crate::script_types::Blocker>,
    amp_blockers: Vec<crate::script_types::Blocker>,
    /// The empty paths that a blocker names.
    labelled_empty: usize,
}

impl<'t> Gathered<'t> {
    /// A write of the one check at the place of `span`: a write and a path of its name, or a
    /// write and a path of an unknown name. Call it after the source write of the same target.
    fn check(&mut self, written: Option<Written>, span: Span, form: &'static str) {
        let amplifier = matches!(written, Some(Written::Amplified));
        let (name, path) = match written {
            Some(Written::Name(name)) => (Some(name.clone()), vec![name]),
            Some(Written::Unknown | Written::Amplified) => (None, Vec::new()),
            None => return,
        };
        // An amplifier form leaves the unknown write of the file but no empty path: the project
        // decides with its host entry whether the write blocks every name.
        self.amplified |= amplifier;
        if amplifier {
            self.amp_blockers.push((span.clone(), form));
        }
        if name.is_none() && !amplifier {
            self.blockers.push((span.clone(), form));
            self.labelled_empty += 1;
        }
        // The write of the target that the source writes just took: the script writes and the
        // paths hold it already.
        if self
            .writes
            .last()
            .is_some_and(|last| last.0 == name && last.1 == span)
        {
            // The source write of a target with no static path holds no path of its own, so an
            // unknown name still gives the empty path that blocks every proof (AD-460).
            if name.is_none() && !amplifier {
                self.paths.push(Vec::new());
            }
            return;
        }
        self.writes.push((name.clone(), span.clone()));
        self.checked.push((name, span));
        if !(amplifier && path.is_empty()) {
            self.paths.push(path);
        }
    }

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
        let tree: &Tree<'_, '_> = self.tree;
        let Some(first) = route.first() else {
            return;
        };
        if is_root(first) || tree.script_free_in(target, target, false) {
            let skip = usize::from(is_root(first));
            found.paths.push(route.iter().skip(skip).cloned().collect());
            return;
        }
        let at_top =
            bound_scope(tree, target, first).is_some_and(|scope| scope.id() == tree.root.id());
        if at_top {
            found.top_level.push(route.to_vec());
        }
    }

    /// The write that an assignment makes to `target`, with the aliases of the wrapper of `node`.
    pub(crate) fn write_of(&self, node: Node<'t>, target: Node<'t>) -> Write {
        let tree: &Tree<'_, '_> = self.tree;
        let wrapper = self.wrapper_of(node);
        let alias = |name: &str| self.is_alias(wrapper, name);
        tree.target_write(node, target, &alias)
    }

    /// The paths that an assignment target writes.
    fn write_paths(&self, node: Node<'t>, target: Node<'t>, found: &mut Gathered<'t>) {
        let tree: &Tree<'_, '_> = self.tree;
        found.writes.push(self.write_of(node, target));
        let route = tree.static_path(target);
        self.route_paths(target, &route, found);
        if route.len() > 1 {
            found
                .paths
                .extend(self.write_alias_path(target, &[], None, None));
        }
    }

    /// The target of an assignment, unless the object that it writes into is a call.
    fn declared_target(&self, node: Node<'t>, target: Node<'t>, found: &mut Gathered<'t>) {
        let tree: &Tree<'_, '_> = self.tree;
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
        let tree: &Tree<'_, '_> = self.tree;
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
        let tree: &Tree<'_, '_> = self.tree;
        let mut found = Gathered::default();
        let mut targets = self.targets.iter().peekable();
        for node in tree.nodes.iter().copied() {
            found.writes.extend(tree.declaration_write(node));
            found.check(self.node_write(node), tree.span(node), form_of(node));
            found.check(
                self.prototype_escape(node).then_some(Written::Unknown),
                tree.span(node),
                "a prototype of the global object that is passed on",
            );
            while let Some((_, target)) = targets.next_if(|(owner, _)| owner.id() == node.id()) {
                self.declared_target(node, *target, &mut found);
                found.check(
                    self.global_write(*target),
                    tree.span(node),
                    "a write through a key that is no literal",
                );
                found.check(
                    self.method_key_write(*target),
                    tree.span(node),
                    "a write through this with a key that is no literal",
                );
                found.check(
                    self.location_target(node, *target),
                    tree.span(node),
                    "a navigation to a text that is no literal",
                );
                found.check(
                    self.prototype_write(*target),
                    tree.span(node),
                    "a write that changes a prototype of the global object",
                );
                found.check(
                    self.changed_global(*target),
                    tree.span(node),
                    "a write that changes a global through a window value",
                );
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
        let unlabelled_empty =
            found.paths.iter().filter(|path| path.is_empty()).count() > found.labelled_empty;
        Declarations {
            members,
            writes: unique(found.writes),
            paths: unique(found.paths),
            top_level_paths: unique(found.top_level),
            checked: unique(found.checked),
            amplified: found.amplified,
            unlabelled_empty,
            blockers: unique(found.blockers),
            amp_blockers: unique(found.amp_blockers),
        }
    }
}

/// The kind of the form at a node that writes an unknown global, as a short phrase (AD-540).
fn form_of(node: Node) -> &'static str {
    match node.kind() {
        "subscript_expression" => key_form(),
        "call_expression" => "a call that can run code or open a window",
        "string" | "template_string" => "a text that can run as code",
        "assignment_expression" | "augmented_assignment_expression" | "for_in_statement" => {
            "a write of markup or code"
        }
        "shorthand_property_identifier_pattern" | "pair_pattern" => "a pattern that takes a window",
        "member_expression" => "a member that can be the window or can reach code",
        "this" => "a this that a caller can give the window",
        _ => "a name that is the global object or runs code",
    }
}
