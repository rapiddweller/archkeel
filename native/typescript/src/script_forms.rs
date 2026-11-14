// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The open forms of AD-460 and AD-492 that the write check can close without a value flow (AD-498).
//!
//! Each form below can reach `Function`, `eval` or a window through a key, a pattern or a URL that
//! the file builds at run time. The check adds one unknown write for each such node. It adds no
//! publication and no PASS, and each form is stricter than before.

use tree_sitter::Node;

use crate::kinds::F;
use crate::references::literal;
use crate::script_syntax::Producer;
use crate::script_window::Receiver;

/// The global objects that are no function and give no reflection (`Reflect` does): a computed
/// call on them reaches no `Function`.
const NAMESPACES: [&str; 5] = ["Math", "JSON", "Atomics", "Intl", "console"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A write with a key that is not a literal on `this` of a class method: a caller can extract
    /// the method and give it the window (AD-460).
    pub(crate) fn open_key_write(&self, object: Node<'t>) -> bool {
        let object = self.tree.cx.unwrapped(object);
        object.kind() == "this" && self.receiver(object) == Receiver::Method
    }

    /// A node of an open form that writes an unknown name.
    pub(crate) fn open_form(&self, node: Node<'t>) -> bool {
        match node.kind() {
            "subscript_expression" => self.runtime_key_call(node),
            "call_expression" => {
                self.runtime_reflection(node) || self.location_call(node) || self.open_self(node)
            }
            "assignment_expression" | "augmented_assignment_expression" => {
                self.location_write(node)
            }
            "shorthand_property_identifier_pattern" | "pair_pattern" => self.window_pattern(node),
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
        let called = self.called(node);
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

    /// The value is called, constructed or tagged, also through `call`, `apply` or `bind`, and
    /// through parentheses and type wrappers.
    fn called(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let mut at = node;
        while let Some(parent) = tree.parent(at) {
            match parent.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression"
                | "type_assertion" => at = parent,
                "call_expression" | "new_expression" => {
                    return tree.is_field_of_parent(at, F::Function)
                        || tree.is_field_of_parent(at, F::Constructor);
                }
                "member_expression" if tree.is_field_of_parent(at, F::Object) => {
                    let name = tree.field(parent, F::Property).map(|p| tree.text(p));
                    return matches!(name.as_deref(), Some("call" | "apply" | "bind"));
                }
                _ => return false,
            }
        }
        false
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
        let key = tree.field(call, F::Arguments).and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .get(1)
                .copied()
        });
        match name.as_str() {
            "getOwnPropertyDescriptors" | "*" => true,
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
        let first = tree.field(call, F::Arguments).and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .first()
                .copied()
        });
        object == "location"
            && matches!(name.as_str(), "assign" | "replace" | "*")
            && first.is_none_or(|first| literal(Some(first), tree.cx.source).is_none())
    }

    /// `location = x`, `x.location = x`, `location.href = x` and the same with a string key or a
    /// key that is not a literal, also with `+=`: a value that is no literal can be a
    /// `javascript:` URL, which runs in this page.
    fn location_write(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(left) = tree.field(node, F::Left).map(|l| tree.cx.unwrapped(l)) else {
            return false;
        };
        let name = |n: Node<'t>| match n.kind() {
            "property_identifier" | "identifier" => Some(tree.text(n)),
            "string" | "template_string" => crate::script_window::string_text(self, n),
            _ => None,
        };
        let member = |at: Node<'t>| match at.kind() {
            "member_expression" => tree.field(at, F::Property).and_then(name),
            "subscript_expression" => tree.field(at, F::Index).and_then(name),
            _ => None,
        };
        // `location`, `x.location` and `x["location"]` name the location of a window.
        let is_location = |at: Node<'t>| {
            let at = tree.cx.unwrapped(at);
            match at.kind() {
                "identifier" => tree.text(at) == "location",
                _ => member(at).is_some_and(|key| key == "location"),
            }
        };
        let sink = match left.kind() {
            "identifier" => tree.text(left) == "location",
            "member_expression" | "subscript_expression" => {
                let on_location = tree.field(left, F::Object).is_some_and(is_location);
                let runtime_key = left.kind() == "subscript_expression"
                    && tree.field(left, F::Index).is_some_and(|i| {
                        i.kind() != "number" && crate::script_window::string_text(self, i).is_none()
                    });
                member(left).is_some_and(|key| key == "location")
                    || (on_location
                        && (runtime_key || member(left).is_some_and(|key| key == "href")))
            }
            _ => false,
        };
        sink && literal(tree.field(node, F::Right), tree.cx.source).is_none()
    }

    /// A destructuring pattern that takes a window member or a window name out of a value: the
    /// binding is then a window, and no later read of the name sees it.
    fn window_pattern(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let key = match node.kind() {
            "pair_pattern" => tree.field(node, F::Key),
            _ => Some(node),
        };
        let Some(key) = key else { return false };
        let name = match key.kind() {
            "string" => crate::script_window::string_text(self, key),
            "computed_property_name" => return false,
            _ => crate::script_window::cooked(&tree.text(key)),
        };
        !tree.in_type(node)
            && name.is_none_or(|name| crate::script_window::window_member_name(&name))
    }

    /// `open(x, y)` and `window.open(x, y)` with a first argument that is no literal and a second
    /// that is no `_blank`: the target can be this window, and a `javascript:` URL runs there.
    fn open_self(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(callee) = tree.field(call, F::Function).map(|c| tree.cx.unwrapped(c)) else {
            return false;
        };
        let global = match callee.kind() {
            "identifier" => {
                tree.text(callee) == "open" && tree.binding_scope(callee, "open").is_none()
            }
            "member_expression" => {
                let named = tree.field(callee, F::Property).map(|p| tree.text(p));
                named.as_deref() == Some("open")
                    && tree
                        .field(callee, F::Object)
                        .is_some_and(|object| self.window_leaf(tree.cx.unwrapped(object)))
            }
            _ => false,
        };
        let arguments = tree
            .field(call, F::Arguments)
            .map(crate::tree::nodes::named_children)
            .unwrap_or_default();
        let plain = |node: Option<&Node<'t>>| node.and_then(|n| literal(Some(*n), tree.cx.source));
        global
            && !arguments.is_empty()
            && plain(arguments.first()).is_none()
            && arguments.get(1).is_some()
            && plain(arguments.get(1)).is_none_or(|target| target != "_blank")
    }

    /// The object name and the member name of a call `object.name(…)`.
    fn member_call(&self, call: Node<'t>) -> Option<(String, String)> {
        let tree = self.tree;
        // A key that is no literal is `*`: it can be any member.
        let key = |at: Node<'t>| match at.kind() {
            "member_expression" => tree.field(at, F::Property).map(|p| tree.text(p)),
            "subscript_expression" => tree
                .field(at, F::Index)
                .map(|i| crate::script_window::string_text(self, i).unwrap_or_else(|| "*".into())),
            _ => None,
        };
        let callee = tree.cx.unwrapped(tree.field(call, F::Function)?);
        let name = key(callee)?;
        let object = tree.cx.unwrapped(tree.field(callee, F::Object)?);
        let object = match object.kind() {
            "identifier" => tree.text(object),
            _ => key(object)?,
        };
        Some((object, name))
    }
}
