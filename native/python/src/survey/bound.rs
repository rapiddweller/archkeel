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
use ruff_python_ast::{
    ExceptHandler, Expr, ExprContext, Parameter, Pattern, Stmt, StmtClassDef, StmtImportFrom,
};
use ruff_text_size::{Ranged, TextSize};

use super::binders::{
    bind_handler, bind_handler_and_pattern, bind_pattern, declared, import_bindings, Bind,
};
use super::bound_kind::{scalar_literal, value_kind, Kind};
use super::copy_local::{self, CopyWrites};
use super::value::{value_deps, Deps};
use crate::module::plain_name;

/// One statement that binds a name at module scope.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Site {
    /// The statement is directly in the module body: no `if`, `try`, `for`, `with` or `match`.
    plain: bool,
    start: TextSize,
    kind: Kind,
}

/// The module-scope binders of one module body.
#[derive(Default)]
pub(super) struct Bound {
    sites: HashMap<String, Vec<Site>>,
    /// Names that a function of the module declares `global` (a write binds the module name).
    globals: HashSet<String>,
    /// A star import binds names that cannot be listed.
    pub(super) opaque: bool,
    /// What the value of each plain `name = value` reads (AD-530).
    values: HashMap<String, Deps>,
    /// A top-level `__getattr__` can give any attribute.
    pub(super) getattr: bool,
    /// A namespace write through a runtime attribute helper can change a binding.
    pub(super) attribute_write: bool,
    /// `setattr` or `delattr` on an object that is no copied local (`copy_local.rs`): it can
    /// write a module of the scan (AD-530, decision 5).
    pub(super) foreign_write: bool,
    /// `setattr` or `delattr` on a copied local: no write to a module while the scan names no hook.
    pub(super) copy_write: bool,
    /// The module names a word of a copy hook (`copy_local::names_a_hook`).
    pub(super) copy_hook: bool,
    /// The callee of `name = callee(...)`, for the names whose kind is `Kind::Call`.
    callees: HashMap<String, String>,
    /// The class statements of the module scope (AD-566).
    classes: HashMap<String, Class>,
}

/// What a `class` statement of the module scope says about the call of its name.
struct Class {
    /// No base class and no keyword: the metaclass is `type`.
    bare: bool,
    /// The class body binds `__new__`, which may return any object.
    new: bool,
    /// The plain name of each decorator, or `None` for any other decorator form.
    decorators: Vec<Option<String>>,
}

