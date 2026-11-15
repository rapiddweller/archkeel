// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One-step aliases and literal reflection of import-bound module names.

use std::collections::HashMap;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};

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
