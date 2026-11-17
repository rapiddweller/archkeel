// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scopes of a module for the uses of a module binding (#1506, AD-708).
//!
//! A load of a name reads the innermost function scope that binds it, then the enclosing ones,
//! then the module; a class body is a scope only for a load directly in it. A scope binds a name by
//! an import statement, or by anything else: a parameter, a store, a `del`, a `def` or `class`, an
//! `except` name, a match capture, a walrus (also inside a comprehension of the scope). `global`
//! and `nonlocal` move the name out of the function. A name that only imports bind is the module
//! of the import; one that only other bindings bind is another value; one that both bind may be
//! either. A comprehension binds its targets.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Comprehension, ExceptHandler, Expr, Parameters, Pattern, Stmt};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Kind {
    Module,
    Function,
    Class,
    Comprehension,
}

/// The names that one scope binds.
#[derive(Debug)]
pub(super) struct Scope {
    kind: Kind,
    imported: HashSet<String>,
    other: HashSet<String>,
    global: HashSet<String>,
    nonlocal: HashSet<String>,
}

/// What a name reads at a place.
#[derive(Debug, PartialEq, Eq)]
pub(super) enum Resolved {
    /// Only import statements bind it in its scope.
    Imported,
    /// Only other bindings bind it: it is no module object of an import.
    Value,
    /// Both bind it, or the order of a class body decides: it may be the module.
    Either,
    /// No scope binds it.
    Unbound,
}

impl Scope {
    /// The scope of a module, a function (with its parameters) or a class body.
    pub(super) fn of(kind: Kind, body: &[Stmt], parameters: Option<&Parameters>) -> Self {
        let mut binds = Binds::default();
        for stmt in body {
            binds.visit_stmt(stmt);
        }
        if let Some(parameters) = parameters {
            binds.other.extend(parameter_names(parameters));
        }
        binds.scope(kind)
    }

    /// The scope of a lambda: its parameters.
    pub(super) fn lambda(parameters: Option<&Parameters>) -> Self {
        let mut binds = Binds::default();
        binds
            .other
            .extend(parameters.into_iter().flat_map(parameter_names));
        binds.scope(Kind::Function)
    }

    /// The scope of a comprehension: its targets.
    pub(super) fn comprehension(generators: &[Comprehension]) -> Self {
        let mut binds = Binds::default();
        for generator in generators {
            binds.visit_expr(&generator.target);
        }
        binds.scope(Kind::Comprehension)
    }

    fn decide(&self, name: &str) -> Resolved {
        match (self.imported.contains(name), self.other.contains(name)) {
            (true, false) => Resolved::Imported,
            (false, true) if self.kind == Kind::Class => Resolved::Either,
            (false, true) => Resolved::Value,
            _ => Resolved::Either,
        }
    }

    fn binds(&self, name: &str) -> bool {
        self.imported.contains(name) || self.other.contains(name)
    }
}

/// What `name` reads in the innermost scope of `stack`; `stack[0]` is the module.
pub(super) fn resolve(stack: &[Scope], name: &str) -> Resolved {
    let innermost = stack.len().saturating_sub(1);
    for (at, scope) in stack.iter().enumerate().rev() {
        if scope.kind == Kind::Class && at != innermost {
            continue;
        }
        if scope.kind == Kind::Function && scope.global.contains(name) {
            return stack
                .first()
                .map_or(Resolved::Unbound, |module| module.decide(name));
        }
        if scope.kind == Kind::Function && scope.nonlocal.contains(name) {
            continue;
        }
        if scope.binds(name) {
            return scope.decide(name);
        }
    }
    Resolved::Unbound
}

fn parameter_names(parameters: &Parameters) -> impl Iterator<Item = String> + '_ {
    let plain = (parameters.posonlyargs.iter())
        .chain(&parameters.args)
        .chain(&parameters.kwonlyargs)
        .map(|p| p.parameter.name.to_string());
    let star = (parameters.vararg.iter())
        .chain(&parameters.kwarg)
        .map(|p| p.name.to_string());
    plain.chain(star)
}

/// The names that the statements of one scope bind; a nested scope is not read.
#[derive(Default)]
struct Binds {
    imported: HashSet<String>,
    other: HashSet<String>,
    global: HashSet<String>,
    nonlocal: HashSet<String>,
}

impl Binds {
    fn scope(self, kind: Kind) -> Scope {
        Scope {
            kind,
            imported: self.imported,
            other: self.other,
            global: self.global,
            nonlocal: self.nonlocal,
        }
    }
}

impl<'a> Visitor<'a> for Binds {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => drop(self.other.insert(node.name.to_string())),
            Stmt::ClassDef(node) => drop(self.other.insert(node.name.to_string())),
            Stmt::Import(node) => {
                for alias in &node.names {
                    let name = alias.asname.as_ref().map_or_else(
                        || alias.name.split('.').next().unwrap_or_default().to_owned(),
                        ToString::to_string,
                    );
                    self.imported.insert(name);
                }
            }
            Stmt::ImportFrom(node) => {
                for alias in &node.names {
                    let name = alias.asname.as_ref().unwrap_or(&alias.name);
                    self.imported.insert(name.to_string());
                }
            }
            Stmt::Global(node) => self
                .global
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::Nonlocal(node) => {
                self.nonlocal
                    .extend(node.names.iter().map(ToString::to_string));
            }
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) if !node.ctx.is_load() => drop(self.other.insert(node.id.to_string())),
            // A lambda is a scope of its own.
            Expr::Lambda(_) => {}
            // A comprehension binds its targets; a walrus in it binds in this scope.
            Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
                let mut walrus = Walrus(&mut self.other);
                walrus.visit_expr(expr);
            }
            _ => visitor::walk_expr(self, expr),
        }
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        let ExceptHandler::ExceptHandler(node) = handler;
        self.other
            .extend(node.name.as_ref().map(ToString::to_string));
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        let name = match pattern {
            Pattern::MatchAs(node) => node.name.as_ref(),
            Pattern::MatchStar(node) => node.name.as_ref(),
            Pattern::MatchMapping(node) => node.rest.as_ref(),
            _ => None,
        };
        self.other.extend(name.map(ToString::to_string));
        visitor::walk_pattern(self, pattern);
    }
}

/// The walrus targets of a comprehension, which bind in the enclosing scope.
struct Walrus<'s>(&'s mut HashSet<String>);

impl<'a> Visitor<'a> for Walrus<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Lambda(_) => {}
            Expr::Named(node) => {
                if let Expr::Name(target) = &*node.target {
                    self.0.insert(target.id.to_string());
                }
                self.visit_expr(&node.value);
            }
            _ => visitor::walk_expr(self, expr),
        }
    }
}
