// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scopes of one module and every binding in them (AD-1175, #2156). One walk lists each form
//! that binds a name: an assignment, an unpack, `:=`, `+=`, a loop or `with` target, an import, a
//! `def`, a `class`, a parameter, an `except` or `match` capture. A binding that the survey does
//! not read as a value is `Unknown`. The rule of `hazards_annotation_clean.rs` asks only this table.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Comprehension, ExceptHandler, Expr, ExprCall, ExprContext, Identifier, Pattern, PatternMatchAs,
    PatternMatchMapping, PatternMatchStar, Stmt, StmtClassDef, StmtImportFrom,
};
use ruff_text_size::{Ranged, TextRange};

use super::facts::{
    Binding, Call, Facts, Kind, Scope, ScopeId, Write, EVALUATORS, READERS, RESERVED,
};
use super::forms::{last, namespace};
use crate::module::Module;
use crate::survey::globals_project::PURE_BUILTINS;
use crate::survey::package_body::anchor;
use crate::survey::typing_count::builtin;
use crate::survey::uses_typing_guard::READS;

const WRITERS: [&str; 2] = ["setattr", "delattr"];

pub(super) fn build(module: &Module) -> Facts<'_> {
    let mut walk = Build {
        facts: Facts::new(),
        current: 0,
        package: &module.package,
        blessed: HashSet::new(),
        signature: false,
    };
    walk.visit_body(&module.tree.body);
    walk.facts.settle();
    walk.facts
}

struct Build<'a, 'm> {
    facts: Facts<'a>,
    current: ScopeId,
    package: &'m str,
    /// The namespace expressions that the parent only reads.
    blessed: HashSet<TextRange>,
    /// Inside the signature of a function: its annotations are evaluated.
    signature: bool,
}

