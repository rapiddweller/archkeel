// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A narrow proof that a module has no written class declarations (AD-726).

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};

/// Plain imports and undecorated functions can form the module body. A class anywhere, a
/// namespace escape, or an eagerly evaluated function header leaves the inventory unread.
pub(super) fn empty(tree: &ModModule) -> bool {
    let future = tree.body.iter().any(|stmt| {
        matches!(stmt, Stmt::ImportFrom(node) if node.level == 0
            && node.module.as_ref().is_some_and(|name| name.as_str() == "__future__")
            && node.names.iter().any(|name| name.name.as_str() == "annotations"))
    });
    let plain = tree.body.iter().all(|stmt| match stmt {
        Stmt::Import(_) | Stmt::ImportFrom(_) => true,
        Stmt::Expr(node) => matches!(&*node.value, Expr::StringLiteral(_)),
        Stmt::FunctionDef(node) => {
            let params = &node.parameters;
            let mut items = params
                .posonlyargs
                .iter()
                .chain(&params.args)
                .chain(&params.kwonlyargs);
            let unsafe_header = items
                .any(|p| p.default.is_some() || (!future && p.parameter.annotation.is_some()))
                || (!future
                    && (node.returns.is_some()
                        || params
                            .vararg
                            .iter()
                            .chain(&params.kwarg)
                            .any(|p| p.annotation.is_some())));
            node.decorator_list.is_empty() && node.type_params.is_none() && !unsafe_header
        }
        _ => false,
    });
    let mut walk = Walk::default();
    walk.visit_body(&tree.body);
    plain && !walk.classes && !walk.unsafe_namespace
}

/// A namespace operation in one module can change another module of the scan.
pub(in crate::survey) fn namespace_safe(tree: &ModModule) -> bool {
    let mut walk = Walk::default();
    walk.visit_body(&tree.body);
    !walk.unsafe_namespace
}

#[derive(Default)]
struct Walk {
    classes: bool,
    unsafe_namespace: bool,
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::ClassDef(_) => self.classes = true,
            Stmt::Global(_) => self.unsafe_namespace = true,
            Stmt::ImportFrom(node)
                if node.names.iter().any(|name| name.name.as_str() == "*")
                    || node
                        .module
                        .as_ref()
                        .is_some_and(|name| name.as_str() == "builtins") =>
            {
                self.unsafe_namespace = true;
            }
            Stmt::Import(node)
                if node
                    .names
                    .iter()
                    .any(|name| name.name.as_str() == "builtins") =>
            {
                self.unsafe_namespace = true;
            }
            Stmt::FunctionDef(node) if node.name.as_str() == "__getattr__" => {
                self.unsafe_namespace = true;
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node)
                if matches!(
                    node.id.as_str(),
                    "type"
                        | "exec"
                        | "eval"
                        | "globals"
                        | "locals"
                        | "vars"
                        | "setattr"
                        | "delattr"
                        | "__import__"
                        | "__builtins__"
                ) =>
            {
                self.unsafe_namespace = true;
            }
            Expr::Attribute(node)
                if node.ctx != ExprContext::Load || node.attr.as_str() == "__dict__" =>
            {
                self.unsafe_namespace = true;
            }
            Expr::Subscript(node) if node.ctx != ExprContext::Load => self.unsafe_namespace = true,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}
