// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binders of one module and its `__all__`, as the Python collector reads them.
//!
//! `source._bound_names` over `ast.walk(tree)`, `_unique_direct_module_bindings`, and the `__all__`
//! rules `imports.literal_all_exports`, `imports.all_is_one_literal` and the module visit of
//! `ImportCollector` (`compatibility_logic_free`). One walk collects all of them.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Alias, ExceptHandler, Expr, ExprContext, Identifier, ModModule, Parameter, Pattern, Stmt,
    StmtImportFrom, TypeParams,
};

const ALL: &str = "__all__";

pub(super) fn named_call(
    func: &Expr,
    names: &HashSet<String>,
    modules: &HashSet<String>,
    attr: &str,
) -> bool {
    match func {
        Expr::Name(name) => names.contains(name.id.as_str()),
        Expr::Attribute(node) => {
            node.attr.as_str() == attr
                && matches!(&*node.value, Expr::Name(name) if modules.contains(name.id.as_str()))
        }
        _ => false,
    }
}

/// The binder facts of one module.
pub(crate) struct Binders {
    /// How often each name is bound anywhere in the module (`source._bound_names`).
    counts: HashMap<String, usize>,
    /// The names that a top-level definition or import binds, in source order.
    direct: Vec<String>,
    /// How many imports of `Any` from `typing` bind the name `Any`.
    typing_any: usize,
    /// How many imports of the module `typing` bind each name.
    typing_modules: HashMap<String, usize>,
    /// A star import or a type parameter list anywhere: no name is unique.
    opaque: bool,
    /// A type parameter list anywhere: the binders of a name are unknown (`count_beside_stars`).
    typed: bool,
    /// The star imports of the module: the level and the module of each.
    pub stars: Vec<(u32, String)>,
    pub all_exports: HashSet<String>,
    pub all_literal: bool,
    /// `__all__` is named but is not one literal list of strings: the module publishes names that
    /// the survey cannot read (AD-504).
    pub all_unread: bool,
    pub logic_free: bool,
    pub imports_importlib: bool,
}

impl Binders {
    pub(crate) fn of(tree: &ModModule) -> Self {
        let mut walk = Walk::default();
        walk.visit_body(&tree.body);
        let mut direct = Vec::new();
        for statement in &tree.body {
            match statement {
                Stmt::FunctionDef(node) => direct.push(node.name.id.to_string()),
                Stmt::ClassDef(node) => direct.push(node.name.id.to_string()),
                _ => {}
            }
        }
        for statement in &tree.body {
            if let Stmt::Import(_) | Stmt::ImportFrom(_) = statement {
                direct.extend(import_bindings(statement));
            }
        }
        let all_literal = !walk.all_imported && one_literal(&tree.body, walk.all_names);
        Self {
            counts: walk.counts,
            typing_any: walk.typing_any,
            typing_modules: walk.typing_modules,
            direct,
            opaque: walk.opaque,
            typed: walk.typed,
            stars: walk.stars,
            all_exports: literal_all_exports(&tree.body),
            all_literal,
            all_unread: !all_literal && (walk.all_imported || walk.all_names > 0),
            logic_free: logic_free(&tree.body),
            imports_importlib: walk.imports_importlib,
        }
    }

    /// `_bare_builtin`: no star import and no type parameter list in the module, and no binder of
    /// the name anywhere in it. A type parameter list parses only from Python 3.12, where the
    /// Python rule applies it.
    pub(crate) fn builtin_visible(&self, name: &str) -> bool {
        !self.opaque && !self.counts.contains_key(name)
    }

    /// The count of `count`, with the star imports left out: the caller reads them (`stars`).
    pub(crate) fn count_beside_stars(&self, name: &str) -> Option<usize> {
        (!self.typed).then(|| self.counts.get(name).copied().unwrap_or(0))
    }

    /// How often a binder binds the name anywhere in the module, or `None` when a star import
    /// or a type parameter list makes the count unknown (`guard.rs`).
    pub(crate) fn count(&self, name: &str) -> Option<usize> {
        (!self.opaque).then(|| self.counts.get(name).copied().unwrap_or(0))
    }

