// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declarations of a script: which names the file declares or writes, where an object that it
//! publishes gets its members (`_script_declarations`, `_script_local_definition`,
//! `_script_object_members`, `_script_write_alias_path`).
//!
//! The index of the declarations is in `script_index.rs`.

use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::definitions::Definition;
use crate::kinds::{F, K};
use crate::script_index::Key;
use crate::script_scope::{is_function, is_root};
use crate::script_syntax::Producer;
use crate::script_types::Member;
use crate::tree::nodes::named_children;

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// `f"{definition.parent}.{definition.name}" if definition.parent else definition.name`.
    pub(crate) fn qualified(&self, definition: &Definition) -> String {
        match definition.parent {
            Some(at) => {
                let parent = self.scopes.qualified(at);
                if parent.is_empty() {
                    definition.name.clone()
                } else {
                    format!("{parent}.{}", definition.name)
                }
            }
            None => definition.name.clone(),
        }
    }

    /// `_script_local_definition`: the one declaration of the name that a value refers to, when
    /// the scope binds the name once and nothing writes it.
    pub(crate) fn local_definition(
        &self,
        value: Node<'t>,
    ) -> Option<(Option<&'x Definition>, Node<'t>)> {
        let tree = self.tree;
        let name = tree.text(value);
        let scope = tree.bound_scope(value, &name)?;
        if tree.count(scope, &name) != 1 || !tree.cx.valid_unicode_member_name(value) {
            return None;
        }
        let key = (scope.id(), name);
        let declarations = self.index.declared.get(&key)?;
        let [declaration] = declarations.as_slice() else {
            return None;
        };
        let declaration = *declaration;
        if tree.k(declaration) == K::VariableDeclarator {
            let constant = tree
                .parent(declaration)
                .and_then(|parent| tree.field(parent, F::Kind))
                .is_some_and(|kind| tree.k(kind) == K::Const);
            if declaration.end_byte() > value.start_byte() || !constant {
                return None;
            }
        }
        if self.index.written.contains(&key) {
            return None;
        }
        match self.definitions_at(&tree.span(declaration)) {
            [] => Some((None, declaration)),
            [one] => Some((Some(*one), declaration)),
            _ => None,
        }
    }

    /// `_script_object_values`: `(name, value)` of an object literal with plain, distinct keys.
    pub(crate) fn object_values(&self, object: Node<'t>) -> Vec<(String, Node<'t>)> {
        let mut values: Vec<(String, Node<'t>)> = Vec::new();
        for member in named_children(object) {
            let Some(entry) = self.object_value(member) else {
                return Vec::new();
            };
            values.push(entry);
        }
        let names: HashSet<&str> = values.iter().map(|(name, _)| name.as_str()).collect();
        if names.len() == values.len() {
            values
        } else {
            Vec::new()
        }
    }

    /// The name and the value of one member of an object literal; `None` for any other member.
    fn object_value(&self, member: Node<'t>) -> Option<(String, Node<'t>)> {
        let tree = self.tree;
        match tree.k(member) {
            K::ShorthandPropertyIdentifier => Some((tree.text(member), member)),
            K::Pair => {
                let key = tree.field(member, F::Key)?;
                let value = tree.field(member, F::Value)?;
                (tree.k(key) == K::PropertyIdentifier).then(|| (tree.text(key), value))
            }
            _ => None,
        }
    }

    /// `_script_object_members`: the local definitions that an object literal publishes.
    pub(crate) fn object_members(&self, object: Node<'t>) -> Vec<Member> {
        let mut found = Vec::new();
        for (published, value) in self.object_values(object) {
            found.extend(self.published_member(published, value));
        }
        found
    }

    /// The member that a value publishes, when it names a local definition.
    fn published_member(&self, published: String, value: Node<'t>) -> Option<Member> {
        let tree = self.tree;
        if !matches!(
            tree.k(value),
            K::Identifier | K::ShorthandPropertyIdentifier
        ) {
            return None;
        }
        let (definition, declaration) = self.local_definition(value)?;
        if let Some(definition) = definition {
            return Some((
                published,
                self.qualified(definition),
                definition.span.clone(),
            ));
        }
        let initializer = tree.field(declaration, F::Value)?;
        matches!(tree.k(initializer), K::ArrowFunction | K::Object)
            .then(|| (published, tree.text(value), tree.span(declaration)))
    }

    /// `this` at the top of a function that the file calls once is the global object when its
    /// function is the owner.
    fn global_this(&self, target: Node<'t>, owner: Node<'t>) -> Option<Vec<String>> {
        let tree = self.tree;
        let found = tree
            .ancestors(target)
            .find(|parent| is_function(tree.k(*parent)) && tree.k(*parent) != K::ArrowFunction);
        found
            .is_some_and(|found| found.id() == owner.id())
            .then(Vec::new)
    }

    /// The object at the start of a chain of members; `None` for a member without an object.
    fn chain_start(&self, target: Node<'t>) -> Option<Node<'t>> {
        let tree = self.tree;
        let mut receiver = target;
        while tree.k(receiver) == K::MemberExpression {
            receiver = tree.field(receiver, F::Object)?;
        }
        Some(receiver)
    }

    /// The declarations of a name in a scope: the map of the caller, or the index of the file.
    fn listed_declarations(
        &self,
        key: &Key,
        declarations: Option<&HashMap<Key, Vec<Node<'t>>>>,
    ) -> Vec<Node<'t>> {
        let found = match declarations {
            Some(map) => map.get(key),
            None => self.index.variables.get(key),
        };
        found.cloned().unwrap_or_default()
    }

    /// The paths that the values of the declarations reach, for the declarations not yet seen.
    fn alias_origins(
        &self,
        listed: Vec<Node<'t>>,
        seen: &[usize],
        declarations: Option<&HashMap<Key, Vec<Node<'t>>>>,
        owner: Option<Node<'t>>,
    ) -> Vec<Vec<String>> {
        let tree = self.tree;
        let mut origins = Vec::new();
        for declaration in listed {
            if seen.contains(&declaration.id()) {
                continue;
            }
            let right = declarations.and_then(|_| tree.field(declaration, F::Right));
            let Some(value) = tree.field(declaration, F::Value).or(right) else {
                continue;
            };
            let mut deeper = seen.to_vec();
            deeper.push(declaration.id());
            origins.extend(self.write_alias_path(value, &deeper, declarations, owner));
        }
        origins
    }

    /// `_script_write_alias_path`: the path on the global object that an assignment target
    /// reaches through local aliases, `None` where it cannot be known.
    pub(crate) fn write_alias_path(
        &self,
        target: Node<'t>,
        seen: &[usize],
        declarations: Option<&HashMap<Key, Vec<Node<'t>>>>,
        global_this_owner: Option<Node<'t>>,
    ) -> Option<Vec<String>> {
        let tree = self.tree;
        let target = tree.unparenthesized(target);
        if let Some(owner) = global_this_owner.filter(|_| tree.k(target) == K::This) {
            return self.global_this(target, owner);
        }
        let path = tree.static_path(target);
        let first = path.first()?;
        let receiver = self.chain_start(target)?;
        if !tree.cx.valid_unicode_member_name(receiver) {
            return declarations.map(|_| Vec::new());
        }
        let Some(scope) = tree.bound_scope(receiver, first) else {
            let skip = usize::from(is_root(first));
            return Some(path.iter().skip(skip).cloned().collect());
        };
        let listed = self.listed_declarations(&(scope.id(), first.clone()), declarations);
        if declarations.is_none() && (tree.count(scope, first) != 1 || listed.len() != 1) {
            return None;
        }
        let origins = self.alias_origins(listed, seen, declarations, global_this_owner);
        let shortest = origins.into_iter().min_by_key(Vec::len)?;
        Some(
            shortest
                .into_iter()
                .chain(path.iter().skip(1).cloned())
                .collect(),
        )
    }
}
