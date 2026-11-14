// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data exemption of the run-time key call (AD-500): a value that reaches no `Function`.
//!
//! A literal object or array that a name binds once is data, when nothing changes its prototype:
//! no `__proto__` key, no method, no write through the name, no argument, no store and no export.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_syntax::Producer;

/// The global objects that are no function and give no reflection (`Reflect` does): a computed
/// call on them reaches no `Function`.
const NAMESPACES: [&str; 5] = ["Math", "JSON", "Atomics", "Intl", "console"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// A literal object or array that a name binds once, that nothing writes through, that no
    /// call receives and that nothing else stores, or a namespace of the platform. Such a value
    /// reaches no `Function`: its prototype is `Object.prototype` (AD-500).
    pub(crate) fn data_object(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        match object.kind() {
            "object" | "array" => self.plain_literal(object),
            "identifier" => {
                let name = tree.text(object);
                if tree.binding_scope(object, &name).is_none() {
                    return NAMESPACES.contains(&name.as_str());
                }
                let Some(declaration) = self.sole_declaration(object) else {
                    return false;
                };
                self.sole_value(object).is_some_and(|value| {
                    matches!(value.kind(), "object" | "array")
                        && self.plain_literal(value)
                        && !self.exported(declaration)
                        && !self.tainted_data().contains(&declaration.id())
                })
            }
            _ => false,
        }
    }

    /// An object or array without a `__proto__` key, a computed key, a spread, a method, an
    /// accessor or a function that binds its own `this`: nothing in it changes its prototype.
    fn plain_literal(&self, literal: Node<'t>) -> bool {
        let tree = self.tree;
        crate::tree::nodes::named_children(literal)
            .into_iter()
            .all(|member| match member.kind() {
                "comment" | "shorthand_property_identifier" => true,
                "pair" => {
                    let key = tree.field(member, F::Key);
                    let name = key.map(|key| match key.kind() {
                        "string" => self.text_of(key),
                        "property_identifier" | "number" => Some(tree.text(key)),
                        _ => None,
                    });
                    name.flatten().is_some_and(|name| name != "__proto__")
                        && tree
                            .field(member, F::Value)
                            .is_none_or(|value| !self.binds_this(value))
                }
                "object"
                | "array"
                | "string"
                | "number"
                | "true"
                | "false"
                | "null"
                | "identifier"
                | "arrow_function"
                | "template_string"
                | "regex"
                | "unary_expression"
                | "binary_expression"
                | "member_expression"
                | "call_expression"
                | "subscript_expression"
                | "parenthesized_expression"
                | "as_expression" => !self.binds_this(member),
                _ => false,
            })
    }

    /// A function, a class or a generator that binds its own `this`.
    fn binds_this(&self, node: Node<'t>) -> bool {
        matches!(
            self.tree.cx.unwrapped(node).kind(),
            "function_expression" | "generator_function" | "class" | "method_definition"
        )
    }

    /// The declaration is below an `export`: another file can write through the name.
    fn exported(&self, declaration: Node<'t>) -> bool {
        let tree = self.tree;
        tree.ancestors(declaration)
            .take(3)
            .any(|node| node.kind() == "export_statement")
    }

    /// The declarations of literals that some use of the name can change or hand on: a write
    /// through the name, an argument, a store, a spread, an alias, a comparison or an export.
    fn tainted_data(&self) -> &std::collections::HashSet<usize> {
        self.data_taint.get_or_init(|| {
            let tree = self.tree;
            let mut found = std::collections::HashSet::new();
            for node in tree.nodes.iter().copied() {
                let reference = match node.kind() {
                    "identifier" => !tree.in_type(node) && !tree.declaration_name(node),
                    "shorthand_property_identifier" => true,
                    _ => false,
                };
                if !reference {
                    continue;
                }
                let Some(declaration) = self.sole_declaration(node) else {
                    continue;
                };
                if tree.k(declaration) == K::VariableDeclarator && !self.pure_read(node) {
                    found.insert(declaration.id());
                }
            }
            found
        })
    }

    /// The name is only the object of a member that is read, never written or deleted.
    fn pure_read(&self, name: Node<'t>) -> bool {
        let tree = self.tree;
        let mut at = name;
        loop {
            let Some(parent) = tree.parent(at) else {
                return false;
            };
            match parent.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression"
                | "type_assertion" => at = parent,
                "member_expression" | "subscript_expression"
                    if tree.is_field_of_parent(at, F::Object) =>
                {
                    return !self.written_through(parent);
                }
                _ => return false,
            }
        }
    }

    /// The member chain that ends at `member` is an assignment target, an update, a `delete`, or
    /// a pattern target.
    fn written_through(&self, member: Node<'t>) -> bool {
        let tree = self.tree;
        let mut top = member;
        while let Some(parent) = tree.parent(top) {
            let wrapper = matches!(
                parent.kind(),
                "parenthesized_expression" | "as_expression" | "non_null_expression"
            );
            let chain = matches!(parent.kind(), "member_expression" | "subscript_expression")
                && tree.is_field_of_parent(top, F::Object);
            if !(wrapper || chain) {
                break;
            }
            top = parent;
        }
        let Some(parent) = tree.parent(top) else {
            return false;
        };
        let left = |node: Node<'t>| {
            tree.field(node, F::Left)
                .is_some_and(|left| tree.cx.unwrapped(left).id() == tree.cx.unwrapped(top).id())
        };
        match parent.kind() {
            "assignment_expression" | "augmented_assignment_expression" | "for_in_statement" => {
                left(parent)
            }
            "update_expression" => true,
            "unary_expression" => tree.has_child_kind(parent, K::Delete),
            "array_pattern"
            | "object_pattern"
            | "pair_pattern"
            | "rest_pattern"
            | "object_assignment_pattern"
            | "assignment_pattern"
            | "spread_element" => true,
            _ => false,
        }
    }
}
