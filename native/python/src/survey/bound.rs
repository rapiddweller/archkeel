// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a module body may bind, at any depth (AD-504): the one function that both the
//! package shadow rule (`package_body.rs`) and the proof of a re-export (`routes.rs`) read.
//!
//! Python binds a module attribute by a statement of the module scope in any compound statement
//! (`if`, `try`, `for`, `with`, `match`), by each target form, by a walrus, by `del`, and by a
//! function that declares the name `global`. A name has one *plain* binder when exactly one
//! statement binds it and that statement is a `def`, `class`, `import` or `name = value` directly
//! in the module body. Any other binding makes the name ambiguous: the survey cannot say what the
//! attribute is when the module runs. A star import binds names that the survey cannot list.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{ExceptHandler, Expr, ExprContext, Parameter, Pattern, Stmt, StmtImportFrom};
use ruff_text_size::{Ranged, TextSize};

use super::binders::{
    bind_handler, bind_handler_and_pattern, bind_pattern, declared, import_bindings, Bind,
};

/// One statement that binds a name at module scope.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Site {
    /// The statement is directly in the module body: no `if`, `try`, `for`, `with` or `match`.
    plain: bool,
    start: TextSize,
}

/// The module-scope binders of one module body.
#[derive(Default)]
pub(super) struct Bound {
    sites: HashMap<String, Vec<Site>>,
    /// Names that a function of the module declares `global` (a write binds the module name).
    globals: HashSet<String>,
    /// A star import binds names that cannot be listed.
    pub(super) opaque: bool,
    /// A top-level `__getattr__` can give any attribute.
    pub(super) getattr: bool,
}

impl Bound {
    pub(super) fn of(body: &[Stmt]) -> Self {
        let mut walk = Walk::default();
        walk.visit_body(body);
        walk.bound
    }

    /// True when `start` is the one statement that binds `name`, it is a plain statement of the
    /// module body, and nothing else can bind the name.
    pub(super) fn sole(&self, name: &str, start: TextSize) -> bool {
        !self.opaque
            && !self.globals.contains(name)
            && self.sites.get(name).is_some_and(
                |sites| matches!(sites.as_slice(), [only] if only.plain && only.start == start),
            )
    }

    /// Each name that a statement of the module scope, or a `global` declaration, binds.
    pub(super) fn names(&self) -> HashSet<String> {
        let sites = self.sites.keys().cloned();
        sites.chain(self.globals.iter().cloned()).collect()
    }

    /// The names that only the statement at `start` binds (`from . import name`, AD-53).
    pub(super) fn only_at(&self, name: &str, start: TextSize) -> bool {
        self.sites
            .get(name)
            .is_some_and(|sites| matches!(sites.as_slice(), [only] if only.start == start))
            && !self.globals.contains(name)
    }
}

/// The statements of the module body that bind each name of a plain `from . import name`.
pub(super) fn plain_from(node: &StmtImportFrom) -> impl Iterator<Item = (&str, TextSize)> {
    let start = node.range().start();
    node.names
        .iter()
        .filter(|alias| alias.asname.is_none())
        .map(move |alias| (alias.name.as_str(), start))
}

#[derive(Default)]
struct Walk {
    bound: Bound,
    /// The depth of function and class definitions: only depth 0 binds a module name.
    scope: usize,
    /// The depth of compound statements at module scope.
    depth: usize,
}

impl Walk {
    fn site(&mut self, name: &str, start: TextSize, plain: bool) {
        if self.scope == 0 {
            let plain = plain && self.depth == 0;
            let site = Site { plain, start };
            self.bound
                .sites
                .entry(name.to_owned())
                .or_default()
                .push(site);
        }
    }

    /// A star import of the module scope binds names that cannot be listed.
    fn star(&mut self, stmt: &Stmt) {
        let Stmt::ImportFrom(node) = stmt else {
            return;
        };
        let star = node.names.iter().any(|alias| alias.name.as_str() == "*");
        self.bound.opaque |= star && self.scope == 0;
    }

    fn definition(&mut self, name: &str, start: TextSize) {
        self.site(name, start, true);
        if self.scope == 0 && self.depth == 0 && name == "__getattr__" {
            self.bound.getattr = true;
        }
    }
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let start = stmt.range().start();
        match stmt {
            Stmt::FunctionDef(node) => {
                self.definition(node.name.as_str(), start);
                self.scope += 1;
                visitor::walk_stmt(self, stmt);
                self.scope -= 1;
            }
            Stmt::ClassDef(node) => {
                self.definition(node.name.as_str(), start);
                self.scope += 1;
                visitor::walk_stmt(self, stmt);
                self.scope -= 1;
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                self.star(stmt);
                for name in import_bindings(stmt) {
                    self.site(&name, start, true);
                }
            }
            Stmt::Global(_) | Stmt::Nonlocal(_) => {
                let names = declared(stmt).iter().map(|name| name.to_string());
                self.bound.globals.extend(names);
            }
            Stmt::Assign(node) => {
                for target in &node.targets {
                    match target {
                        Expr::Name(name) => self.site(name.id.as_str(), start, true),
                        other => self.visit_expr(other),
                    }
                }
                self.visit_expr(&node.value);
            }
            Stmt::AnnAssign(node) => {
                match &*node.target {
                    Expr::Name(name) => self.site(name.id.as_str(), start, true),
                    other => self.visit_expr(other),
                }
                self.visit_expr(&node.annotation);
                node.value.iter().for_each(|value| self.visit_expr(value));
            }
            Stmt::If(_)
            | Stmt::For(_)
            | Stmt::While(_)
            | Stmt::With(_)
            | Stmt::Try(_)
            | Stmt::Match(_) => {
                self.depth += 1;
                visitor::walk_stmt(self, stmt);
                self.depth -= 1;
            }
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if matches!(node.ctx, ExprContext::Store | ExprContext::Del) {
                self.site(node.id.as_str(), expr.range().start(), false);
            }
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, _: &'a Parameter) {}

    bind_handler_and_pattern!();
}

impl<'a> Bind<'a> for Walk {
    fn bind_name(&mut self, name: &'a str) {
        self.site(name, TextSize::default(), false);
    }
}

#[cfg(test)]
#[path = "bound_tests.rs"]
mod tests;
