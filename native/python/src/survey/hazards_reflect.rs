// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One-step aliases and literal reflection of import-bound module names.

use std::collections::HashMap;

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};

use crate::survey::value::assignment_parts;

type Bindings = HashMap<String, Vec<String>>;

pub(super) fn deleted_code(tree: &ModModule) -> bool {
    #[derive(Default)]
    struct Deleted(bool);
    impl<'a> Visitor<'a> for Deleted {
        fn visit_expr(&mut self, expr: &'a Expr) {
            self.0 |= matches!(expr, Expr::Name(node) if node.id.as_str() == "code" && node.ctx == ExprContext::Del);
            visitor::walk_expr(self, expr);
        }
    }
    let mut walk = Deleted::default();
    walk.visit_body(&tree.body);
    walk.0
}

/// Add aliases whose value directly names an imported binding, without following alias chains.
pub(super) fn aliases(tree: &ModModule, imports: &mut Bindings) {
    struct Walk<'a> {
        imports: &'a Bindings,
        aliases: Bindings,
    }
    impl Walk<'_> {
        fn add(&mut self, target: &Expr, value: &Expr) {
            let (Expr::Name(target), Expr::Name(value)) = (target, value) else {
                return;
            };
            if let Some(origins) = self.imports.get(value.id.as_str()) {
                self.aliases
                    .entry(target.id.to_string())
                    .or_default()
                    .extend(origins.clone());
            }
        }
    }
    impl<'a> Visitor<'a> for Walk<'_> {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            match stmt {
                Stmt::Assign(node) => node
                    .targets
                    .iter()
                    .for_each(|target| self.add(target, &node.value)),
                Stmt::AnnAssign(node) => node
                    .value
                    .iter()
                    .for_each(|value| self.add(&node.target, value)),
                _ => {}
            }
            visitor::walk_stmt(self, stmt);
        }
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::Named(node) = expr {
                self.add(&node.target, &node.value);
            }
            visitor::walk_expr(self, expr);
        }
    }
    let mut walk = Walk {
        imports,
        aliases: Bindings::new(),
    };
    walk.visit_body(&tree.body);
    for (name, origins) in walk.aliases {
        imports.entry(name).or_default().extend(origins);
    }
}

/// A visible imported module, or a direct assignment expression of one.
pub(super) fn module(expr: &Expr, bindings: &Bindings) -> bool {
    match expr {
        Expr::Name(node) => bindings.contains_key(node.id.as_str()),
        Expr::Named(node) => {
            matches!(&*node.value, Expr::Name(name) if bindings.contains_key(name.id.as_str()))
        }
        _ => false,
    }
}

fn text(expr: &Expr, expected: &str) -> bool {
    matches!(expr, Expr::StringLiteral(node) if node.value.to_str() == expected)
}

fn call<'a>(expr: &'a Expr, name: &str) -> Option<&'a [Expr]> {
    let Expr::Call(node) = expr else { return None };
    if !matches!(&*node.func, Expr::Name(id) if id.id.as_str() == name)
        || !node.arguments.keywords.is_empty()
    {
        return None;
    }
    Some(&node.arguments.args)
}

/// The functions and classes of the `code` module that run text (#1520).
const RUNNERS: [&str; 3] = ["interact", "InteractiveConsole", "InteractiveInterpreter"];

/// A runner of the `code` module on a name `code`, on a name that a file assigns from `code` or
/// from an attribute `code` (`c = provider.code`), or on an attribute `code` of any value: the scan
/// cannot prove that the value is not the module, so the call can import any module (#1520).
pub(super) fn runner(base: &Expr, attributes: &[&str], aliases: &HashSet<String>) -> bool {
    attributes.iter().enumerate().any(|(at, name)| {
        let before = match at {
            0 => matches!(base, Expr::Name(root)
                if root.id.as_str() == "code" || aliases.contains(root.id.as_str())),
            _ => attributes[at - 1] == "code",
        };
        before && RUNNERS.contains(name)
    })
}

/// The names that the file assigns from the name `code` or from an attribute `code`, in any scope.
pub(super) fn code_aliases(tree: &ModModule) -> HashSet<String> {
    struct Aliases(HashSet<String>);
    impl<'a> Visitor<'a> for Aliases {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            let (targets, value) = assignment_parts(stmt).unwrap_or_default();
            let code = value.is_some_and(|value| match value {
                Expr::Name(name) => name.id.as_str() == "code",
                Expr::Attribute(node) => node.attr.as_str() == "code",
                _ => false,
            });
            if code {
                let names = targets.into_iter().filter_map(|target| match target {
                    Expr::Name(name) => Some(name.id.to_string()),
                    _ => None,
                });
                self.0.extend(names);
            }
            visitor::walk_stmt(self, stmt);
        }
    }
    let mut found = Aliases(HashSet::new());
    found.visit_body(&tree.body);
    found.0
}

/// `getattr(m, "code")`, `vars(m)["code"]`, or `m.__dict__["code"]`.
pub(super) fn code(expr: &Expr, bindings: &Bindings) -> bool {
    if let Some([base, key]) = call(expr, "getattr") {
        return module(base, bindings) && text(key, "code");
    }
    let Expr::Subscript(node) = expr else {
        return false;
    };
    if !text(&node.slice, "code") {
        return false;
    }
    if let Some([base]) = call(&node.value, "vars") {
        return module(base, bindings);
    }
    matches!(&*node.value, Expr::Attribute(attr) if attr.attr.as_str() == "__dict__" && module(&attr.value, bindings))
}