    /// The binders of the module prove that `expr` (`Any` or `m.Any`) names the `Any` of the
    /// standard module `typing` (AD-880). `Any`: each binder is an import of `typing.Any`, and each
    /// star import is from `typing`; with no binder one such star import is needed. `m.Any`: each
    /// binder of `m` is an import of the module `typing`. `typing_extensions` is no standard module:
    /// nothing proves its object. A source order, another star import or a second binder leaves the
    /// identity unproven. The caller still needs that nothing replaces `typing` (`ClassWrites`).
    pub(crate) fn names_typing_any(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Name(name) if name.id.as_str() == "Any" => {
                let typing_stars = self
                    .stars
                    .iter()
                    .all(|(level, module)| *level == 0 && module.as_str() == "typing");
                self.count_beside_stars("Any").is_some_and(|bound| {
                    typing_stars
                        && bound == self.typing_any
                        && (bound > 0 || !self.stars.is_empty())
                })
            }
            Expr::Attribute(attr) if attr.attr.as_str() == "Any" => {
                matches!(&*attr.value, Expr::Name(base) if self.count(base.id.as_str())
                    .is_some_and(|bound| bound > 0
                        && self.typing_modules.get(base.id.as_str()) == Some(&bound)))
            }
            _ => false,
        }
    }

    /// The annotation holds a name that the binders prove to be `typing.Any`.
    pub(crate) fn names_any(&self, annotation: &Expr) -> bool {
        struct Any<'b>(&'b Binders, bool);
        impl<'a> Visitor<'a> for Any<'_> {
            fn visit_expr(&mut self, expr: &'a Expr) {
                self.1 |= self.0.names_typing_any(expr);
                visitor::walk_expr(self, expr);
            }
        }
        let mut found = Any(self, false);
        found.visit_expr(annotation);
        found.1
    }

    /// The facts of the trojan horse proofs (`hazards_inert.rs`): the unique direct names, the names that
    /// the module binds exactly once anywhere, and the names of `builtins` that no binder shadows.
    pub(in crate::survey) fn proof_facts(
        &self,
        builtins: &[&str],
    ) -> (HashSet<String>, HashSet<String>, HashSet<String>) {
        let once = |(name, count): (&String, &usize)| (*count == 1).then(|| name.clone());
        let single = (!self.opaque).then(|| self.counts.iter().filter_map(once).collect());
        let visible = builtins.iter().filter(|name| self.builtin_visible(name));
        let visible = visible.map(|name| (*name).to_owned()).collect();
        (self.unique(), single.unwrap_or_default(), visible)
    }

    /// `_unique_direct_module_bindings`: a direct name that no other binder in the module binds.
    pub(crate) fn unique(&self) -> HashSet<String> {
        if self.opaque {
            return HashSet::new();
        }
        let once = |name: &&String| self.counts.get(name.as_str()) == Some(&1);
        self.direct.iter().filter(once).cloned().collect()
    }
}

pub(crate) use crate::module::{first_part, import_bindings};

#[derive(Default)]
struct Walk {
    counts: HashMap<String, usize>,
    typing_any: usize,
    typing_modules: HashMap<String, usize>,
    opaque: bool,
    typed: bool,
    stars: Vec<(u32, String)>,
    /// Each `Name` node `__all__`, in any context.
    all_names: usize,
    /// An import names `__all__` as its name or its alias.
    all_imported: bool,
    imports_importlib: bool,
}

impl Walk {
    fn bind(&mut self, name: &str) {
        *self.counts.entry(name.to_owned()).or_default() += 1;
    }

