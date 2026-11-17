// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A value read with a run-time key that a later call can reach (AD-758, #1547).
//!
//! `o[k]` with a key that can name `constructor` is `Function` when `o` is a function. A direct
//! call of it is a key call (AD-508 rule 2). This check follows the value after the read: through
//! a wrapper, a local name, an array or object literal that holds it, and the members `call`,
//! `apply` and `bind`. A call of the value is the direct form. A use that only measures the value
//! (`typeof`, a comparison, a condition, a member with another name, a text) ends the walk. Each
//! other use (an argument, a `return`, a write to a member or to a name of another scope, an
//! export) leaves this walk, so it is the direct form too.

use std::collections::HashSet;

use tree_sitter::Node;

use crate::kinds::F;
use crate::script_names::bound_scope;
use crate::script_syntax::Producer;

/// The steps that one walk may take before it gives the direct form.
const BUDGET: usize = 256;

/// The members of a function that call it, or that give a function that calls it.
fn calls_it(name: &str) -> bool {
    matches!(name, "call" | "apply" | "bind")
}

/// What the walk follows: the value itself, or a literal that holds it in some element.
#[derive(Clone, Copy, PartialEq)]
enum Carrier {
    Value,
    Holder,
}

/// What one use of a carrier gives.
enum Use<'t> {
    /// The use cannot call the value.
    Ends,
    /// The value can be called, or it leaves the walk.
    Reaches,
    /// The walk goes on with these nodes.
    Next(Vec<(Node<'t>, Carrier)>),
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// `o[k]` with a run-time key, read and not called at once, whose value a later call can
    /// reach or that leaves the walk. A direct call is `runtime_key_call`.
    pub(crate) fn looked_up_call(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(object) = self.runtime_object(node) else {
            return false;
        };
        if self.namespace(object) || tree.in_type(node) || self.written_target(node) {
            return false;
        }
        let mut pending = vec![(node, Carrier::Value)];
        let mut seen = HashSet::new();
        while let Some((at, carrier)) = pending.pop() {
            if !seen.insert((at.id(), carrier == Carrier::Value)) {
                continue;
            }
            if seen.len() > BUDGET {
                return true;
            }
            match self.use_of(at, carrier) {
                Use::Ends => {}
                Use::Reaches => return true,
                Use::Next(next) => pending.extend(next),
            }
        }
        false
    }

    /// The node is the target of a write: an assignment, a pattern or the left of a `for`.
    fn written_target(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(parent) = tree.parent(node) else {
            return false;
        };
        match parent.kind() {
            "assignment_expression" | "augmented_assignment_expression" | "for_in_statement" => {
                tree.is_field_of_parent(node, F::Left)
            }
            "array_pattern" | "rest_pattern" => true,
            "pair_pattern" => tree.is_field_of_parent(node, F::Value),
            "assignment_pattern" => tree.is_field_of_parent(node, F::Left),
            _ => false,
        }
    }

    /// The node that gives the value of `node` after the wrappers that pass it on unchanged:
    /// parentheses, a type wrapper, `await`, the last of a comma, a branch of a condition and an
    /// operand of `||`, `&&` and `??`.
    fn outer(&self, node: Node<'t>) -> Node<'t> {
        let tree = self.tree;
        let mut at = node;
        while let Some(parent) = tree.parent(at) {
            let children = crate::tree::nodes::named_children(parent);
            let passes = match parent.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression"
                | "type_assertion"
                | "await_expression" => true,
                "sequence_expression" => children.last().is_some_and(|l| l.id() == at.id()),
                "ternary_expression" => children.first().is_some_and(|c| c.id() != at.id()),
                "binary_expression" => tree
                    .field(parent, F::Operator)
                    .is_some_and(|op| matches!(op.kind(), "||" | "&&" | "??")),
                _ => false,
            };
            if !passes {
                break;
            }
            at = parent;
        }
        at
    }

    /// What the parent of a carrier does with it.
    fn use_of(&self, node: Node<'t>, carrier: Carrier) -> Use<'t> {
        let tree = self.tree;
        let at = self.outer(node);
        let Some(parent) = tree.parent(at) else {
            return Use::Reaches;
        };
        let field = |name: F| tree.is_field_of_parent(at, name);
        match (parent.kind(), carrier) {
            ("expression_statement", _) => Use::Ends,
            ("member_expression" | "subscript_expression", Carrier::Holder) if field(F::Object) => {
                Use::Next(vec![(parent, Carrier::Value)])
            }
            ("member_expression" | "subscript_expression", Carrier::Value) if field(F::Object) => {
                self.member_of_value(parent)
            }
            ("subscript_expression", _) if field(F::Index) => Use::Ends,
            ("variable_declarator", _) if field(F::Value) => self.declared(parent, carrier),
            ("assignment_expression", _) if field(F::Right) => self.assigned(parent, carrier),
            ("augmented_assignment_expression", _) if field(F::Right) => {
                let logical = tree
                    .field(parent, F::Operator)
                    .is_some_and(|op| matches!(op.kind(), "||=" | "&&=" | "??="));
                if logical {
                    self.assigned(parent, carrier)
                } else {
                    Use::Ends
                }
            }
            ("array" | "object", _) => Use::Next(vec![(parent, Carrier::Holder)]),
            ("pair", _) if field(F::Value) => self.held(parent),
            ("spread_element", _) => self.held(parent),
            (_, Carrier::Value) => self.measured(parent, at),
            _ => Use::Reaches,
        }
    }

    /// A use of the value that cannot call it, or a call of it.
    fn measured(&self, parent: Node<'t>, at: Node<'t>) -> Use<'t> {
        let tree = self.tree;
        let field = |name: F| tree.is_field_of_parent(at, name);
        match parent.kind() {
            "call_expression" if field(F::Function) => Use::Reaches,
            "new_expression" if field(F::Constructor) => Use::Reaches,
            "unary_expression"
            | "binary_expression"
            | "update_expression"
            | "template_substitution"
            | "computed_property_name" => Use::Ends,
            "for_in_statement" if field(F::Right) => Use::Ends,
            "ternary_expression" | "if_statement" | "while_statement" | "do_statement" => Use::Ends,
            "for_statement" if !field(F::Body) => Use::Ends,
            _ => Use::Reaches,
        }
    }

    /// `value.name` or `value['name']`: `call`, `apply` and `bind` call the value, each other
    /// member is a value that no key named.
    fn member_of_value(&self, member: Node<'t>) -> Use<'t> {
        let tree = self.tree;
        let name = match member.kind() {
            "member_expression" => tree.field(member, F::Property).map(|p| tree.text(p)),
            _ => tree.field(member, F::Index).and_then(|i| self.text_of(i)),
        };
        match name {
            Some(name) if calls_it(&name) => Use::Next(vec![(member, Carrier::Value)]),
            Some(_) => Use::Ends,
            // A run-time key on the value is a read of its own (`o[a][b]` is a chain).
            None => Use::Ends,
        }
    }

    /// A pair or a spread of an array or object literal holds the value: the walk follows the
    /// literal. A spread in an argument list or a JSX element leaves the walk.
    fn held(&self, part: Node<'t>) -> Use<'t> {
        match self.tree.parent(part) {
            Some(literal) if matches!(literal.kind(), "array" | "object") => {
                Use::Next(vec![(literal, Carrier::Holder)])
            }
            _ => Use::Reaches,
        }
    }

    /// `const p = carrier`: the uses of `p`. A pattern of the value with plain names other than
    /// `call`, `apply` and `bind` gives members that no key named; any other pattern leaves.
    fn declared(&self, declarator: Node<'t>, carrier: Carrier) -> Use<'t> {
        let tree = self.tree;
        let Some(name) = tree.field(declarator, F::Name) else {
            return Use::Reaches;
        };
        let exported = tree
            .parent(declarator)
            .and_then(|declaration| tree.parent(declaration))
            .is_some_and(|above| above.kind() == "export_statement");
        if exported {
            return Use::Reaches;
        }
        match (name.kind(), carrier) {
            ("identifier", _) => self.uses_of(name, carrier),
            ("object_pattern", Carrier::Value) if self.plain_pattern(name) => Use::Ends,
            ("array_pattern", Carrier::Value) => Use::Ends,
            _ => Use::Reaches,
        }
    }

    /// An object pattern whose keys are plain names other than `call`, `apply` and `bind`.
    fn plain_pattern(&self, pattern: Node<'t>) -> bool {
        let tree = self.tree;
        crate::tree::nodes::named_children(pattern)
            .into_iter()
            .all(|part| match part.kind() {
                "shorthand_property_identifier_pattern" | "object_assignment_pattern" => {
                    !calls_it(&tree.text(part))
                }
                "pair_pattern" => tree
                    .field(part, F::Key)
                    .filter(|key| key.kind() != "computed_property_name")
                    .and_then(|key| {
                        self.text_of(key)
                            .or_else(|| crate::script_window::cooked(&tree.text(key)))
                    })
                    .is_some_and(|key| !calls_it(&key)),
                "rest_pattern" | "comment" => true,
                _ => false,
            })
    }

    /// `p = carrier`: the uses of the binding of `p`; a free name or a member leaves the walk.
    fn assigned(&self, assignment: Node<'t>, carrier: Carrier) -> Use<'t> {
        let tree = self.tree;
        match tree
            .field(assignment, F::Left)
            .map(|l| tree.cx.unwrapped(l))
        {
            Some(left) if left.kind() == "identifier" => self.uses_of(left, carrier),
            _ => Use::Reaches,
        }
    }

    /// Each reference to the binding of `name` in its scope. A free name and a name with an
    /// escape leave the walk. A name of a script leaves it too: a top-level name of a script is a
    /// global that another file can call, and `with` can give a name to an object. A module is
    /// strict code, so it has no `with` and its `eval` declares no name.
    fn uses_of(&self, name: Node<'t>, carrier: Carrier) -> Use<'t> {
        let tree = self.tree;
        let text = tree.text(name);
        let Some(scope) = bound_scope(tree, name, &text) else {
            return Use::Reaches;
        };
        let range = tree.range(scope);
        if !self.module_syntax || self.refs.any_bad(range) {
            return Use::Reaches;
        }
        let uses = self
            .refs
            .named(&text, range)
            .filter(|reference| reference.id() != name.id())
            .filter(|reference| {
                bound_scope(tree, *reference, &text).is_some_and(|bound| bound.id() == scope.id())
            })
            .filter(|reference| !self.written_target(*reference) && !self.declared_name(*reference))
            .map(|reference| (reference, carrier))
            .collect();
        Use::Next(uses)
    }

    /// The node is the name of a declaration (`var p` again, a function or a parameter).
    fn declared_name(&self, node: Node<'t>) -> bool {
        self.tree.declaration_name(node)
    }
}

#[cfg(test)]
#[path = "script_lookup_tests.rs"]
mod tests;
