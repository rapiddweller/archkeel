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
    kind: Kind,
}

/// What the statement of a site binds the name to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Kind {
    /// A `def` or a `class`: the name is a function or a class, never a module.
    Callable,
    /// A display or literal makes a value, not a module.
    Value,
    /// A subscript of a builtin generic, if the module does not bind that builtin.
    BuiltinGeneric(&'static str),
    /// An import: the name is whatever the imported name is.
    Import,
    /// Any other binder: the value is unknown.
    Other,
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
    /// A namespace write through a runtime attribute helper can change a binding.
    pub(super) attribute_write: bool,
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

    /// What the one plain statement that binds `name` makes it, or `None` when the name has no
    /// sole plain binder.
    pub(super) fn kind(&self, name: &str) -> Option<Kind> {
        let sites = self
            .sites
            .get(name)
            .filter(|_| !self.opaque && !self.globals.contains(name))?;
        match sites.as_slice() {
            [only] if only.plain => Some(only.kind),
            _ => None,
        }
    }

    /// Each name that a statement of the module scope, or a `global` declaration, binds.
    pub(super) fn names(&self) -> HashSet<String> {
        let sites = self.sites.keys().cloned();
        sites.chain(self.globals.iter().cloned()).collect()
    }

    pub(super) fn unbound(&self, name: &str) -> bool {
        !self.opaque && !self.globals.contains(name) && !self.sites.contains_key(name)
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
    fn site(&mut self, name: &str, start: TextSize, plain: bool, kind: Kind) {
        if self.scope == 0 {
            if name == "__getattr__" {
                // Any binder of `__getattr__` opens the package: every name of it is ambiguous.
                self.bound.getattr = true;
            }
            let plain = plain && self.depth == 0;
            let site = Site { plain, start, kind };
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

    /// The body of a definition: the names of its statements bind in a scope of their own.
    fn body_scope<'a>(&mut self, body: &'a [Stmt])
    where
        Self: Visitor<'a>,
    {
        self.scope += 1;
        self.visit_body(body);
        self.scope -= 1;
    }

    fn definition(&mut self, name: &str, start: TextSize) {
        self.site(name, start, true, Kind::Callable);
    }
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let start = stmt.range().start();
        match stmt {
            Stmt::FunctionDef(node) => {
                self.definition(node.name.as_str(), start);
                // The decorators, the defaults, the annotations run in the enclosing scope.
                node.decorator_list
                    .iter()
                    .for_each(|item| self.visit_decorator(item));
                self.visit_parameters(&node.parameters);
                node.returns.iter().for_each(|item| self.visit_expr(item));
                self.body_scope(&node.body);
            }
            Stmt::ClassDef(node) => {
                self.definition(node.name.as_str(), start);
                // The decorators, the base classes and the keywords run in the enclosing scope.
                node.decorator_list
                    .iter()
                    .for_each(|item| self.visit_decorator(item));
                node.arguments
                    .iter()
                    .for_each(|item| self.visit_arguments(item));
                self.body_scope(&node.body);
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                self.star(stmt);
                for name in import_bindings(stmt) {
                    self.site(&name, start, true, Kind::Import);
                }
            }
            Stmt::Global(_) | Stmt::Nonlocal(_) => {
                let names = declared(stmt).iter().map(|name| name.to_string());
                self.bound.globals.extend(names);
                self.bound.getattr |= self.bound.globals.contains("__getattr__");
            }
            Stmt::TypeAlias(node) => {
                if let Expr::Name(name) = &*node.name {
                    self.site(name.id.as_str(), start, true, Kind::Value);
                }
                if let Some(params) = &node.type_params {
                    self.visit_type_params(params);
                }
                self.visit_expr(&node.value);
            }
            Stmt::Assign(node) => {
                for target in &node.targets {
                    match target {
                        Expr::Name(name) => {
                            self.site(name.id.as_str(), start, true, value_kind(&node.value))
                        }
                        other => self.visit_expr(other),
                    }
                }
                self.visit_expr(&node.value);
            }
            Stmt::AnnAssign(node) => {
                match &*node.target {
                    Expr::Name(name) => self.site(
                        name.id.as_str(),
                        start,
                        true,
                        node.value.as_deref().map_or(Kind::Other, value_kind),
                    ),
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
        if let Expr::Call(call) = expr {
            let name = match &*call.func {
                Expr::Name(name) => Some(name.id.as_str()),
                Expr::Attribute(attr) => Some(attr.attr.as_str()),
                _ => None,
            };
            self.bound.attribute_write |= matches!(name, Some("setattr" | "delattr"));
        }
        if let Expr::Name(node) = expr {
            if matches!(node.ctx, ExprContext::Store | ExprContext::Del) {
                self.site(node.id.as_str(), expr.range().start(), false, Kind::Other);
            }
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        // The name of a parameter binds in the body, not in the module; its annotation runs here.
        parameter
            .annotation
            .iter()
            .for_each(|item| self.visit_expr(item));
    }

    bind_handler_and_pattern!();
}

fn value_kind(value: &Expr) -> Kind {
    if let Expr::Subscript(subscript) = value {
        if let Expr::Name(name) = &*subscript.value {
            let builtin = match name.id.as_str() {
                "list" => Some("list"),
                "dict" => Some("dict"),
                "tuple" => Some("tuple"),
                "set" => Some("set"),
                "frozenset" => Some("frozenset"),
                "type" => Some("type"),
                _ => None,
            };
            if let Some(builtin) = builtin {
                return Kind::BuiltinGeneric(builtin);
            }
        }
    }
    if matches!(
        value,
        Expr::NumberLiteral(_)
            | Expr::StringLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::Tuple(_)
            | Expr::List(_)
            | Expr::Dict(_)
            | Expr::Set(_)
            | Expr::FString(_)
    ) {
        Kind::Value
    } else {
        Kind::Other
    }
}

impl<'a> Bind<'a> for Walk {
    fn bind_name(&mut self, name: &'a str) {
        self.site(name, TextSize::default(), false, Kind::Other);
    }
}

#[cfg(test)]
#[path = "bound_tests.rs"]
mod tests;
