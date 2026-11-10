// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The namespaces of a script: `var name;` followed by `(function (name) {...})(name || (name =
//! {}))` (`_script_namespaces`, `_script_namespace_initializer`).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::is_root;
use crate::script_syntax::Producer;
use crate::script_types::ScriptNamespace;
use crate::tree::nodes::named_children;

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// `_script_namespace_initializer`: the assignment of `(function (name) {...})(name || ...)`.
    fn namespace_initializer(&self, statement: Node<'t>, name: &str) -> Option<Node<'t>> {
        let tree = self.tree;
        if tree.k(statement) != K::ExpressionStatement {
            return None;
        }
        let call = statement.named_child(0)?;
        let wrapper = tree.strip_parentheses(tree.field(call, F::Function))?;
        let arguments = tree.field(call, F::Arguments)?;
        if tree.k(call) != K::CallExpression
            || tree.k(wrapper) != K::FunctionExpression
            || tree.has_child_kind(wrapper, K::Async)
            || arguments.named_child_count() != 1
        {
            return None;
        }
        let parameters = tree.field(wrapper, F::Parameters)?;
        if parameters.named_child_count() != 1 {
            return None;
        }
        let parameter = parameters.named_child(0)?;
        let pattern = tree.field(parameter, F::Pattern)?;
        if tree.k(parameter) != K::RequiredParameter
            || tree.k(pattern) != K::Identifier
            || tree.text(pattern) != name
            || tree.field(parameter, F::Value).is_some()
        {
            return None;
        }
        let argument = arguments.named_child(0)?;
        let publication = self.templates.publication(tree.cx, argument)?;
        if publication != name {
            return None;
        }
        tree.subtree(argument)
            .iter()
            .copied()
            .find(|node| tree.k(*node) == K::AssignmentExpression)
    }

    /// The nodes that write each name as a top-level binding or as a member of a root of the global
    /// object, in document order (the targets that `_script_namespaces` keeps for a name).
    fn names_written(&self) -> HashMap<String, Vec<Node<'t>>> {
        let tree = self.tree;
        let mut by_name: HashMap<String, Vec<Node<'t>>> = HashMap::new();
        for (node, target) in &self.targets {
            let route = tree.static_path(*target);
            match route.as_slice() {
                [name]
                    if tree
                        .bound_scope(*target, name)
                        .is_some_and(|scope| scope.id() == tree.root.id()) =>
                {
                    by_name.entry(name.clone()).or_default().push(*node);
                }
                [root, name] if is_root(root) && tree.script_free_in(*target, *target, false) => {
                    by_name.entry(name.clone()).or_default().push(*node);
                }
                _ => {}
            }
        }
        by_name
    }

    /// `_script_namespaces`: `var name;` followed by `(function (name) {...})(name || (name = {}))`.
    pub fn namespaces(&self) -> Vec<ScriptNamespace> {
        let tree = self.tree;
        let mut result = Vec::new();
        let mut written: Option<HashMap<String, Vec<Node<'t>>>> = None;
        let statements: Vec<Node> = named_children(tree.root)
            .into_iter()
            .filter(|node| tree.k(*node) != K::Comment)
            .collect();
        for pair in statements.windows(2) {
            let &[declaration, statement] = pair else {
                continue;
            };
            if tree.k(declaration) != K::VariableDeclaration {
                continue;
            }
            let variables: Vec<Node> = named_children(declaration)
                .into_iter()
                .filter(|node| tree.k(*node) == K::VariableDeclarator)
                .collect();
            let [variable] = variables.as_slice() else {
                continue;
            };
            let Some(name) = tree.field(*variable, F::Name) else {
                continue;
            };
            if tree.k(name) != K::Identifier
                || tree.field(*variable, F::Value).is_some()
                || tree.count(tree.root, &tree.text(name)) != 1
            {
                continue;
            }
            let spelling = tree.text(name);
            let Some(initializer) = self.namespace_initializer(statement, &spelling) else {
                continue;
            };
            let writes = written
                .get_or_insert_with(|| self.names_written())
                .get(&spelling);
            let only = writes.is_some_and(
                |nodes| matches!(nodes.as_slice(), [only] if only.id() == initializer.id()),
            );
            if only {
                result.push(ScriptNamespace {
                    name: spelling,
                    span: tree.span(*variable),
                    initialization: tree.span(initializer),
                });
            }
        }
        result
    }
}
