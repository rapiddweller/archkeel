// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The writes of a script: what it assigns, calls or leaves open (`_script_opaque_writes`,
//! `_script_intrinsic_effect`, `_script_declaration_write`, `_script_target_write`,
//! `_script_call_writes`, `_script_escape`, `_script_computed_dispatch`).

use std::collections::HashSet;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::references::literal;
use crate::script_scope::{is_callable_value, is_root, Tree};
use crate::script_types::Write;
use crate::source::Span;

/// `_SCRIPT_EFFECT_NAMES`: a name that reaches the global object or runs text as code.
pub(crate) fn is_effect_name(name: &str) -> bool {
    matches!(
        name,
        "constructor"
            | "eval"
            | "Function"
            | "Reflect"
            | "getPrototypeOf"
            | "getOwnPropertyDescriptor"
            | "getOwnPropertyDescriptors"
            | "defineProperty"
            | "defineProperties"
            | "setPrototypeOf"
            | "__proto__"
            | "setTimeout"
            | "setInterval"
    )
}

/// The name that a path writes: the member of an alias of the global object, or the first name.
fn written_name(path: &[String], alias: bool) -> Option<String> {
    if alias {
        path.get(1).cloned()
    } else {
        path.first().cloned()
    }
}

impl<'a, 't> Tree<'a, 't> {
    /// `_script_escape`: the value of the node leaves the place where it is written.
    pub(crate) fn script_escape(&self, node: Node<'t>) -> bool {
        let target = match self.parent(node) {
            Some(parent)
                if self.k(parent) == K::MemberExpression
                    && self.is_field_of_parent(node, F::Property) =>
            {
                parent
            }
            _ => node,
        };
        let Some(parent) = self.parent(target) else {
            return true;
        };
        let parent_kind = self.k(parent);
        if parent_kind == K::Pair && self.is_field_of_parent(target, F::Key) {
            return false;
        }
        if parent_kind == K::Arguments
            && self
                .parent(parent)
                .is_some_and(|call| self.calls_wrapper(call))
        {
            return false;
        }
        if (matches!(parent_kind, K::MemberExpression | K::SubscriptExpression)
            && self.is_field_of_parent(target, F::Object))
            || (parent_kind == K::UnaryExpression && self.has_child_kind(parent, K::Typeof))
        {
            return false;
        }
        !((matches!(
            parent_kind,
            K::AssignmentExpression | K::AugmentedAssignmentExpression
        ) && self.is_field_of_parent(target, F::Left))
            || parent_kind == K::UpdateExpression
            || (parent_kind == K::UnaryExpression && self.has_child_kind(parent, K::Delete)))
    }

    /// The callee of a call, without parentheses, is a wrapper of a script.
    fn calls_wrapper(&self, call: Node<'t>) -> bool {
        let callee = self.strip_parentheses(self.field(call, F::Function));
        callee.is_some_and(|callee| self.is_wrapper(callee))
    }

    /// The receiver of `a[b]` is a function or a class, or a name that binds one.
    fn callable_receiver(
        &self,
        node: Node<'t>,
        receiver: Node<'t>,
        callables: &HashSet<(usize, String)>,
    ) -> bool {
        if is_callable_value(self.k(receiver)) {
            return true;
        }
        let path = self.static_path(receiver);
        let Some(first) = path.first() else {
            return false;
        };
        self.bound_scope(node, first)
            .is_some_and(|scope| callables.contains(&(scope.id(), first.clone())))
    }

    /// `_script_computed_dispatch`: `a[b]` may reach a function that the script declares.
    fn computed_dispatch(&self, node: Node<'t>, callables: &HashSet<(usize, String)>) -> bool {
        let index = self.field(node, F::Index);
        if index.is_some_and(|index| matches!(self.k(index), K::String | K::TemplateString)) {
            return true;
        }
        let receiver = self.strip_parentheses(self.field(node, F::Object));
        if receiver.is_some_and(|receiver| self.callable_receiver(node, receiver, callables)) {
            return true;
        }
        // Getter effects are outside the declared source-binding contract.
        self.leads_to_call(node)
    }

