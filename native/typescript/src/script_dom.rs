// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The DOM places that run a text that the file can build at run time (#1526, AD-792).
//!
//! A page runs a text as code in more places than `eval`: `document.write` after `document.open`,
//! a `javascript:` address of a link, a frame, an object or a form, and the markup of `insertHTML`.
//! Such code can write any global. The check below adds an unknown write for each place where the
//! text is no literal, and for each document that the file keeps or passes on, because no later
//! read of that value sees its `write`. A literal text is read by the text checks of
//! `script_code.rs`. Each of these values needs a page, so each form that reads a value is an
//! amplifier form (AD-540); a document member that runs a text is a direct form. Only
//! `script_declarations.rs` calls this check.

use tree_sitter::Node;

use crate::kinds::F;
use crate::references::literal;
use crate::script_names::bound_scope;
use crate::script_syntax::Producer;
use crate::script_tree::Tree;
use crate::script_window::{cooked, string_text, Reach, Written};
use crate::tree::cx::Cx;

/// The members of a document that run a text or open a window.
const DOCUMENT_CODE: [&str; 3] = ["write", "writeln", "open"];

/// The members whose value is an address that a page loads or runs on a click or a submit.
const ADDRESSES: [&str; 6] = ["href", "src", "action", "formAction", "data", "baseVal"];