impl<'a> Build<'a, '_> {
    fn open(&mut self, kind: Kind, class: Option<&'a StmtClassDef>) -> ScopeId {
        let scope = Scope::new(kind, Some(self.current), class);
        self.facts.scopes.push(scope);
        self.facts.scopes.len() - 1
    }

    /// The scope that a binding of `name` goes to: `global` and `nonlocal` redirect it.
    fn home(&self, name: &str) -> ScopeId {
        let scope = &self.facts.scopes[self.current];
        if scope.globals.contains(name) {
            return 0;
        }
        self.current
    }

    fn bind(&mut self, name: &str, binding: Binding<'a>) {
        if self.facts.scopes[self.current].nonlocals.contains(name) {
            let at = self.current;
            self.facts.pending.push((at, name.to_owned(), binding));
            return;
        }
        let home = self.home(name);
        let names = &mut self.facts.scopes[home].names;
        names.entry(name.to_owned()).or_default().push(binding);
    }

    /// `target = value`; `None` is a binding of a value that the survey does not read.
    fn target(&mut self, target: &'a Expr, value: Option<&'a Expr>) {
        let at = self.current;
        let binding = || value.map_or(Binding::Unknown, |v| Binding::Value(v, at));
        match target {
            Expr::Name(node) => self.bind(node.id.as_str(), binding()),
            Expr::Attribute(node) => {
                let stores = self.facts.stores.entry(node.attr.to_string());
                stores.or_default().push(binding());
                self.facts.writes.push(Write {
                    receiver: &node.value,
                    scope: self.current,
                    attr: Some(node.attr.to_string()),
                });
            }
            // `d[k] = v` changes the value of `d`; a write into `vars(C)` or `x.__dict__` is opaque.
            Expr::Subscript(node) => self.target(&node.value, None),
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.target(e, None)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.target(e, None)),
            Expr::Starred(node) => self.target(&node.value, None),
            _ => {}
        }
    }

    /// The writes of a target that is no plain name.
    fn stores_of(&mut self, target: &'a Expr) {
        match target {
            Expr::Attribute(_) | Expr::Subscript(_) => self.target(target, None),
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.stores_of(e)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.stores_of(e)),
            Expr::Starred(node) => self.stores_of(&node.value),
            _ => {}
        }
    }

    fn import_from(&mut self, node: &'a StmtImportFrom) {
        let module = anchor(node, self.package);
        for alias in &node.names {
            let name = alias.name.as_str();
            self.facts.evaluates |= EVALUATORS.contains(&name);
            let future = node
                .module
                .as_ref()
                .is_some_and(|m| m.as_str() == "__future__");
            self.facts.postponed |= future && name == "annotations";
            let local = alias.asname.as_ref().map_or(name, Identifier::as_str);
            match (&module, name) {
                (Some(module), "*") => {
                    let scope = &mut self.facts.scopes[self.current];
                    scope.stars.push(module.clone());
                }
                (Some(module), _) => {
                    let binding = Binding::Import(module.clone(), Some(name.to_owned()));
                    self.bind(local, binding);
                }
                (None, _) => self.bind(local, Binding::Unknown),
            }
        }
    }

    /// The expression `expr` is a namespace and its parent only reads it.
    fn bless(&mut self, expr: &Expr) {
        match expr {
            Expr::If(node) => {
                self.bless(&node.body);
                self.bless(&node.orelse);
            }
            other if namespace(other) => {
                self.blessed.insert(other.range());
            }
            _ => {}
        }
    }

    fn call(&mut self, call: &'a ExprCall, expr: &'a Expr) {
        let callee = last(&call.func).unwrap_or_default();
        if READERS.contains(&callee)
            || builtin(callee)
            || PURE_BUILTINS.contains(&callee)
            || EVALUATORS.contains(&callee)
        {
            let keywords = call.arguments.keywords.iter().map(|k| &k.value);
            call.arguments
                .args
                .iter()
                .chain(keywords)
                .for_each(|a| self.bless(a));
        }
        if let Expr::Attribute(method) = &*call.func {
            if READS.contains(&method.attr.as_str()) {
                self.bless(&method.value);
            }
        }
        let keywords = &call.arguments.keywords;
        let eval_str = keywords
            .iter()
            .any(|k| k.arg.as_ref().is_some_and(|a| a.as_str() == "eval_str"));
        self.facts.evaluates |= eval_str;
        let args = &call.arguments.args;
        if last(&call.func).is_some_and(|name| WRITERS.contains(&name)) {
            if let Some(receiver) = args.first() {
                let attr = match args.get(1) {
                    Some(Expr::StringLiteral(name)) => Some(name.value.to_string()),
                    _ => None,
                };
                let scope = self.current;
                self.facts.writes.push(Write {
                    receiver,
                    scope,
                    attr,
                });
            }
            match (args.get(1), args.get(2)) {
                (Some(Expr::StringLiteral(name)), value) => {
                    let at = self.current;
                    let binding = value.map_or(Binding::Unknown, |v| Binding::Value(v, at));
                    let stores = self.facts.stores.entry(name.value.to_string());
                    stores.or_default().push(binding);
                }
                _ => self.facts.opaque = true,
            }
        }
        if matches!(&*call.func, Expr::Name(_) | Expr::Attribute(_)) {
            let literal_ref = matches!(args.first(), Some(Expr::StringLiteral(_)));
            self.facts.calls.push(Call {
                callee: &call.func,
                scope: self.current,
                literal_ref,
                range: expr.range(),
            });
        }
    }
}

