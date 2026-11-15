// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a function binds (AD-530): its parameters, its writes and what it declares.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, Stmt, StmtFunctionDef};

/// The names that a function binds: its parameters, its assignments, and what it declares.
#[derive(Default)]
pub(super) struct Locals<'f> {
    pub(super) names: HashSet<String>,
    /// The names that the function binds in its own scope: `names` less each comprehension
    /// variable, which binds in the comprehension only (AD-530).
    pub(super) scoped: HashSet<String>,
    /// True while a comprehension target is read.
    pub(super) in_target: bool,
    pub(super) declared: HashSet<String>,
    /// The value of each name that the function writes exactly once by `name = value`.
    pub(super) assigned: HashMap<String, &'f Expr>,
    pub(super) stored: HashMap<String, usize>,
}

impl<'f> Locals<'f> {
    pub(super) fn of(def: &'f StmtFunctionDef) -> Self {
        let mut found = Locals::default();
        let parameters = &def.parameters;
        let all = parameters
            .posonlyargs
            .iter()
            .chain(&parameters.args)
            .chain(&parameters.kwonlyargs)
            .map(|p| &p.parameter)
            .chain(parameters.vararg.as_deref())
            .chain(parameters.kwarg.as_deref());
        for parameter in all {
            found.names.insert(parameter.name.to_string());
            found.scoped.insert(parameter.name.to_string());
            *found.stored.entry(parameter.name.to_string()).or_default() += 1;
        }
        found.visit_body(&def.body);
        found
    }

    /// True when the function writes `name` more than once (a parameter counts as one write).
    pub(super) fn written(&self, name: &str) -> bool {
        self.stored.get(name).copied().unwrap_or(0) > 1
    }
}

impl Locals<'_> {
    /// A name that an expression writes or deletes.
    fn store(&mut self, node: &ruff_python_ast::ExprName) {
        if node.ctx == ExprContext::Load {
            return;
        }
        let name = node.id.to_string();
        self.names.insert(name.clone());
        if !self.in_target {
            self.scoped.insert(name.clone());
        }
        *self.stored.entry(name).or_default() += 1;
    }
}

impl<'a> Visitor<'a> for Locals<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Global(node) => self
                .declared
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::Nonlocal(node) => self
                .declared
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::FunctionDef(node) => {
                self.names.insert(node.name.to_string());
                self.scoped.insert(node.name.to_string());
                *self.stored.entry(node.name.to_string()).or_default() += 2;
                return;
            }
            Stmt::ClassDef(node) => {
                self.names.insert(node.name.to_string());
                self.scoped.insert(node.name.to_string());
                *self.stored.entry(node.name.to_string()).or_default() += 2;
                return;
            }
            Stmt::Assign(node) => {
                if let ([Expr::Name(name)], value) = (node.targets.as_slice(), &*node.value) {
                    self.assigned.insert(name.id.to_string(), value);
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            self.store(node);
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_comprehension(&mut self, comprehension: &'a ruff_python_ast::Comprehension) {
        self.in_target = true;
        self.visit_expr(&comprehension.target);
        self.in_target = false;
        self.visit_expr(&comprehension.iter);
        comprehension
            .ifs
            .iter()
            .for_each(|test| self.visit_expr(test));
    }
}

/// The names that the statements of a module body store at any depth.
pub(super) fn stores(body: &[Stmt]) -> HashSet<String> {
    let mut walk = Locals::default();
    walk.visit_body(body);
    walk.names
}

/// The local names of a function for the door check of `hazards.rs`: each parameter and each
/// written name, less a name that a `global` or `nonlocal` line declares.
pub(super) fn local_names(def: &StmtFunctionDef) -> HashSet<String> {
    let found = Locals::of(def);
    found
        .scoped
        .into_iter()
        .filter(|name| !found.declared.contains(name))
        .collect()
}