/// The attributes, in lower case, whose value is such an address.
const ADDRESS_ATTRIBUTES: [&str; 6] = ["href", "src", "action", "formaction", "data", "xlink:href"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The DOM form at a node that is not a target, with its phrase: a document member that runs
    /// a text, a document that escapes, a pattern that takes a document, an address attribute with
    /// a value that is no literal, and `insertHTML` with markup that is no inert literal.
    pub(crate) fn dom_form(&self, node: Node<'t>) -> Option<(Written, &'static str)> {
        if self.tree.in_type(node) {
            return None;
        }
        let (reach, form) = match Node::kind(&node) {
            "member_expression" | "subscript_expression" if self.document_code(node) => (
                Some(Reach::Direct),
                "a document member that runs a text or opens a window",
            ),
            "member_expression" | "subscript_expression" | "identifier" => (
                self.document_value(node)
                    .filter(|_| self.value_escapes(node)),
                "a document that is passed on",
            ),
            "pair_pattern" | "shorthand_property_identifier_pattern" => (
                self.document_pattern(node),
                "a pattern that takes a document",
            ),
            "call_expression" => (
                self.address_call(node),
                "an address or markup that is no literal",
            ),
            _ => (None, ""),
        };
        reach.map(|reach| (reach.written(), form))
    }

    /// A write of an address member (`href`, `src`, `action`, `formAction`, `data`, `baseVal`)
    /// with a value that is no literal, from any target. `location` has its own check.
    pub(crate) fn address_target(&self, node: Node<'t>, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let target = Cx::unwrapped(&tree.cx, target);
        let name = self.key_name(target)?;
        let object = Tree::field(tree, target, F::Object).map(|o| Cx::unwrapped(&tree.cx, o));
        if !ADDRESSES.contains(&String::as_str(&name))
            || object.is_some_and(|o| self.names_location(o))
        {
            return None;
        }
        let plain = Node::kind(&node) == "assignment_expression"
            && Tree::field(tree, node, F::Left)
                .is_some_and(|left| Node::id(&Cx::unwrapped(&tree.cx, left)) == Node::id(&target));
        let literal_value =
            plain && literal(Tree::field(tree, node, F::Right), tree.cx.source).is_some();
        (!literal_value).then_some(Written::Amplified)
    }

    /// `write`, `writeln` or `open` of a document, with a name or a literal key, used in any way
    /// but the direct call `document.write(…)` that `script_code.rs` reads already.
    fn document_code(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(name) = self.key_name(node) else {
            return false;
        };
        let object = Tree::field(tree, node, F::Object).map(|o| Cx::unwrapped(&tree.cx, o));
        if !DOCUMENT_CODE.contains(&String::as_str(&name))
            || !object.is_some_and(|o| self.document(o))
        {
            return false;
        }
        let read_already = Node::kind(&node) == "member_expression"
            && name != "open"
            && tree.parent(node).is_some_and(|parent| {
                Node::kind(&parent) == "call_expression"
                    && tree.is_field_of_parent(node, F::Function)
            });
        !read_already
    }

    /// A value that can be the document of a page: the free name `document`, or a member
    /// `document`, `ownerDocument` or `contentDocument` of any value.
    fn document_value(&self, node: Node<'t>) -> Option<Reach> {
        let tree = self.tree;
        let document = match Node::kind(&node) {
            "identifier" => {
                let name = Tree::text(tree, node);
                name == "document"
                    && !tree.declaration_name(node)
                    && bound_scope(tree, node, &name).is_none()
            }
            _ => self.key_name(node).is_some_and(|name| document_name(&name)),
        };
        document.then_some(Reach::Amplified)
    }

    /// The value leaves its place, and it is not the target of a write.
    fn value_escapes(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let target = tree.parent(node).is_some_and(|parent| {
            matches!(
                Node::kind(&parent),
                "assignment_expression" | "augmented_assignment_expression"
            ) && tree.is_field_of_parent(node, F::Left)
        });
        !target && self.escapes(node, false)
    }

    /// A destructuring pattern that takes a document out of a value.
    fn document_pattern(&self, node: Node<'t>) -> Option<Reach> {
        let tree = self.tree;
        let key = match Node::kind(&node) {
            "pair_pattern" => Tree::field(tree, node, F::Key)?,
            _ => node,
        };
        let name = match Node::kind(&key) {
            "string" => string_text(self, key),
            _ => cooked(&Tree::text(tree, key)),
        };
        name.is_some_and(|name| document_name(&name))
            .then_some(Reach::Amplified)
    }

    /// `setAttribute(name, value)` and `setAttributeNS(ns, name, value)` of an address attribute
    /// with a value that is no literal; `execCommand('insertHTML', …)` with markup that is no
    /// inert literal, or with a command that is no literal.
    fn address_call(&self, call: Node<'t>) -> Option<Reach> {
        let tree = self.tree;
        let callee = Cx::unwrapped(&tree.cx, Tree::field(tree, call, F::Function)?);
        let name = self.key_name(callee)?;
        let text = |at: usize| self.argument(call, at).and_then(|a| string_text(self, a));
        let value_is_literal =
            |at: usize| literal(self.argument(call, at), tree.cx.source).is_some();
        let address = |name: Option<String>| {
            name.is_some_and(|name| {
                ADDRESS_ATTRIBUTES.contains(&String::as_str(&str::to_ascii_lowercase(&name)))
            })
        };
        match String::as_str(&name) {
            "setAttribute" => {
                (address(text(0)) && !value_is_literal(1)).then_some(Reach::Amplified)
            }
            "setAttributeNS" => {
                (address(text(1)) && !value_is_literal(2)).then_some(Reach::Amplified)
            }
            "execCommand" => {
                let insert =
                    text(0).is_none_or(|command| command.eq_ignore_ascii_case("insertHTML"));
                let markup = self.argument(call, 2);
                (insert && markup.is_some() && !self.plain_text(markup)).then_some(Reach::Direct)
            }
            _ => None,
        }
    }

    /// The cooked name of a dotted member or of a literal key.
    fn key_name(&self, node: Node<'t>) -> Option<String> {
        let tree = self.tree;
        match Node::kind(&node) {
            "member_expression" => cooked(&Tree::text(tree, Tree::field(tree, node, F::Property)?)),
            "subscript_expression" => string_text(self, Tree::field(tree, node, F::Index)?),
            _ => None,
        }
    }

    /// `location` or a member `location`: the navigation check of AD-508 reads its address.
    fn names_location(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        match Node::kind(&object) {
            "identifier" => Tree::text(tree, object) == "location",
            _ => self.key_name(object).as_deref() == Some("location"),
        }
    }
}

/// A member name whose value is a document on any object.
fn document_name(name: &str) -> bool {
    matches!(name, "document" | "ownerDocument" | "contentDocument")
}