    fn type_params(&mut self, params: Option<&TypeParams>) {
        if params.is_some_and(|params| !params.type_params.is_empty()) {
            self.opaque = true;
            self.typed = true;
        }
    }
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => {
                self.bind(node.name.as_str());
                self.type_params(node.type_params.as_deref());
            }
            Stmt::ClassDef(node) => {
                self.bind(node.name.as_str());
                self.type_params(node.type_params.as_deref());
            }
            Stmt::TypeAlias(node) => self.type_params(node.type_params.as_deref()),
            Stmt::Import(node) => {
                self.imports_importlib |= node
                    .names
                    .iter()
                    .any(|alias| first_part(alias.name.as_str()) == "importlib");
                self.typing_module_imports(&node.names);
                self.imports(&node.names, stmt);
            }
            Stmt::ImportFrom(node) => {
                if node.names.iter().any(|alias| alias.name.as_str() == "*") {
                    self.opaque = true;
                    let module = node.module.as_ref().map_or("", |name| name.as_str());
                    self.stars.push((node.level, module.to_owned()));
                }
                self.typing_any += typing_any_imports(node);
                self.imports(&node.names, stmt);
            }
            Stmt::Global(_) | Stmt::Nonlocal(_) => {
                declared(stmt)
                    .iter()
                    .for_each(|name| self.bind(name.as_str()));
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if node.id.as_str() == ALL {
                self.all_names += 1;
            }
            if matches!(node.ctx, ExprContext::Store | ExprContext::Del) {
                self.bind(node.id.as_str());
            }
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.bind(parameter.name.as_str());
        visitor::walk_parameter(self, parameter);
    }

    bind_handler_and_pattern!();
}

impl<'a> Bind<'a> for Walk {
    fn bind_name(&mut self, name: &'a str) {
        self.bind(name);
    }
}

/// The visitor methods that bind the name of an `except` handler and of a pattern. The walks of
/// `binders.rs` and `bound.rs` share them.
macro_rules! bind_handler_and_pattern {
    () => {
        fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
            bind_handler(self, handler);
        }

        fn visit_pattern(&mut self, pattern: &'a Pattern) {
            bind_pattern(self, pattern);
        }
    };
}
pub(super) use bind_handler_and_pattern;

/// A visitor that counts the names that binders bind.
pub(crate) trait Bind<'a>: Visitor<'a> {
    fn bind_name(&mut self, name: &'a str);
}

/// Count the name of an except handler and walk the handler.
pub(crate) fn bind_handler<'a, V: Bind<'a>>(visitor: &mut V, handler: &'a ExceptHandler) {
    if let Some(name) = handler_name(handler) {
        visitor.bind_name(name);
    }
    visitor::walk_except_handler(visitor, handler);
}

/// Count the name of a pattern and walk the pattern.
pub(crate) fn bind_pattern<'a, V: Bind<'a>>(visitor: &mut V, pattern: &'a Pattern) {
    if let Some(name) = pattern_name(pattern) {
        visitor.bind_name(name);
    }
    visitor::walk_pattern(visitor, pattern);
}

/// The names of a `global` or a `nonlocal` statement.
pub(crate) fn declared(stmt: &Stmt) -> &[Identifier] {
    match stmt {
        Stmt::Global(node) => &node.names,
        Stmt::Nonlocal(node) => &node.names,
        _ => &[],
    }
}

/// The name that `except ... as name` binds.
pub(super) fn handler_name(handler: &ExceptHandler) -> Option<&str> {
    let ExceptHandler::ExceptHandler(node) = handler;
    node.name.as_ref().map(Identifier::as_str)
}

/// The name that a capture, a star or a mapping rest pattern binds.
pub(super) fn pattern_name(pattern: &Pattern) -> Option<&str> {
    let name = match pattern {
        Pattern::MatchAs(node) => node.name.as_ref(),
        Pattern::MatchStar(node) => node.name.as_ref(),
        Pattern::MatchMapping(node) => node.rest.as_ref(),
        _ => None,
    };
    name.map(Identifier::as_str)
}

/// How many names of `from typing import ...` bind `Any` as `Any`.
fn typing_any_imports(node: &StmtImportFrom) -> usize {
    let typing = node
        .module
        .as_ref()
        .is_some_and(|name| name.as_str() == "typing");
    let own = |alias: &&Alias| {
        let named_any = alias
            .asname
            .as_ref()
            .is_none_or(|name| name.as_str() == "Any");
        alias.name.as_str() == "Any" && named_any
    };
    if node.level == 0 && typing {
        node.names.iter().filter(own).count()
    } else {
        0
    }
}

impl Walk {
    fn typing_module_imports(&mut self, names: &[Alias]) {
        for alias in names {
            if alias.name.as_str() == "typing" {
                let bound = alias.asname.as_ref().unwrap_or(&alias.name);
                *self.typing_modules.entry(bound.to_string()).or_default() += 1;
            }
        }
    }

