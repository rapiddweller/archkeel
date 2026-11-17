// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The attribute names that code stores on any value, for the lazy annotations of Python 3.14
//! (#1523, AD-802).
//!
//! On Python 3.14 a method annotation is evaluated when it is read, in the namespace of its class
//! (PEP 649). The namespace can get a name after the class statement: `Box.object = Hidden`,
//! `setattr(Box, "object", v)`, `type.__setattr__(Box, "object", v)`. A store does not say whether
//! its value is a class, so each attribute store counts. A store with a computed name, and a use
//! of `setattr` or `__setattr__` as a value, can write any name.

use std::collections::HashSet;

use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ExprContext, Identifier, ModModule, Stmt};

/// The functions that write an attribute by a name in an argument.
const WRITERS: [&str; 4] = ["setattr", "delattr", "__setattr__", "__delattr__"];

/// The attribute names that the files store, or every name.
#[derive(Default)]
pub(crate) struct ClassWrites {
    names: HashSet<String>,
    any: bool,
}

impl ClassWrites {
    /// Add the stores of one file.
    pub(super) fn add(&mut self, tree: &ModModule) {
        Walk(self).visit_body(&tree.body);
    }

    /// True when a class namespace can get `name` after the class statement.
    pub(crate) fn can_write(&self, name: &str) -> bool {
        self.any || self.names.contains(name)
    }
}

/// True when the module has `from __future__ import annotations`: its annotations are strings.
pub(crate) fn future_annotations(tree: &ModModule) -> bool {
    tree.body.iter().any(|stmt| {
        matches!(stmt, Stmt::ImportFrom(node) if node.level == 0
            && node.module.as_ref().is_some_and(|name| Identifier::as_str(name) == "__future__")
            && node.names.iter().any(|name| Identifier::as_str(&name.name) == "annotations"))
    })
}

struct Walk<'w>(&'w mut ClassWrites);

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Attribute(node) if node.ctx != ExprContext::Load => {
                self.0.names.insert(node.attr.to_string());
            }
            Expr::Call(node) if writer(&node.func) => {
                self.call(node);
                // The callee is read here; its arguments can hold more stores.
                for argument in &node.arguments.args {
                    self.visit_expr(argument);
                }
                for keyword in &node.arguments.keywords {
                    self.visit_expr(&keyword.value);
                }
                return;
            }
            // A writer used as a value can be called with any name.
            _ if writer(expr) => self.0.any = true,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

impl Walk<'_> {
    /// A call of a writer: the literal name in its first two arguments, or any name.
    fn call(&mut self, node: &ExprCall) {
        let literal = node
            .arguments
            .args
            .iter()
            .take(2)
            .find_map(|argument| match argument {
                Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
                _ => None,
            });
        match literal {
            Some(name) => {
                self.0.names.insert(name);
            }
            None => self.0.any = true,
        }
    }
}

/// True for `setattr`, `delattr` or an attribute `__setattr__` or `__delattr__`.
fn writer(expr: &Expr) -> bool {
    match expr {
        Expr::Name(name) => WRITERS[..2].contains(&Name::as_str(&name.id)),
        Expr::Attribute(node) => WRITERS[2..].contains(&Identifier::as_str(&node.attr)),
        _ => false,
    }
}
