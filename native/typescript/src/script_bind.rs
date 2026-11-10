// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bindings of the scopes of a script (`_script_bindings`, `_script_declaration_bindings`,
//! `_script_callable_bindings`).

use std::collections::HashSet;

use tree_sitter::Node;

use crate::import_bindings::ImportBinding;
use crate::kinds::{F, K};
use crate::scope::assignment_targets;
use crate::script_scope::{is_callable_value, is_function, is_scope, is_var_scope, Tree};
use crate::tree::nodes::named_children;

/// A scope and the pattern that it binds.
type Pattern<'t> = (Node<'t>, Node<'t>);

impl<'a, 't> Tree<'a, 't> {
    /// `_script_bindings`: the names that each scope binds, and the scopes that are not statically
    /// known. `nodes` is the whole tree, or the nodes that a closed envelope selects.
    pub fn bind(&mut self, nodes: &[Node<'t>], imports: &[ImportBinding]) {
        let mut patterns: Vec<Pattern<'t>> = Vec::new();
        for node in nodes.iter().copied() {
            self.patterns_of(node, &mut patterns);
        }
        let mut seen: HashSet<(usize, usize)> = HashSet::new();
        for (scope, pattern) in patterns {
            if seen.insert((scope.id(), pattern.id())) {
                self.bind_pattern(scope, pattern);
            }
        }
        let module = self.bindings.entry(self.root.id()).or_default();
        for item in imports {
            let count = module.entry(item.local.clone()).or_insert(0);
            *count = count.saturating_add(1);
        }
        self.index_scopes();
    }

    /// The names of a pattern are bound in the scope; a target that is not a plain name makes the
    /// scope ambiguous.
    fn bind_pattern(&mut self, scope: Node<'t>, pattern: Node<'t>) {
        self.bindings.entry(scope.id()).or_default();
        for target in assignment_targets(&self.cx, pattern) {
            let plain = matches!(
                self.k(target),
                K::Identifier | K::TypeIdentifier | K::ShorthandPropertyIdentifierPattern
            ) && self.cx.valid_unicode_member_name(target);
            if !plain {
                self.ambiguous.insert(scope.id());
                continue;
            }
            let name = self.text(target);
            let names = self.bindings.entry(scope.id()).or_default();
            let count = names.entry(name).or_insert(0);
            *count = count.saturating_add(1);
        }
    }

    /// The patterns that a node binds, with the scope of each.
    fn patterns_of(&mut self, node: Node<'t>, out: &mut Vec<Pattern<'t>>) {
        let kind = self.k(node);
        if kind == K::WithStatement {
            self.ambiguous.insert(node.id());
        }
        if is_function(kind) {
            let parameters = self.field(node, F::Parameters);
            out.extend(
                parameters
                    .into_iter()
                    .flat_map(named_children)
                    .map(|p| (node, p)),
            );
            out.extend(self.field(node, F::Parameter).map(|p| (node, p)));
        }
        if kind == K::CatchClause {
            out.extend(self.field(node, F::Parameter).map(|p| (node, p)));
        }
        if kind == K::ForInStatement {
            out.extend(self.for_in_pattern(node));
        }
        if matches!(
            kind,
            K::FunctionExpression | K::GeneratorFunction | K::Class
        ) {
            out.extend(self.field(node, F::Name).map(|name| (node, name)));
        }
        if matches!(
            kind,
            K::VariableDeclarator
                | K::FunctionDeclaration
                | K::GeneratorFunctionDeclaration
                | K::ClassDeclaration
        ) {
            self.declaration_bindings(node, out);
        }
    }

    /// The pattern of a `for (... in ...)` that declares it: `var` binds in the function.
    fn for_in_pattern(&self, node: Node<'t>) -> Option<Pattern<'t>> {
        let declaration = self.field(node, F::Kind)?;
        let left = self.field(node, F::Left)?;
        if self.k(declaration) != K::Var {
            return Some((node, left));
        }
        let scope = self
            .ancestors(node)
            .find(|parent| is_var_scope(self.k(*parent)));
        Some((scope.unwrap_or(self.root), left))
    }

    /// `_script_declaration_bindings`.
    fn declaration_bindings(&mut self, node: Node<'t>, out: &mut Vec<Pattern<'t>>) {
        let kind = self.k(node);
        let Some(name) = self.field(node, F::Name) else {
            self.ambiguous.insert(self.root.id());
            return;
        };
        let function_scoped = kind == K::VariableDeclarator
            && self
                .parent(node)
                .is_some_and(|parent| self.k(parent) == K::VariableDeclaration);
        let holds = |found: K| {
            if function_scoped {
                is_var_scope(found)
            } else {
                is_scope(found)
            }
        };
        let scope = self.ancestors(node).find(|parent| holds(self.k(*parent)));
        out.push((scope.unwrap_or(self.root), name));
        // Sloppy-script block functions can also bind in their enclosing var scope.
        if kind == K::FunctionDeclaration {
            let var_scope = self
                .ancestors(node)
                .find(|parent| is_var_scope(self.k(*parent)));
            out.push((var_scope.unwrap_or(self.root), name));
        }
    }

    /// `_script_callable_bindings`: the names that bind a function or a class, with their scope.
    pub fn callable_bindings(&self) -> HashSet<(usize, String)> {
        let mut result = HashSet::new();
        for node in self.nodes.iter().copied() {
            if let Some((scope, name)) = self.callable_binding(node) {
                result.insert((scope.id(), name));
            }
        }
        result
    }

    fn callable_binding(&self, node: Node<'t>) -> Option<(Node<'t>, String)> {
        let kind = self.k(node);
        let name = self.field(node, F::Name)?;
        let value = self.strip_parentheses(self.field(node, F::Value));
        let callable = is_callable_value(kind)
            || (kind == K::VariableDeclarator
                && value.is_some_and(|value| is_callable_value(self.k(value))));
        if !callable {
            return None;
        }
        let spelling = self.text(name);
        let scope = if self.binds(node, &spelling) {
            Some(node)
        } else {
            self.bound_scope(node, &spelling)
        };
        scope.map(|scope| (scope, spelling))
    }
}
