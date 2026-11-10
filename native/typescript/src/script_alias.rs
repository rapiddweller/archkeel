// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a script gives to a browser global or to a factory (`_script_aliases`,
//! `_script_alias_calls`, `_script_factory_uses`).
//!
//! Python walks the subtree of a scope for each alias. Here the references are grouped by name
//! once, and a scope is a range of the document order.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::members::children;
use crate::script_scope::is_root;
use crate::script_syntax::Producer;
use crate::script_types::ScriptAlias;
use crate::source::Span;

/// The calls, the reads and the escapes of a factory alias.
pub type Uses = (Vec<Span>, Vec<Span>, Vec<Vec<String>>);

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    pub fn optional_chain(&self, node: Node<'t>) -> bool {
        children(node)
            .into_iter()
            .any(|child| self.tree.k(child) == K::OptionalChain)
    }

    /// `_script_factory_publication_escape`: a pair of an object that the file publishes on the
    /// global object, when nothing writes below it.
    fn publication_escape(&self, pair: Node<'t>) -> Option<Vec<String>> {
        let tree = self.tree;
        let object = tree.parent(pair)?;
        let assignment = tree.parent(object)?;
        let key = tree.field(pair, F::Key)?;
        let target = tree.field(assignment, F::Left)?;
        if tree.k(object) != K::Object
            || tree.k(assignment) != K::AssignmentExpression
            || !tree.is_field_of_parent(object, F::Right)
            || tree.k(key) != K::PropertyIdentifier
        {
            return None;
        }
        let path = tree.static_path(target);
        let [root, member] = path.as_slice() else {
            return None;
        };
        if !is_root(root) {
            return None;
        }
        let prefix = vec![member.clone(), tree.text(key)];
        let written = self
            .refs
            .routes
            .iter()
            .any(|route| route.starts_with(&prefix));
        (!written).then_some(prefix)
    }

    /// The reference is a use of the binding of `scope`, and not the binding itself.
    fn uses_binding(&self, reference: Node<'t>, name: Node<'t>, scope: Node<'t>) -> bool {
        let spelling = self.tree.text(name);
        reference.id() != name.id()
            && self
                .tree
                .bound_scope(reference, &spelling)
                .is_some_and(|bound| bound.id() == scope.id())
    }

    /// `_script_factory_uses`: the calls, the reads and the escapes of a factory alias, or `None`
    /// where the alias is used in a way that the script facts cannot follow.
    fn factory_uses(&self, scope: Node<'t>, name: Node<'t>) -> Option<Uses> {
        let tree = self.tree;
        let mut uses: Uses = (Vec::new(), Vec::new(), Vec::new());
        for reference in self.refs.named(&tree.text(name), tree.range(scope)) {
            if self.uses_binding(reference, name, scope) {
                self.factory_use(reference, &mut uses)?;
            }
        }
        Some(uses)
    }

    /// One use of a factory alias; `None` where it is a use that the facts cannot follow.
    fn factory_use(&self, reference: Node<'t>, uses: &mut Uses) -> Option<()> {
        let tree = self.tree;
        let member = tree.parent(reference);
        let pair = member.filter(|member| {
            tree.k(*member) == K::Pair && tree.is_field_of_parent(reference, F::Value)
        });
        if let Some(pair) = pair {
            uses.2.push(self.publication_escape(pair)?);
            return Some(());
        }
        let member = member?;
        let property = tree.field(member, F::Property);
        if !self.plain_member_use(reference, member, property) || self.assigned_member(member) {
            return None;
        }
        let called = tree.parent(member).filter(|call| {
            tree.k(*call) == K::CallExpression && tree.is_field_of_parent(member, F::Function)
        });
        let Some(call) = called else {
            uses.1.extend(property.map(|property| tree.span(property)));
            return Some(());
        };
        if tree.has_child_kind(call, K::OptionalChainOperator) {
            return None;
        }
        uses.0.push(tree.span(call));
        Some(())
    }

    /// `reference.name` with a plain name, outside any scope that is not statically known.
    fn plain_member_use(
        &self,
        reference: Node<'t>,
        member: Node<'t>,
        property: Option<Node<'t>>,
    ) -> bool {
        let tree = self.tree;
        tree.cx.valid_unicode_member_name(reference)
            && tree.k(member) == K::MemberExpression
            && tree.is_field_of_parent(reference, F::Object)
            && tree.static_path(member).len() == 2
            && property.is_some_and(|property| tree.cx.valid_unicode_member_name(property))
            && !tree.in_ambiguous_scope(reference)
            && !self.optional_chain(member)
    }

    /// The member, with the members above it, is a target of an assignment.
    fn assigned_member(&self, member: Node<'t>) -> bool {
        let tree = self.tree;
        let mut used = member;
        while let Some(parent) = tree.parent(used) {
            if tree.k(parent) != K::MemberExpression {
                break;
            }
            used = parent;
        }
        let parent = tree.parent(used);
        parent.is_some_and(|parent| {
            tree.script_targets(parent)
                .iter()
                .any(|t| t.id() == used.id())
        })
    }

    /// `_script_alias_calls`: the calls through an alias, or `None` where it is used otherwise.
    fn alias_calls(&self, scope: Node<'t>, name: Node<'t>) -> Option<Vec<Span>> {
        let tree = self.tree;
        let range = tree.range(scope);
        if self.refs.any_bad(range) {
            return None;
        }
        let mut calls = Vec::new();
        for reference in self.refs.named(&tree.text(name), range) {
            if self.uses_binding(reference, name, scope) {
                calls.push(self.alias_call(reference)?);
            }
        }
        Some(calls)
    }

    /// The call `alias.member()` that a reference to an alias is; `None` for any other use.
    fn alias_call(&self, reference: Node<'t>) -> Option<Span> {
        let tree = self.tree;
        let target = tree.parent(reference)?;
        let call = tree.parent(target)?;
        let property = tree.field(target, F::Property);
        let chained = [target, call].into_iter().any(|node| {
            let marks = [K::OptionalChain, K::OptionalChainOperator];
            children(node)
                .into_iter()
                .any(|child| marks.contains(&tree.k(child)))
        });
        let proper = tree.k(target) == K::MemberExpression
            && tree.is_field_of_parent(reference, F::Object)
            && tree.static_path(target).len() == 2
            && property.is_some_and(|property| tree.cx.valid_unicode_member_name(property))
            && tree.k(call) == K::CallExpression
            && tree.is_field_of_parent(target, F::Function)
            && !tree.in_ambiguous_scope(reference);
        (proper && !chained).then(|| tree.span(call))
    }

    /// `_script_aliases`: `const name = window.member` and `const name = window.make()`.
    pub fn aliases(&self) -> Vec<ScriptAlias> {
        self.collect_nodes(|node| self.alias(node))
    }

    /// The alias that a declarator makes, when it makes one that the facts can follow.
    fn alias(&self, node: Node<'t>) -> Option<ScriptAlias> {
        let tree = self.tree;
        if tree.k(node) != K::VariableDeclarator || tree.in_error(node) {
            return None;
        }
        let declaration = tree.parent(node)?;
        let (name, value) = (tree.field(node, F::Name)?, tree.field(node, F::Value)?);
        let constant = tree
            .field(declaration, F::Kind)
            .is_some_and(|kind| tree.k(kind) == K::Const);
        if tree.k(declaration) != K::LexicalDeclaration
            || !constant
            || tree.k(name) != K::Identifier
            || !tree.cx.valid_unicode_member_name(name)
            || !matches!(tree.k(value), K::MemberExpression | K::CallExpression)
        {
            return None;
        }
        let factory = tree.k(value) == K::CallExpression;
        let target = if factory {
            tree.field(value, F::Function)?
        } else {
            value
        };
        let path = tree.static_path(target);
        let member = tree.field(target, F::Property)?;
        let spelling = tree.text(name);
        let scope = tree.bound_scope(node, &spelling)?;
        let shape = if factory {
            path.len() == 2 || path.len() == 3
        } else {
            matches!(path.as_slice(), [root, _] if is_root(root))
        };
        if !shape
            || !tree.cx.valid_unicode_member_name(member)
            || tree.count(scope, &spelling) != 1
            || !tree.script_free(target, node)
            || self.optional_chain(target)
            || self.optional_chain(value)
        {
            return None;
        }
        let mut alias = ScriptAlias {
            name: spelling,
            span: tree.span(node),
            reference_span: tree.span(member),
            path,
            calls: Vec::new(),
            factory,
            reads: Vec::new(),
            escapes: Vec::new(),
            complete: true,
        };
        if !factory {
            alias.calls = self.alias_calls(scope, name)?;
            return Some(alias);
        }
        alias.reference_span = tree.span(value);
        match self.factory_uses(scope, name) {
            Some((calls, reads, escapes)) => {
                (alias.calls, alias.reads, alias.escapes) = (calls, reads, escapes)
            }
            None => alias.complete = false,
        }
        Some(alias)
    }
}
