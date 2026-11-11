// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a script destructures from the global object and what its factory functions return
//! (`_script_destructures`, `_script_factories`).

use tree_sitter::Node;

use crate::definitions::DefinitionKind;
use crate::kinds::{F, K};
use crate::script_scope::is_root;
use crate::script_syntax::Producer;
use crate::script_types::{FactoryMember, Member, ScriptDestructure, ScriptFactory};
use crate::tree::nodes::named_children;

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// `_script_destructures`: `const { a, b } = window.object`.
    pub fn destructures(&self) -> Vec<ScriptDestructure> {
        self.collect_nodes(|node| self.destructure(node))
    }

    /// The destructuring that a declarator makes, when its members are names that the file binds
    /// once.
    fn destructure(&self, node: Node<'t>) -> Option<ScriptDestructure> {
        let tree = self.tree;
        if tree.k(node) != K::VariableDeclarator {
            return None;
        }
        let (name, value) = (tree.field(node, F::Name)?, tree.field(node, F::Value)?);
        let kind = tree.field(tree.parent(node)?, F::Kind)?;
        if tree.k(name) != K::ObjectPattern
            || tree.k(value) != K::MemberExpression
            || tree.k(kind) != K::Const
        {
            return None;
        }
        let path = tree.static_path(value);
        let property = tree.field(value, F::Property)?;
        let [root, _] = path.as_slice() else {
            return None;
        };
        if !is_root(root) || !tree.script_free(value, node) {
            return None;
        }
        let members = self.destructured_members(name, node)?;
        (!members.is_empty()).then(|| ScriptDestructure {
            span: tree.span(property),
            path,
            members,
        })
    }

    /// The members of an object pattern; `None` where one of them is not a name that the file
    /// binds once.
    fn destructured_members(&self, pattern: Node<'t>, node: Node<'t>) -> Option<Vec<Member>> {
        let tree = self.tree;
        let mut members = Vec::new();
        for pair in named_children(pattern) {
            let shorthand = tree.k(pair) == K::ShorthandPropertyIdentifierPattern;
            let key = if shorthand {
                Some(pair)
            } else {
                tree.field(pair, F::Key)
            };
            let local = if shorthand {
                Some(pair)
            } else {
                tree.field(pair, F::Value)
            };
            let (key, local) = (key?, local?);
            let plain = matches!(
                tree.k(local),
                K::Identifier | K::ShorthandPropertyIdentifierPattern
            ) && tree.cx.valid_unicode_member_name(key)
                && tree.cx.valid_unicode_member_name(local);
            let spelling = tree.text(local);
            let bound = tree
                .bound_scope(node, &spelling)
                .is_some_and(|scope| tree.count(scope, &spelling) == 1);
            if !plain || !bound {
                return None;
            }
            members.push((tree.text(key), spelling, tree.span(key)));
        }
        Some(members)
    }

    /// `_script_factories`: `function make() { return { a, b: x.y }; }` and what it publishes.
    pub fn factories(&self) -> Vec<ScriptFactory> {
        self.collect_nodes(|node| self.factory(node))
    }

    /// The only `return` of a function declaration, when it is a statement of the body and
    /// returns an object literal.
    fn returned_object(&self, function: Node<'t>, body: Node<'t>) -> Option<Node<'t>> {
        let tree = self.tree;
        let (start, end) = tree.range(body);
        let list = self.refs.returns.get(&function.id())?;
        let inside = |item: &&Node<'t>| (start..end).contains(&tree.at(**item));
        let mut returns = list.iter().filter(inside);
        let only = *returns.next()?;
        let in_body = tree
            .parent(only)
            .is_some_and(|parent| parent.id() == body.id());
        if returns.next().is_some() || !in_body || only.named_child_count() != 1 {
            return None;
        }
        only.named_child(0)
            .filter(|object| tree.k(*object) == K::Object)
    }

    /// The factory that a function declaration is, when it returns an object literal.
    fn factory(&self, node: Node<'t>) -> Option<ScriptFactory> {
        let tree = self.tree;
        if tree.k(node) != K::FunctionDeclaration || tree.has_child_kind(node, K::Async) {
            return None;
        }
        let definition = self.definitions_at(&tree.span(node)).last().copied()?;
        let body = tree.field(node, F::Body)?;
        let object = self.returned_object(node, body)?;
        let name = self.qualified(definition);
        let members = self
            .object_values(object)
            .into_iter()
            .filter_map(|(published, value)| self.factory_member(&name, published, value))
            .collect();
        Some(ScriptFactory {
            name,
            span: definition.span.clone(),
            members,
        })
    }

    /// A member of a factory: a local definition, or a member that is forwarded from another
    /// object.
    fn factory_member(
        &self,
        factory: &str,
        published: String,
        value: Node<'t>,
    ) -> Option<FactoryMember> {
        let tree = self.tree;
        let named = matches!(
            tree.k(value),
            K::Identifier | K::ShorthandPropertyIdentifier
        );
        let local = if named {
            self.local_definition(value)
        } else {
            None
        };
        if let Some((local, declaration)) = local {
            let initializer = tree.field(declaration, F::Value);
            let target = match local {
                Some(local) => self.qualified(local),
                None => format!("{factory}.{}", tree.text(value)),
            };
            let callable = local.is_some_and(|local| local.kind == DefinitionKind::Function)
                || initializer.is_some_and(|node| tree.k(node) == K::ArrowFunction);
            return Some(FactoryMember {
                name: published,
                span: tree.span(value),
                target: Some(target),
                target_span: Some(tree.span(declaration)),
                forwarded_span: None,
                callable,
            });
        }
        if tree.k(value) != K::MemberExpression || tree.static_path(value).len() != 2 {
            return None;
        }
        let property = tree.field(value, F::Property)?;
        Some(FactoryMember {
            name: published,
            span: tree.span(value),
            target: None,
            target_span: None,
            forwarded_span: Some(tree.span(property)),
            callable: false,
        })
    }
}