    /// `_script_intrinsic_effect`.
    fn intrinsic_effect(&self, node: Node<'t>) -> bool {
        let kind = self.k(node);
        let parent = self.parent(node);
        let named = matches!(
            kind,
            K::Identifier | K::PropertyIdentifier | K::ShorthandPropertyIdentifier
        ) && !self.declaration_name(node)
            && !parent.is_some_and(|parent| {
                self.k(parent) == K::Pair && self.is_field_of_parent(node, F::Key)
            });
        if !named {
            return false;
        }
        let text = self.text(node);
        if !is_effect_name(&text) {
            return false;
        }
        let target = match parent {
            Some(parent)
                if self.k(parent) == K::MemberExpression
                    && self.is_field_of_parent(node, F::Property) =>
            {
                parent
            }
            _ => node,
        };
        let arguments = self.parent(target).and_then(|call| {
            (self.k(call) == K::CallExpression && self.is_field_of_parent(target, F::Function))
                .then(|| self.field(call, F::Arguments))
                .flatten()
        });
        let callback = arguments.and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .into_iter()
                .find(|argument| self.k(*argument) != K::Comment)
        });
        let timer = matches!(text.as_str(), "setTimeout" | "setInterval")
            && callback.is_some_and(|callback| {
                matches!(
                    self.k(callback),
                    K::FunctionExpression | K::GeneratorFunction | K::ArrowFunction
                )
            });
        !timer
    }

    /// `_script_opaque_writes`: the places where a script writes a name that is not known.
    pub(crate) fn opaque_writes(
        &self,
        node: Node<'t>,
        callables: &HashSet<(usize, String)>,
    ) -> Vec<Span> {
        let mut found = Vec::new();
        let kind = self.k(node);
        if matches!(
            kind,
            K::Identifier | K::PropertyIdentifier | K::ShorthandPropertyIdentifier
        ) && !self.cx.valid_unicode_member_name(node)
        {
            found.push(self.span(node));
        }
        if self.intrinsic_effect(node) {
            found.push(self.span(node));
        }
        if kind == K::SubscriptExpression {
            let receiver = self.field(node, F::Object);
            let text = literal(self.field(node, F::Index), self.cx.source);
            let effect = text.as_deref().is_some_and(is_effect_name);
            if effect
                || receiver.is_some_and(|receiver| self.script_free(receiver, node))
                || (text.is_none() && self.computed_dispatch(node, callables))
            {
                found.push(self.span(node));
            }
        }
        if kind == K::PairPattern {
            let key = self.field(node, F::Key);
            let text = literal(key, self.cx.source);
            let opaque = key.is_some_and(|key| {
                self.k(key) == K::ComputedPropertyName
                    || (self.k(key) == K::String && text.as_deref().is_none_or(is_effect_name))
            });
            if opaque {
                found.push(self.span(node));
            }
        }
        found
    }

    /// `_script_declaration_write`: a top-level declaration publishes its name.
    pub(crate) fn declaration_write(&self, node: Node<'t>) -> Option<Write> {
        if !matches!(
            self.k(node),
            K::VariableDeclarator | K::FunctionDeclaration | K::ClassDeclaration
        ) {
            return None;
        }
        if self.inside_function(node) {
            return None;
        }
        let name = self.field(node, F::Name)?;
        if self.k(name) != K::Identifier {
            return None;
        }
        let written = self.text(name);
        let published = (!is_root(&written)).then_some(written);
        Some((published, self.span(node)))
    }

    /// `_script_target_write`: the name that an assignment writes on the global object.
    pub(crate) fn target_write(
        &self,
        node: Node<'t>,
        target: Node<'t>,
        alias: &dyn Fn(&str) -> bool,
    ) -> Write {
        let mut path = self.static_path(target);
        if path.is_empty() && self.k(target) == K::SubscriptExpression {
            let receiver = self.field(target, F::Object);
            path = receiver.map_or_else(Vec::new, |receiver| self.static_path(receiver));
        }
        let name = path
            .first()
            .and_then(|first| written_name(&path, alias(first)));
        (name, self.span(node))
    }

    /// `_script_call_writes`: a global that a call receives as an argument may be written there.
    pub(crate) fn call_writes(&self, node: Node<'t>, wrapper_calls: &HashSet<usize>) -> Vec<Write> {
        let mut found = Vec::new();
        if self.k(node) != K::CallExpression || wrapper_calls.contains(&node.id()) {
            return found;
        }
        let Some(arguments) = self.field(node, F::Arguments) else {
            return found;
        };
        for argument in crate::tree::nodes::named_children(arguments) {
            let path = self.static_path(argument);
            let Some(first) = path.first() else {
                continue;
            };
            found.push((written_name(&path, is_root(first)), self.span(argument)));
        }
        found
    }
}
