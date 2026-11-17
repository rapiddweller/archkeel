// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The forms of a lazy `__getattr__` that its run needs (AD-654, `lazy_return.rs`): no walrus,
//! each `globals()` value only a subscript store base, no jump out of a loop, and the global
//! names that the function reads.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ParameterWithDefault, Stmt, StmtFunctionDef};

use super::lazy_binds::Abs;

/// The module dunders that a `globals()` store must not write.
pub(super) const DUNDERS: [&str; 5] = [
    "__getattr__",
    "__spec__",
    "__package__",
    "__name__",
    "__path__",
];

/// True when a loop body has a `break` or `continue` at any depth.
pub(super) fn jumps(body: &[Stmt]) -> bool {
    let mut walk = Jumps(false);
    walk.visit_body(body);
    walk.0
}

struct Jumps(bool);

impl<'a> Visitor<'a> for Jumps {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.0 |= matches!(stmt, Stmt::Break(_) | Stmt::Continue(_));
        visitor::walk_stmt(self, stmt);
    }
}

/// True when the function has no walrus and each `globals()` value is only a subscript store
/// base: `globals()[k] = v`, or `g[k] = v` where `g` is bound only to `globals()`.
pub(super) fn closed(function: &StmtFunctionDef, map: &HashMap<String, Vec<Abs>>) -> bool {
    let mut walk = Uses { map, ok: true };
    walk.visit_body(&function.body);
    walk.ok
}

struct Uses<'a> {
    map: &'a HashMap<String, Vec<Abs>>,
    ok: bool,
}

impl Uses<'_> {
    fn alias(&self, name: &str) -> bool {
        self.map
            .get(name)
            .is_some_and(|all| all.iter().all(|abs| *abs == Abs::Globals))
    }

    fn globals(expr: &Expr) -> bool {
        matches!(expr, Expr::Call(call) if matches!(&*call.func,
            Expr::Name(name) if name.id.as_str() == "globals"))
    }

    fn base(&self, expr: &Expr) -> bool {
        Self::globals(expr) || matches!(expr, Expr::Name(name) if self.alias(name.id.as_str()))
    }

    /// A store into `globals()` or an alias, or the binding of an alias: true when handled.
    fn assign(&mut self, node: &ruff_python_ast::StmtAssign) -> bool {
        match node.targets.as_slice() {
            [Expr::Subscript(target)] if self.base(&target.value) => {
                self.visit_expr(&target.slice);
                self.visit_expr(&node.value);
                true
            }
            [Expr::Name(name)] if Self::globals(&node.value) => {
                self.ok &= self.alias(name.id.as_str());
                true
            }
            _ => false,
        }
    }
}

impl<'a> Visitor<'a> for Uses<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let handled = matches!(stmt, Stmt::Assign(node) if self.assign(node));
        if !handled {
            visitor::walk_stmt(self, stmt);
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Named(_) => self.ok = false,
            Expr::Name(name) if self.alias(name.id.as_str()) => self.ok = false,
            Expr::Name(name) if name.id.as_str() == "globals" => self.ok = false,
            _ => visitor::walk_expr(self, expr),
        }
    }
}

/// The global names that the function reads, and the module dunders: a `globals()` store must
/// not rebind one of them.
pub(super) fn global_reads(
    function: &StmtFunctionDef,
    locals: &HashSet<String>,
) -> HashSet<String> {
    let mut walk = Reads(locals, HashSet::new());
    walk.visit_body(&function.body);
    let mut found = walk.1;
    found.extend(DUNDERS.map(str::to_owned));
    found
}

struct Reads<'a>(&'a HashSet<String>, HashSet<String>);

impl<'a> Visitor<'a> for Reads<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if node.ctx == ExprContext::Load && !self.0.contains(node.id.as_str()) {
                self.1.insert(node.id.to_string());
            }
        }
        visitor::walk_expr(self, expr);
    }
}

/// The one parameter of a function that takes no other kind: no positional-only, keyword-only,
/// `*` or `**` parameter. Its default is the reader's to check.
pub(super) fn plain_parameter(function: &StmtFunctionDef) -> Option<&ParameterWithDefault> {
    let parameters = &function.parameters;
    let plain = parameters.posonlyargs.is_empty()
        && parameters.kwonlyargs.is_empty()
        && parameters.vararg.is_none()
        && parameters.kwarg.is_none();
    match parameters.args.as_slice() {
        [one] if plain => Some(one),
        _ => None,
    }
}
