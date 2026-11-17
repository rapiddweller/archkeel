// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The values that may be a prototype that the global object inherits from (#1527, AD-768).
//!
//! The global object inherits members such as `dispatchEvent` from `EventTarget.prototype` and
//! `toString` from `Object.prototype`. A write through such a prototype changes the global as a
//! write through the window does. A prototype that escapes and a write through it with a run-time
//! key write an unknown global, and a new `__proto__` of a value that is not proven local is an
//! amplifier form (AD-540). Only a
//! class that the file declares and never writes again has a prototype that is no platform
//! prototype. A named write through a prototype blocks the global of that name already (AD-460).

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_names::bound_scope;
use crate::script_syntax::Producer;
use crate::script_window::{cooked, Written};

/// The member names that give a prototype of their object.
const PROTOTYPE: &str = "prototype";
const PROTO: &str = "__proto__";

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A prototype of the global object that leaves its place: passed, stored or returned. A
    /// member read, an element and a comparison give no prototype to anyone.
    pub(crate) fn prototype_escape(&self, node: Node<'t>) -> bool {
        self.platform_prototype(node) && self.escapes(node, false)
    }

    /// A write target that changes a prototype of the global object. `p[k] = v` with a run-time
    /// key on such a prototype is direct. `x.__proto__ = v` on a value that is not proven local is
    /// an amplifier, as each write through such a value is (AD-766): the value is the window only
    /// with a host entry.
    pub(crate) fn prototype_write(&self, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let target = tree.cx.unwrapped(target);
        if !matches!(target.kind(), "member_expression" | "subscript_expression") {
            return None;
        }
        let keyed = target.kind() == "subscript_expression"
            && self
                .runtime_object(target)
                .is_some_and(|object| self.platform_prototype(object));
        if keyed {
            return Some(Written::Unknown);
        }
        let object = tree.field(target, F::Object).map(|o| tree.cx.unwrapped(o));
        let proto = self.member_key(target).as_deref() == Some(PROTO);
        (proto && !object.is_some_and(|o| self.proven_local(o))).then_some(Written::Amplified)
    }

    /// The value may be a prototype of the global object: `X.prototype` of a name that is no
    /// class of the file, `x.__proto__` on any value, and a call of a member `getPrototypeOf`.
    fn platform_prototype(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let node = tree.cx.unwrapped(node);
        if tree.in_type(node) {
            return false;
        }
        match node.kind() {
            "member_expression" | "subscript_expression" => {
                let object = tree.field(node, F::Object).map(|o| tree.cx.unwrapped(o));
                match self.member_key(node).as_deref() {
                    Some(PROTO) => true,
                    Some(PROTOTYPE) => !object.is_some_and(|o| self.local_class(o)),
                    _ => false,
                }
            }
            "call_expression" => tree
                .field(node, F::Function)
                .map(|callee| tree.cx.unwrapped(callee))
                .and_then(|callee| self.member_key(callee))
                .is_some_and(|name| name == "getPrototypeOf"),
            _ => false,
        }
    }

    /// The cooked name of a dotted member or of a literal key. A name with an escape that is not
    /// plain is unknown, and an unknown name can be any of them, so it is the text `__proto__`.
    fn member_key(&self, node: Node<'t>) -> Option<String> {
        let tree = self.tree;
        match node.kind() {
            "member_expression" => {
                let property = tree.text(tree.field(node, F::Property)?);
                Some(cooked(&property).unwrap_or_else(|| PROTO.to_owned()))
            }
            "subscript_expression" => self.text_of(tree.field(node, F::Index)?),
            _ => None,
        }
    }

    /// A name that the file binds once to a class and never writes again. The `prototype` of a
    /// class can be neither written nor redefined, so it stays the new object of the class. The
    /// `prototype` of a function can be written, so a function is no such class.
    fn local_class(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        if object.kind() != "identifier" {
            return false;
        }
        let expression = self
            .sole_value(object)
            .is_some_and(|value| matches!(tree.k(value), K::Class | K::ClassExpression));
        expression || self.class_declaration(object)
    }

    /// A name that one class declaration of its scope binds, and that nothing writes again.
    fn class_declaration(&self, name: Node<'t>) -> bool {
        let tree = self.tree;
        let text = tree.text(name);
        let Some(scope) = bound_scope(tree, name, &text) else {
            return false;
        };
        if tree.binding_count(scope, &text) != 1
            || self.index.written.contains(&(scope.id(), text.clone()))
        {
            return false;
        }
        crate::tree::nodes::named_children(scope)
            .into_iter()
            .filter_map(|statement| match statement.kind() {
                "export_statement" => tree.field(statement, F::Declaration),
                _ => Some(statement),
            })
            .any(|declaration| {
                matches!(
                    tree.k(declaration),
                    K::ClassDeclaration | K::AbstractClassDeclaration
                ) && tree
                    .field(declaration, F::Name)
                    .is_some_and(|class| tree.text(class) == text)
            })
    }
}
