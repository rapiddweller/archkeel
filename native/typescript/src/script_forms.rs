// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The open forms of AD-460 that the write check can close without a value flow.

use tree_sitter::Node;

use crate::kinds::F;
use crate::references::literal;
use crate::script_syntax::Producer;
use crate::script_window::Receiver;

/// MEASURE: one switch for each open form.
pub(crate) const FORMS: [bool; 5] = [false, false, false, false, false];

/// The global objects that are no function: a computed call on them reaches no `Function`.
const NAMESPACES: [&str; 6] = ["Math", "JSON", "Reflect", "Atomics", "Intl", "console"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A write with a key that is not a literal on an object that is not proven local.
    pub(crate) fn open_key_write(&self, object: Node<'t>) -> bool {
        let object = self.tree.cx.unwrapped(object);
        let method_this = object.kind() == "this" && self.receiver(object) == Receiver::Method;
        FORMS[0] || (FORMS[1] && method_this)
    }

    /// A node of an open form that writes an unknown name.
    pub(crate) fn open_form(&self, node: Node<'t>) -> bool {
        match node.kind() {
            "subscript_expression" => FORMS[2] && self.runtime_key_call(node),
            "call_expression" => {
                (FORMS[3] && self.runtime_reflection(node)) || (FORMS[4] && self.location_call(node))
            }
            "assignment_expression" => FORMS[4] && self.location_write(node),
            _ => false,
        }
    }

    /// `o[k](…)` with a key that is not a literal, on a value that is not data or a namespace.
    fn runtime_key_call(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let index = tree.field(node, F::Index);
        if literal(index, tree.cx.source).is_some() || index.is_some_and(|i| i.kind() == "number") {
            return false;
        }
        let called = tree.parent(node).is_some_and(|parent| {
            matches!(parent.kind(), "call_expression" | "new_expression")
                && (tree.is_field_of_parent(node, F::Function)
                    || tree.is_field_of_parent(node, F::Constructor))
        });
        let Some(object) = tree.field(node, F::Object).map(|o| tree.cx.unwrapped(o)) else {
            return false;
        };
        let data = matches!(object.kind(), "object" | "array")
            || (object.kind() == "identifier"
                && (self
                    .sole_value(object)
                    .is_some_and(|value| matches!(value.kind(), "object" | "array"))
                    || (tree.binding_scope(object, &tree.text(object)).is_none()
                        && NAMESPACES.contains(&tree.text(object).as_str()))));
        called && !data
    }

    /// `Reflect.get(o, k)`, `Object.getOwnPropertyDescriptor(o, k)` with a key that is not a
    /// literal, and `getOwnPropertyDescriptors`: they can reach `constructor`.
    fn runtime_reflection(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some((object, name)) = self.member_call(call) else {
            return false;
        };
        if !matches!(object.as_str(), "Reflect" | "Object") {
            return false;
        }
        let key = tree
            .field(call, F::Arguments)
            .and_then(|arguments| crate::tree::nodes::named_children(arguments).get(1).copied());
        match name.as_str() {
            "getOwnPropertyDescriptors" => true,
            "get" | "getOwnPropertyDescriptor" => {
                key.is_none_or(|key| literal(Some(key), tree.cx.source).is_none())
            }
            _ => false,
        }
    }

    /// `location.assign(x)` or `location.replace(x)` with a value that is not a literal.
    fn location_call(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some((object, name)) = self.member_call(call) else {
            return false;
        };
        let first = tree
            .field(call, F::Arguments)
            .and_then(|arguments| crate::tree::nodes::named_children(arguments).first().copied());
        object == "location"
            && matches!(name.as_str(), "assign" | "replace")
            && first.is_none_or(|first| literal(Some(first), tree.cx.source).is_none())
    }

    /// `location = x`, `x.location = x` or `location.href = x` with a value that is not a literal.
    fn location_write(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(left) = tree.field(node, F::Left).map(|l| tree.cx.unwrapped(l)) else {
            return false;
        };
        let text = |n: Option<Node<'t>>| n.map(|n| tree.text(n)).unwrap_or_default();
        let sink = match left.kind() {
            "identifier" => tree.text(left) == "location",
            "member_expression" => {
                let property = text(tree.field(left, F::Property));
                let object = tree.field(left, F::Object).map(|o| tree.cx.unwrapped(o));
                property == "location"
                    || (property == "href"
                        && object.is_some_and(|o| {
                            o.kind() == "identifier" && tree.text(o) == "location"
                                || (o.kind() == "member_expression"
                                    && text(tree.field(o, F::Property)) == "location")
                        }))
            }
            _ => false,
        };
        sink && literal(tree.field(node, F::Right), tree.cx.source).is_none()
    }

    /// The object name and the member name of a call `object.name(…)`.
    fn member_call(&self, call: Node<'t>) -> Option<(String, String)> {
        let tree = self.tree;
        let callee = tree.field(call, F::Function)?;
        if callee.kind() != "member_expression" {
            return None;
        }
        let object = tree.cx.unwrapped(tree.field(callee, F::Object)?);
        let name = tree.text(tree.field(callee, F::Property)?);
        let object = match object.kind() {
            "identifier" => tree.text(object),
            "member_expression" => tree.text(tree.field(object, F::Property)?),
            _ => return None,
        };
        Some((object, name))
    }
}
