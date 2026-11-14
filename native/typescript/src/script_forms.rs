// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The open forms of AD-460 and AD-492 that the write check can close without a value flow (AD-500).
//!
//! Each form below can reach `Function`, `eval` or a window through a key, a pattern or a URL that
//! the file builds at run time. The check adds one unknown write for each such node. It adds no
//! publication and no PASS, and each form is stricter than before.

use tree_sitter::Node;

use crate::kinds::F;
use crate::references::literal;
use crate::script_syntax::Producer;
use crate::script_window::{Receiver, Written};

/// The globals whose value gives reflection, a navigation or a window of another origin. A free
/// name of them that is called, passed, stored or returned is an alias of the class.
const ALIASED: [&str; 4] = ["Object", "Reflect", "location", "open"];

/// The members that read a descriptor, and so the member `constructor`, with a key.
const REFLECTION: [&str; 2] = ["getOwnPropertyDescriptor", "getOwnPropertyDescriptors"];

fn call_member(name: &str) -> bool {
    matches!(name, "call" | "apply" | "bind")
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A write with a key that is no literal through `this` of a class method, through `super`,
    /// or through a name that is bound once to such a `this`: a caller can extract the method and
    /// give it the window (AD-460). Its place is the assignment target.
    pub(crate) fn method_key_write(&self, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let target = tree.cx.unwrapped(target);
        if target.kind() != "subscript_expression" {
            return None;
        }
        let object = tree.cx.unwrapped(tree.field(target, F::Object)?);
        let index = tree.field(target, F::Index)?;
        let key = index.kind() != "number" && self.text_of(index).is_none();
        let method =
            |this: Node<'t>| this.kind() == "this" && self.receiver(this) == Receiver::Method;
        let aliased = match object.kind() {
            "this" => method(object),
            "super" => true,
            "identifier" => self.sole_value(object).is_some_and(method),
            _ => false,
        };
        (key && aliased).then_some(Written::Unknown)
    }

    /// A write to `location`, to its `href`, or through a run-time key on it, from any target:
    /// an assignment with a value that is no literal, a compound assignment, a pattern, a `for`.
    pub(crate) fn location_target(&self, node: Node<'t>, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let target = tree.cx.unwrapped(target);
        if !self.location_sink(target) {
            return None;
        }
        let plain = node.kind() == "assignment_expression"
            && tree
                .field(node, F::Left)
                .is_some_and(|left| tree.cx.unwrapped(left).id() == target.id());
        let literal_value = plain && literal(tree.field(node, F::Right), tree.cx.source).is_some();
        (!literal_value).then_some(Written::Unknown)
    }

    /// A node of an open form that writes an unknown name.
    pub(crate) fn open_form(&self, node: Node<'t>) -> bool {
        match node.kind() {
            "subscript_expression" => self.runtime_key_call(node) || self.member_use(node),
            "member_expression" => self.member_use(node) || self.location_value(node),
            "identifier" | "shorthand_property_identifier" => self.alias_escape(node),
            "call_expression" => {
                self.runtime_reflection(node) || self.location_call(node) || self.open_call(node)
            }
            "shorthand_property_identifier_pattern" | "pair_pattern" => self.window_pattern(node),
            _ => false,
        }
    }

    /// The operands that a callee can give: a sequence gives its last, a condition and a logical
    /// operator give each branch, and a wrapper gives its inside.
    fn callee_parts(&self, callee: Node<'t>) -> Vec<Node<'t>> {
        let tree = self.tree;
        let mut found = Vec::new();
        let mut pending = vec![callee];
        while let Some(next) = pending.pop() {
            let next = tree.cx.unwrapped(next);
            let children = crate::tree::nodes::named_children(next);
            match next.kind() {
                "sequence_expression" => pending.extend(children.last().copied()),
                "ternary_expression" => pending.extend(children.iter().skip(1).copied()),
                "binary_expression" => pending.extend(children.iter().copied()),
                "await_expression" => pending.extend(children.first().copied()),
                _ => found.push(next),
            }
        }
        found
    }

    /// `o[k](…)` with a key that is not a literal, on a value that is not data or a namespace.
    fn runtime_key_call(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let index = tree.field(node, F::Index);
        if literal(index, tree.cx.source).is_some() || index.is_some_and(|i| i.kind() == "number") {
            return false;
        }
        let Some(object) = tree.field(node, F::Object).map(|o| tree.cx.unwrapped(o)) else {
            return false;
        };
        self.called(node) && !self.data_object(object)
    }

    /// The value is called, constructed or tagged, also through `call`, `apply` or `bind` (with a
    /// name or a literal key), through parentheses, a type wrapper, `await`, a comma, a condition
    /// and a logical operator.
    fn called(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let mut at = node;
        while let Some(parent) = tree.parent(at) {
            let children = crate::tree::nodes::named_children(parent);
            match parent.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression"
                | "type_assertion"
                | "await_expression" => at = parent,
                "sequence_expression" if children.last().is_some_and(|l| l.id() == at.id()) => {
                    at = parent;
                }
                "ternary_expression" if children.first().is_some_and(|c| c.id() != at.id()) => {
                    at = parent;
                }
                "binary_expression" if self.logical(parent) => at = parent,
                "call_expression" | "new_expression" => {
                    return tree.is_field_of_parent(at, F::Function)
                        || tree.is_field_of_parent(at, F::Constructor);
                }
                "member_expression" if tree.is_field_of_parent(at, F::Object) => {
                    let name = tree.field(parent, F::Property).map(|p| tree.text(p));
                    return name.is_some_and(|name| call_member(&name));
                }
                "subscript_expression" if tree.is_field_of_parent(at, F::Object) => {
                    let key = tree.field(parent, F::Index).and_then(|i| self.text_of(i));
                    return key.is_some_and(|key| call_member(&key));
                }
                _ => return false,
            }
        }
        false
    }

    fn logical(&self, node: Node<'t>) -> bool {
        let operator = self.tree.field(node, F::Operator);
        operator.is_some_and(|op| matches!(op.kind(), "||" | "&&" | "??"))
    }

    /// A member or key that reads a descriptor or `Reflect.get` and is no direct callee: it is
    /// stored, passed or called through `call`, so its key is unknown.
    fn member_use(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let (object, name) = match node.kind() {
            "member_expression" => (
                tree.field(node, F::Object),
                tree.field(node, F::Property).map(|p| tree.text(p)),
            ),
            "subscript_expression" => (
                tree.field(node, F::Object),
                tree.field(node, F::Index).and_then(|i| self.text_of(i)),
            ),
            _ => return false,
        };
        let Some(name) = name else { return false };
        let on = |text: &str| {
            object.map(|o| tree.cx.unwrapped(o)).is_some_and(|o| {
                o.kind() == "identifier"
                    && tree.text(o) == text
                    && tree.binding_scope(o, text).is_none()
            })
        };
        let location = |at: Node<'t>| self.location_ref(at);
        let reads = REFLECTION.contains(&name.as_str()) || (name == "get" && on("Reflect"));
        let navigates = matches!(name.as_str(), "assign" | "replace")
            && object.is_some_and(|o| location(tree.cx.unwrapped(o)));
        (reads || navigates) && !self.direct_callee(node)
    }

    fn direct_callee(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        tree.parent(node).is_some_and(|parent| {
            parent.kind() == "call_expression" && tree.is_field_of_parent(node, F::Function)
        })
    }

    /// A free name of `ALIASED` that is passed, stored or returned.
    fn alias_escape(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let name = tree.text(node);
        if !ALIASED.contains(&name.as_str())
            || tree.in_type(node)
            || tree.declaration_name(node)
            || tree.binding_scope(node, &name).is_some()
        {
            return false;
        }
        let called = tree.parent(node).is_some_and(|parent| {
            matches!(parent.kind(), "call_expression" | "new_expression")
                && (tree.is_field_of_parent(node, F::Function)
                    || tree.is_field_of_parent(node, F::Constructor))
        });
        !called && self.escapes(node, false)
    }

    /// A member `location` (`window.location`, `document.location`) that is passed or stored.
    fn location_value(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let property = tree.field(node, F::Property).map(|p| tree.text(p));
        property.as_deref() == Some("location") && self.escapes(node, false)
    }

    /// `location`, `x.location` or `x["location"]`.
    fn location_ref(&self, at: Node<'t>) -> bool {
        let tree = self.tree;
        let at = tree.cx.unwrapped(at);
        match at.kind() {
            "identifier" => {
                tree.text(at) == "location" && tree.binding_scope(at, "location").is_none()
            }
            "member_expression" => tree
                .field(at, F::Property)
                .is_some_and(|p| tree.text(p) == "location"),
            "subscript_expression" => tree
                .field(at, F::Index)
                .and_then(|i| self.text_of(i))
                .is_some_and(|text| text == "location"),
            _ => false,
        }
    }

    /// A target that is `location`, `x.location`, `location.href` or `location[k]` with a
    /// run-time key.
    fn location_sink(&self, target: Node<'t>) -> bool {
        let tree = self.tree;
        match target.kind() {
            "identifier" => self.location_ref(target),
            "member_expression" | "subscript_expression" => {
                let on_location = tree
                    .field(target, F::Object)
                    .is_some_and(|object| self.location_ref(object));
                let key = if target.kind() == "member_expression" {
                    tree.field(target, F::Property).map(|p| tree.text(p))
                } else {
                    tree.field(target, F::Index).and_then(|i| self.text_of(i))
                };
                let runtime = target.kind() == "subscript_expression"
                    && tree
                        .field(target, F::Index)
                        .is_some_and(|i| i.kind() != "number" && self.text_of(i).is_none());
                self.location_ref(target)
                    || (on_location && (runtime || key.is_some_and(|key| key == "href")))
            }
            _ => false,
        }
    }

    /// `Reflect.get(o, k)`, `x.getOwnPropertyDescriptor(o, k)` with a key that is not a literal or
    /// that names `eval`, `Function` or `constructor`, `getOwnPropertyDescriptors`, and a method
    /// with a run-time key on `Object` or `Reflect`: they can reach `constructor`.
    fn runtime_reflection(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some((object, name)) = self.member_call(call) else {
            return false;
        };
        let key = tree.field(call, F::Arguments).and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .get(1)
                .copied()
        });
        let risky_key = || {
            key.is_none_or(|key| {
                literal(Some(key), tree.cx.source)
                    .is_none_or(|text| crate::script_window::CODE_NAMES.contains(&text.as_str()))
            })
        };
        match name.as_str() {
            "getOwnPropertyDescriptors" => true,
            "getOwnPropertyDescriptor" => risky_key(),
            "get" => object == "Reflect" && risky_key(),
            "*" => matches!(object.as_str(), "Object" | "Reflect"),
            _ => false,
        }
    }

    /// `location.assign(x)` or `replace(x)` with a spread or a value that is not a literal.
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
            "string" => self.text_of(key),
            "computed_property_name" => return false,
            _ => crate::script_window::cooked(&tree.text(key)),
        };
        !tree.in_type(node)
            && name.is_none_or(|name| crate::script_window::window_member_name(&name))
    }

    /// `open(x, …)` or `window.open(x, …)`, also through a comma, a condition or a wrapper, with a
    /// first argument that is a spread or no literal: a `javascript:` URL runs in the page for the
    /// target `_self` and in a same-origin window for each other target (AD-500).
    fn open_call(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(callee) = tree.field(call, F::Function) else {
            return false;
        };
        let global = self
            .callee_parts(callee)
            .into_iter()
            .any(|part| match part.kind() {
                "identifier" => {
                    tree.text(part) == "open" && tree.binding_scope(part, "open").is_none()
                }
                "member_expression" => {
                    let named = tree.field(part, F::Property).map(|p| tree.text(p));
                    named.as_deref() == Some("open")
                        && tree
                            .field(part, F::Object)
                            .is_some_and(|object| self.window_leaf(tree.cx.unwrapped(object)))
                }
                _ => false,
            });
        let first = tree.field(call, F::Arguments).and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .into_iter()
                .find(|argument| argument.kind() != "comment")
        });
        global && first.is_some_and(|first| literal(Some(first), tree.cx.source).is_none())
    }

    /// The object name and the member name of a call `object.name(…)`.
    fn member_call(&self, call: Node<'t>) -> Option<(String, String)> {
        let tree = self.tree;
        // A key that is no literal is `*`: it can be any member.
        let key = |at: Node<'t>| match at.kind() {
            "member_expression" => tree.field(at, F::Property).map(|p| tree.text(p)),
            "subscript_expression" => tree
                .field(at, F::Index)
                .map(|i| self.text_of(i).unwrap_or_else(|| "*".into())),
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