    fn imports(&mut self, names: &[Alias], stmt: &Stmt) {
        if names.iter().any(|alias| {
            alias.name.as_str() == ALL || alias.asname.as_ref().is_some_and(|a| a.as_str() == ALL)
        }) {
            self.all_imported = true;
        }
        for name in import_bindings(stmt) {
            self.bind(&name);
        }
    }
}

/// The targets and the value of a top-level `Assign` or `AnnAssign`.
fn assignment(statement: &Stmt) -> Option<(Vec<&Expr>, Option<&Expr>)> {
    match statement {
        Stmt::Assign(node) => Some((node.targets.iter().collect(), Some(&*node.value))),
        Stmt::AnnAssign(node) => Some((vec![&*node.target], node.value.as_deref())),
        _ => None,
    }
}

fn is_all(target: &Expr) -> bool {
    matches!(target, Expr::Name(node) if node.id.as_str() == ALL)
}

/// The elements of a list or a tuple, and of a set when `set` is true.
fn elements(value: Option<&Expr>, set: bool) -> Option<&[Expr]> {
    match value? {
        Expr::List(node) => Some(&node.elts),
        Expr::Tuple(node) => Some(&node.elts),
        Expr::Set(node) if set => Some(&node.elts),
        _ => None,
    }
}

fn text(element: &Expr) -> Option<String> {
    match element {
        Expr::StringLiteral(node) => Some(node.value.to_str().to_owned()),
        _ => None,
    }
}

/// `literal_all_exports`: each string of each top-level literal bound to `__all__`.
fn literal_all_exports(body: &[Stmt]) -> HashSet<String> {
    let mut exports = HashSet::new();
    for (targets, value) in body.iter().filter_map(assignment) {
        if targets.iter().any(|target| is_all(target)) {
            if let Some(items) = elements(value, true) {
                exports.extend(items.iter().filter_map(text));
            }
        }
    }
    exports
}

fn all_strings(value: Option<&Expr>) -> bool {
    elements(value, false).is_some_and(|items| items.iter().all(|item| text(item).is_some()))
}

/// `all_is_one_literal`: one top-level statement binds `__all__`, its targets are every `Name`
/// `__all__` of the module (`node.targets == references`), and its value is a string literal.
fn one_literal(body: &[Stmt], all_names: usize) -> bool {
    let mut values = body.iter().filter_map(assignment).filter(|(targets, _)| {
        targets.len() == all_names && targets.iter().all(|target| is_all(target))
    });
    match (values.next(), values.next()) {
        (Some((_, value)), None) => all_strings(value),
        _ => false,
    }
}

/// The module visit of `ImportCollector`: an optional docstring, imports, and one literal
/// `__all__`; anything else stops the module from being free of logic.
fn logic_free(body: &[Stmt]) -> bool {
    let mut has_all = false;
    for (index, statement) in body.iter().enumerate() {
        if index == 0 && is_docstring(statement) {
            continue;
        }
        if let Stmt::Import(_) | Stmt::ImportFrom(_) = statement {
            continue;
        }
        let Some((targets, value)) = assignment(statement) else {
            return false;
        };
        if has_all || targets.len() != 1 || !is_all(targets[0]) {
            return false;
        }
        has_all = true;
        if !all_strings(value) {
            return false;
        }
    }
    has_all
}

fn is_docstring(statement: &Stmt) -> bool {
    matches!(statement, Stmt::Expr(node) if matches!(&*node.value, Expr::StringLiteral(_)))
}

#[cfg(test)]
#[path = "binders_tests.rs"]
mod tests;