impl<'a> Visitor<'a> for Build<'a, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => {
                let at = self.current;
                self.bind(
                    node.name.as_str(),
                    Binding::Function(&node.decorator_list, at),
                );
                node.decorator_list
                    .iter()
                    .for_each(|d| self.visit_decorator(d));
                node.type_params
                    .iter()
                    .for_each(|p| self.visit_type_params(p));
                // The signature is evaluated in the scope that holds the function.
                self.signature = true;
                self.visit_parameters(&node.parameters);
                node.returns.iter().for_each(|r| self.visit_annotation(r));
                self.signature = false;
                let outer = self.current;
                self.current = self.open(Kind::Function, None);
                for parameter in node.parameters.iter() {
                    self.bind(parameter.name().as_str(), Binding::Unknown);
                }
                self.visit_body(&node.body);
                self.current = outer;
                return;
            }
            Stmt::ClassDef(node) => {
                node.decorator_list
                    .iter()
                    .for_each(|d| self.visit_decorator(d));
                node.type_params
                    .iter()
                    .for_each(|p| self.visit_type_params(p));
                node.arguments.iter().for_each(|a| self.visit_arguments(a));
                let outer = self.current;
                let body = self.open(Kind::Class, Some(node));
                let at = outer;
                self.bind(
                    node.name.as_str(),
                    Binding::Class(body, &node.decorator_list, at),
                );
                self.current = body;
                self.visit_body(&node.body);
                self.current = outer;
                return;
            }
            Stmt::Assign(node) => node
                .targets
                .iter()
                .for_each(|t| self.target(t, Some(&node.value))),
            Stmt::AnnAssign(node) => {
                if let Some(value) = &node.value {
                    self.target(&node.target, Some(value));
                }
            }
            Stmt::AugAssign(node) => self.target(&node.target, None),
            Stmt::Delete(node) => node.targets.iter().for_each(|t| self.target(t, None)),
            Stmt::For(node) => {
                self.bless(&node.iter);
                self.target(&node.target, None);
            }
            Stmt::With(node) => node
                .items
                .iter()
                .filter_map(|item| item.optional_vars.as_deref())
                .for_each(|target| self.target(target, None)),
            Stmt::Import(node) => {
                for alias in &node.names {
                    let name = alias.name.as_str();
                    self.facts.evaluates |=
                        EVALUATORS.contains(&name.rsplit('.').next().unwrap_or_default());
                    let first = name.split('.').next().unwrap_or(name);
                    let (local, module) = alias
                        .asname
                        .as_ref()
                        .map_or((first, first), |l| (l.as_str(), name));
                    self.bind(local, Binding::Import(module.to_owned(), None));
                }
            }
            Stmt::ImportFrom(node) => self.import_from(node),
            Stmt::Global(node) => {
                let scope = &mut self.facts.scopes[self.current];
                scope
                    .globals
                    .extend(node.names.iter().map(ToString::to_string));
            }
            Stmt::Nonlocal(node) => {
                let scope = &mut self.facts.scopes[self.current];
                scope
                    .nonlocals
                    .extend(node.names.iter().map(ToString::to_string));
            }
            Stmt::TypeAlias(node) => self.target_inert(&node.name),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    /// Python neither evaluates nor stores the annotation of a local variable.
    fn visit_annotation(&mut self, expr: &'a Expr) {
        if self.signature || self.facts.scopes[self.current].kind != Kind::Function {
            self.facts.annotations.push((expr, self.current));
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_comprehension(&mut self, comprehension: &'a Comprehension) {
        self.bless(&comprehension.iter);
        // A name of the target is local to the comprehension; an attribute or item is written.
        self.stores_of(&comprehension.target);
        visitor::walk_comprehension(self, comprehension);
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        let ExceptHandler::ExceptHandler(node) = handler;
        if let Some(name) = &node.name {
            self.bind(name.as_str(), Binding::Unknown);
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        if let Pattern::MatchAs(PatternMatchAs {
            name: Some(name), ..
        })
        | Pattern::MatchStar(PatternMatchStar {
            name: Some(name), ..
        })
        | Pattern::MatchMapping(PatternMatchMapping {
            rest: Some(name), ..
        }) = pattern
        {
            self.bind(name.as_str(), Binding::Unknown);
        }
        visitor::walk_pattern(self, pattern);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if namespace(expr) && !self.blessed.contains(&expr.range()) {
            self.facts.opaque = true;
        }
        let name = last(expr);
        if name.is_some_and(|n| RESERVED.contains(&n)) {
            self.facts.reaches.push(expr.range());
        }
        if name.is_some_and(|n| EVALUATORS.contains(&n)) {
            self.facts.evaluates = true;
        }
        match expr {
            Expr::Attribute(node)
                if matches!(node.attr.as_str(), "__setattr__" | "__delattr__") =>
            {
                self.facts.opaque = true;
            }
            Expr::Subscript(node) if node.ctx == ExprContext::Load => self.bless(&node.value),
            Expr::Compare(node) => {
                node.operands.iter().for_each(|o| self.bless(o));
            }
            Expr::StringLiteral(text) => {
                let text = text.value.to_str();
                if RESERVED.contains(&text) {
                    self.facts.reaches.push(expr.range());
                }
                // An evaluator that the module looks up by name is an evaluator.
                self.facts.evaluates |= EVALUATORS.contains(&text);
            }
            Expr::Call(call) => self.call(call, expr),
            Expr::Named(node) => self.target(&node.target, None),
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

impl<'a> Build<'a, '_> {
    fn target_inert(&mut self, target: &'a Expr) {
        if let Expr::Name(node) = target {
            self.bind(node.id.as_str(), Binding::Inert);
        }
    }
}
