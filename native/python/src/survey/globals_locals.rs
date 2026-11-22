// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a function binds (AD-530): its parameters, its writes and what it declares.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Decorator, ExceptHandler, Expr, ExprContext, Parameters, Pattern, Stmt, StmtFunctionDef,
};

use super::binders::{handler_name, pattern_name};

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
    pub(super) globals: HashSet<String>,
    /// The value of each name that the function writes exactly once by `name = value`.
    pub(super) assigned: HashMap<String, &'f Expr>,
    pub(super) stored: HashMap<String, usize>,
}

impl<'f> Locals<'f> {
    pub(super) fn of(def: &'f StmtFunctionDef) -> Self {
        let mut found = Locals::default();
        found.parameters(&def.parameters);
        found.visit_body(&def.body);
        found
    }

    fn parameters(&mut self, parameters: &Parameters) {
        let all = parameters
            .posonlyargs
            .iter()
            .chain(&parameters.args)
            .chain(&parameters.kwonlyargs)
            .map(|p| &p.parameter)
            .chain(parameters.vararg.as_deref())
            .chain(parameters.kwarg.as_deref());
        for parameter in all {
            self.bind(parameter.name.as_str());
        }
    }

    fn bind(&mut self, name: &str) {
        self.names.insert(name.to_owned());
        if !self.in_target {
            self.scoped.insert(name.to_owned());
        }
        *self.stored.entry(name.to_owned()).or_default() += 1;
    }

    fn definition(&mut self, name: &str, decorators: &'f [Decorator]) {
        self.bind(name);
        self.bind(name);
        decorators
            .iter()
            .for_each(|item| self.visit_decorator(item));
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
        self.bind(node.id.as_str());
    }
}

impl<'a> Visitor<'a> for Locals<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Global(node) => {
                self.declared
                    .extend(node.names.iter().map(ToString::to_string));
                self.globals
                    .extend(node.names.iter().map(ToString::to_string));
            }
            Stmt::Nonlocal(node) => self
                .declared
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::FunctionDef(node) => {
                self.definition(node.name.as_str(), &node.decorator_list);
                self.visit_parameters(&node.parameters);
                node.returns.iter().for_each(|item| self.visit_expr(item));
                return;
            }
            Stmt::ClassDef(node) => {
                self.definition(node.name.as_str(), &node.decorator_list);
                node.arguments
                    .iter()
                    .for_each(|item| self.visit_arguments(item));
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
        if let Expr::Lambda(node) = expr {
            if let Some(parameters) = &node.parameters {
                self.visit_parameters(parameters);
            }
            return;
        }
        if let Expr::Name(node) = expr {
            self.store(node);
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        if let Some(name) = handler_name(handler) {
            self.bind(name);
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        if let Some(name) = pattern_name(pattern) {
            self.bind(name);
        }
        visitor::walk_pattern(self, pattern);
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

/// The local names of a function for the trojan horse check of `hazards.rs`: each parameter and each
/// written name, less a name that a `global` or `nonlocal` line declares.
pub(super) fn local_names(def: &StmtFunctionDef) -> HashSet<String> {
    local_scope(def).0
}

/// The local and explicitly global names of a function.
pub(super) fn local_scope(def: &StmtFunctionDef) -> (HashSet<String>, HashSet<String>) {
    let found = Locals::of(def);
    let local = found
        .scoped
        .into_iter()
        .filter(|name| !found.declared.contains(name))
        .collect();
    (local, found.globals)
}

/// The names bound in a lambda, including assignment expressions in its body.
pub(super) fn lambda_names(lambda: &ruff_python_ast::ExprLambda) -> HashSet<String> {
    let mut found = Locals::default();
    if let Some(parameters) = &lambda.parameters {
        found.parameters(parameters);
    }
    found.visit_expr(&lambda.body);
    found.scoped
}

/// Class lookup is ordered; a possible class or global binding blocks an outer-local proof.
pub(super) fn class_blockers(body: &[Stmt]) -> HashSet<String> {
    let mut found = Locals::default();
    found.visit_body(body);
    found.scoped.retain(|name| !found.declared.contains(name));
    found.scoped.extend(found.globals);
    found.scoped
}