impl Bound {
    pub(super) fn of(body: &[Stmt]) -> Self {
        let mut walk = Walk::default();
        walk.visit_body(body);
        let (proven, any) = walk
            .copy
            .resolved(|name, start| walk.bound.sole(name, start));
        walk.bound.foreign_write |= !proven;
        walk.bound.copy_write = proven && any;
        walk.bound.copy_hook = copy_local::names_a_hook(body);
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

    /// The callee of the sole `name = callee(...)` statement, when `name` has that kind.
    pub(super) fn callee(&self, name: &str) -> Option<&str> {
        (self.kind(name) == Some(Kind::Call))
            .then(|| self.callees.get(name).map(String::as_str))
            .flatten()
    }

    /// The decorator names of the class that `name` is, when a call of it makes an instance of
    /// it: no base, no keyword, no `__new__`. A decorator that is not a plain name is `None`.
    pub(super) fn bare_class(&self, name: &str) -> Option<&[Option<String>]> {
        let class = self.classes.get(name)?;
        (self.kind(name) == Some(Kind::Callable) && class.bare && !class.new)
            .then_some(class.decorators.as_slice())
    }

    /// What the value of the sole plain binder of `name` reads, when that binder is `Derived`.
    pub(super) fn deps(&self, name: &str) -> Option<&Deps> {
        self.values.get(name)
    }

    /// Each name that a statement of the module scope, or a `global` declaration, binds.
    pub(super) fn names(&self) -> HashSet<String> {
        let sites = self.sites.keys().cloned();
        sites.chain(self.globals.iter().cloned()).collect()
    }

    pub(super) fn unbound(&self, name: &str) -> bool {
        !self.opaque && !self.globals.contains(name) && !self.sites.contains_key(name)
    }

    pub(super) fn inert_typing_arg(&self, expr: &Expr) -> bool {
        if scalar_literal(expr) {
            return true;
        }
        match expr {
            Expr::Name(name) => {
                matches!(
                    name.id.as_str(),
                    "int" | "str" | "float" | "bool" | "bytes" | "object"
                ) && self.unbound(name.id.as_str())
            }
            Expr::Tuple(tuple) => tuple.elts.iter().all(|item| self.inert_typing_arg(item)),
            _ => false,
        }
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
    /// The local names of each enclosing function, the innermost last (AD-530).
    locals: Vec<HashSet<String>>,
    /// The `setattr` and `delattr` calls on copied locals (`copy_local.rs`).
    copy: CopyWrites,
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

    fn class(&mut self, node: &StmtClassDef) {
        if self.scope != 0 {
            return;
        }
        let bare = node
            .arguments
            .as_ref()
            .is_none_or(|arguments| arguments.args.is_empty() && arguments.keywords.is_empty());
        let mut news = NewWatch(false);
        news.visit_body(&node.body);
        let decorators = node
            .decorator_list
            .iter()
            .map(|item| match &item.expression {
                Expr::Call(call) => plain_name(&call.func),
                other => plain_name(other),
            })
            .map(|name| name.map(str::to_owned))
            .collect();
        let class = Class {
            bare,
            new: news.0,
            decorators,
        };
        self.bound.classes.insert(node.name.to_string(), class);
    }

    fn definition(&mut self, name: &str, start: TextSize) {
        self.site(name, start, true, Kind::Callable);
    }

    fn assignment_target<'a>(&mut self, target: &'a Expr, start: TextSize, value: Option<&Expr>)
    where
        Self: Visitor<'a>,
    {
        let (mut kind, callee) = value.map_or((Kind::Other, None), value_kind);
        let mut deps = None;
        if kind == Kind::Other {
            deps = value.and_then(value_deps);
            if deps.is_some() {
                kind = Kind::Derived;
            }
        }
        match target {
            Expr::Name(name) => {
                self.site(name.id.as_str(), start, true, kind);
                if let (0, Some(deps)) = (self.scope, deps) {
                    self.bound.values.insert(name.id.to_string(), deps);
                }
                if let (Kind::Call, Some(callee)) = (kind, callee) {
                    self.bound
                        .callees
                        .insert(name.id.to_string(), callee.to_owned());
                }
            }
            other => self.visit_expr(other),
        }
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
                self.locals.push(super::globals_locals::local_names(node));
                self.copy.enter(node);
                self.body_scope(&node.body);
                self.copy.leave();
                self.locals.pop();
            }
            Stmt::ClassDef(node) => {
                self.definition(node.name.as_str(), start);
                self.class(node);
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
                if self.scope == 0 {
                    self.copy.import(stmt, start);
                }
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
                    self.assignment_target(target, start, Some(&node.value));
                }
                self.visit_expr(&node.value);
            }
            Stmt::AnnAssign(node) => {
                self.assignment_target(&node.target, start, node.value.as_deref());
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
            let helper = matches!(name, Some("setattr" | "delattr"));
            self.bound.attribute_write |= helper;
            // A method named `setattr` (`monkeypatch.setattr("app.lib.f", 1)`) can take a path.
            let builtin = matches!(&*call.func, Expr::Name(_));
            let first = call.arguments.args.first();
            let first = first.filter(|_| helper && builtin);
            let copied = first.is_some_and(|expr| self.copy.write(expr, &self.locals));
            self.bound.foreign_write |= helper && !copied;
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

impl<'a> Bind<'a> for Walk {
    fn bind_name(&mut self, name: &'a str) {
        self.site(name, TextSize::default(), false, Kind::Other);
    }
}

/// A class body that binds `__new__`, by a definition or by a name.
struct NewWatch(bool);

impl<'a> Visitor<'a> for NewWatch {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::FunctionDef(node) if node.name.as_str() == "__new__") {
            self.0 = true;
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::Name(node) if node.id.as_str() == "__new__") {
            self.0 = true;
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "bound_tests.rs"]
mod tests;
