// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reflective writes of a value that the file does not make (AD-766): a member of `Object` or
//! `Reflect` that writes members of its first argument, and the accessor members
//! `__defineGetter__` and `__defineSetter__` of any object. On a window value a reflective write
//! is direct; on any other value that the file does not make it is an amplifier form (a host
//! entry can make the value the window). Such a member used as a value (stored, passed, called
//! through `call` or `apply`) is direct: the check cannot read the target of the later call.

use tree_sitter::Node;

use crate::kinds::F;
use crate::script_names::bound_scope;
use crate::script_syntax::Producer;
use crate::script_tree::Tree;
use crate::script_window::Reach;
use crate::tree::cx::Cx;

/// The members of `Object` that write members of their first argument.
const REFLECTIVE_OBJECT: [&str; 4] = [
    "assign",
    "defineProperty",
    "defineProperties",
    "setPrototypeOf",
];

/// The members of `Reflect` that write a member or the prototype of their first argument.
const REFLECTIVE_REFLECT: [&str; 3] = ["set", "defineProperty", "setPrototypeOf"];

/// The members of any object that put an accessor on it.
const ACCESSORS: [&str; 2] = ["__defineGetter__", "__defineSetter__"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A call of a reflective write of `Object` or `Reflect`, or of an accessor member, on a
    /// value that the file does not make.
    pub(crate) fn reflective_write(&self, call: Node<'t>) -> Option<Reach> {
        let tree = self.tree;
        let callee = Cx::unwrapped(&tree.cx, tree.field(call, F::Function)?);
        if tree.in_type(call) || !self.reflective_name(callee) {
            return None;
        }
        let target = if self.accessor_name(callee) {
            tree.field(callee, F::Object)
                .map(|o| Cx::unwrapped(&tree.cx, o))
        } else {
            self.argument(call, 0)
        };
        let Some(target) = target else {
            return Some(Reach::Amplified);
        };
        if Node::kind(&target) == "spread_element" {
            return Some(Reach::Direct);
        }
        if self.proven_local(target) {
            return None;
        }
        Some(
            self.window_gate(target)
                .map_or(Reach::Amplified, |_| Reach::Direct),
        )
    }

    /// A reflective write member that is no direct callee: a later call that the check cannot
    /// read can run it on a window.
    pub(crate) fn reflective_member(&self, node: Node<'t>) -> Option<Reach> {
        let reflective = self.reflective_name(node) && !self.tree.in_type(node);
        let tree = self.tree;
        let callee = tree.parent(node).is_some_and(|parent| {
            Node::kind(&parent) == "call_expression" && tree.is_field_of_parent(node, F::Function)
        });
        (reflective && !callee).then_some(Reach::Direct)
    }

    /// `Object.assign` and the other members of the lists, with the free `Object` or `Reflect`,
    /// or `x.__defineGetter__`, also with a literal key.
    fn reflective_name(&self, member: Node<'t>) -> bool {
        if self.accessor_name(member) {
            return true;
        }
        let tree = self.tree;
        let Some(name) = self.member_text(member) else {
            return false;
        };
        let Some(object) = tree
            .field(member, F::Object)
            .and_then(|root| self.global_namespace(Cx::unwrapped(&tree.cx, root)))
        else {
            return false;
        };
        let list: &[&str] = match String::as_str(&object) {
            "Object" => &REFLECTIVE_OBJECT,
            "Reflect" => &REFLECTIVE_REFLECT,
            _ => return false,
        };
        list.contains(&String::as_str(&name))
    }

    /// The name of the free `Object` or `Reflect`, also read through a window name
    /// (`globalThis.Reflect`, `window['Object']`).
    fn global_namespace(&self, root: Node<'t>) -> Option<String> {
        let tree = self.tree;
        match Node::kind(&root) {
            "identifier" => {
                let name = Tree::text(tree, root);
                bound_scope(tree, root, &name).is_none().then_some(name)
            }
            "member_expression" | "subscript_expression" => {
                let object = tree
                    .field(root, F::Object)
                    .map(|o| Cx::unwrapped(&tree.cx, o))?;
                let window = self.window_gate(object) == Some(Reach::Direct);
                window.then(|| self.member_text(root)).flatten()
            }
            _ => None,
        }
    }

    /// `x.__defineGetter__` or `x['__defineSetter__']`.
    fn accessor_name(&self, member: Node<'t>) -> bool {
        self.member_text(member)
            .is_some_and(|name| ACCESSORS.contains(&String::as_str(&name)))
    }

    /// The name of a member: its property, or the text of a literal key.
    fn member_text(&self, member: Node<'t>) -> Option<String> {
        let tree = self.tree;
        match Node::kind(&member) {
            "member_expression" => tree
                .field(member, F::Property)
                .and_then(|p| crate::script_window::cooked(&Tree::text(tree, p))),
            "subscript_expression" => tree.field(member, F::Index).and_then(|i| self.text_of(i)),
            _ => None,
        }
    }
}
