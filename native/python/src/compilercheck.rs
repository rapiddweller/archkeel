// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compiler limits and expression contexts that the Ruff grammar does not enforce.

use super::work::Work;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    visitor::{self, Visitor},
    Arguments, Expr, ModModule, Stmt, TypeParam, TypeParams,
};
use ruff_text_size::Ranged;
use std::collections::HashSet;

struct Check<'a> {
    source: &'a str,
    minor: PyMinor,
    work: Work,
    depth: usize,
    blocks: usize,
    star: bool,
    restricted: bool,
    private: Option<String>,
    reason: Option<(usize, &'static str)>,
}

pub fn check(module: &ModModule, source: &str, minor: PyMinor) -> Option<(usize, &'static str)> {
    let mut check = Check {
        source,
        minor,
        work: Work::new(),
        depth: 0,
        blocks: 0,
        star: false,
        restricted: false,
        private: None,
        reason: None,
    };
    check.docstring(&module.body);
    check.visit_body(&module.body);
    check
        .reason
        .or_else(|| check.work.failure().map(|reason| (0, reason)))
}

impl Check<'_> {
    fn annotation(&mut self, expr: &Expr) {
        let restricted = match self.minor {
            PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py313 => false,
            PyMinor::Py314 => true,
        };
        let old = self.restricted;
        self.restricted |= restricted;
        self.visit_expr(expr);
        self.restricted = old;
    }

    fn type_parameters(&mut self, params: Option<&TypeParams>) {
        let Some(params) = params else {
            return;
        };
        let old = std::mem::replace(&mut self.restricted, true);
        let mut names = HashSet::new();
        let mut default_seen = false;
        for param in &params.type_params {
            if !self.work.charge(1) {
                break;
            }
            if param.name().as_str() == "__debug__" {
                self.fail(param, "cannot bind __debug__");
            }
            if !names.insert(param.name().as_str()) {
                self.fail(param, "duplicate type parameter");
            }
            let bound = match param {
                TypeParam::TypeVar(var) => var.bound.as_deref(),
                TypeParam::TypeVarTuple(_) | TypeParam::ParamSpec(_) => None,
            };
            if let Some(bound) = bound {
                self.visit_expr(bound);
            }
            let default = param.default();
            if default.is_none() && default_seen {
                self.fail(param, "non-default type parameter follows a default");
            }
            default_seen |= default.is_some();
            if let Some(default) = default {
                self.type_default(param, default);
            }
        }
        self.restricted = old;
    }

    fn type_default(&mut self, param: &TypeParam, default: &Expr) {
        match self.minor {
            PyMinor::Py311 | PyMinor::Py312 => {
                self.fail(param, "type parameter defaults require Python 3.13");
            }
            PyMinor::Py313 | PyMinor::Py314 => {
                let star =
                    std::mem::replace(&mut self.star, matches!(param, TypeParam::TypeVarTuple(_)));
                self.visit_expr(default);
                self.star = star;
            }
        }
    }

    fn docstring(&mut self, body: &[Stmt]) {
        if let Some(reason) =
            super::stringcheck::docstring(body, self.source, self.minor, &mut self.work)
        {
            if let Some(stmt) = body.first() {
                self.fail(stmt, reason);
            }
        }
    }
    fn fail(&mut self, node: &impl Ranged, reason: &'static str) {
        if self.reason.is_none() {
            self.reason = Some((node.start().to_usize(), reason));
        }
    }

    fn enter(&mut self, node: &impl Ranged) -> bool {
        if self.reason.is_some() || !self.work.charge(1) {
            return false;
        }
        if self.depth >= 1000 {
            self.fail(node, "CPython validation depth limit exceeded");
            return false;
        }
        self.depth += 1;
        true
    }

    fn body(&mut self, body: &[Stmt], blocks: usize) {
        let old = self.blocks;
        self.blocks = self.blocks.saturating_add(blocks);
        let max = match self.minor {
            PyMinor::Py311 => 20,
            PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => 21,
        };
        if self.blocks > max {
            if let Some(stmt) = body.first() {
                self.fail(stmt, "too many statically nested blocks");
            }
        } else {
            self.visit_body(body);
        }
        self.blocks = old;
    }

    fn try_statement(&mut self, node: &ruff_python_ast::StmtTry) {
        let finally = usize::from(!node.finalbody.is_empty());
        self.body(&node.body, finally + usize::from(!node.handlers.is_empty()));
        for (index, handler) in node.handlers.iter().enumerate() {
            if !self.work.charge(1) {
                break;
            }
            let ruff_python_ast::ExceptHandler::ExceptHandler(handler) = handler;
            if handler.type_.is_none() && index + 1 != node.handlers.len() {
                self.fail(handler, "default except must be last");
            }
            if let Some(expr) = &handler.type_ {
                self.visit_expr(expr);
            }
            self.body(&handler.body, finally + 2);
        }
        self.body(&node.orelse, finally);
        self.body(&node.finalbody, 1);
    }

    fn arguments(&mut self, arguments: &Arguments) {
        let mut names = HashSet::new();
        for keyword in &arguments.keywords {
            if !self.work.charge(1) {
                break;
            }
            if keyword
                .arg
                .as_ref()
                .is_some_and(|name| !names.insert(name.as_str()))
            {
                self.fail(keyword, "keyword argument repeated");
            }
        }
    }

    fn decorators(&mut self, decorators: &[ruff_python_ast::Decorator]) {
        for decorator in decorators {
            if !self.work.charge(1) {
                break;
            }
            self.visit_expr(&decorator.expression);
        }
    }

    fn with_statement(&mut self, node: &ruff_python_ast::StmtWith) {
        for item in &node.items {
            if !self.work.charge(1) {
                break;
            }
            self.visit_expr(&item.context_expr);
            if let Some(target) = &item.optional_vars {
                self.visit_expr(target);
            }
        }
        self.body(&node.body, node.items.len());
    }
}

impl<'a> Visitor<'a> for Check<'_> {
    fn visit_body(&mut self, body: &'a [Stmt]) {
        for stmt in body {
            if !self.work.charge(1) || self.reason.is_some() {
                break;
            }
            self.visit_stmt(stmt);
        }
    }

    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if !self.enter(stmt) {
            return;
        }
        match stmt {
            Stmt::If(node)
                if self.minor == PyMinor::Py311
                    && node.elif_else_clauses.len().saturating_add(self.depth) > 900 =>
            {
                self.fail(stmt, "CPython default recursion limit bound exceeded");
            }
            Stmt::FunctionDef(node) => {
                self.type_parameters(node.type_params.as_deref());
                self.decorators(&node.decorator_list);
                self.visit_parameters(&node.parameters);
                if let Some(expr) = &node.returns {
                    self.visit_annotation(expr);
                }
                let old = std::mem::replace(&mut self.blocks, usize::from(node.is_async));
                self.docstring(&node.body);
                self.visit_body(&node.body);
                self.blocks = old;
            }
            Stmt::ClassDef(node) => {
                let private = self.private.replace(node.name.to_string());
                self.type_parameters(node.type_params.as_deref());
                if let Some(args) = &node.arguments {
                    self.visit_arguments(args);
                }
                self.decorators(&node.decorator_list);
                let old = std::mem::replace(&mut self.blocks, 0);
                self.docstring(&node.body);
                self.visit_body(&node.body);
                self.blocks = old;
                self.private = private;
            }
            Stmt::For(node) => {
                self.visit_expr(&node.target);
                self.visit_expr(&node.iter);
                self.body(&node.body, 1);
                self.visit_body(&node.orelse);
            }
            Stmt::While(node) => {
                self.visit_expr(&node.test);
                self.body(&node.body, 1);
                self.visit_body(&node.orelse);
            }
            Stmt::With(node) => self.with_statement(node),
            Stmt::Try(node) => self.try_statement(node),
            Stmt::TypeAlias(node) => {
                self.type_parameters(node.type_params.as_deref());
                let old = std::mem::replace(&mut self.restricted, true);
                self.visit_expr(&node.value);
                self.restricted = old;
            }
            _ => visitor::walk_stmt(self, stmt),
        }
        self.depth -= 1;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if !self.enter(expr) {
            return;
        }
        let star = std::mem::replace(
            &mut self.star,
            matches!(expr, Expr::Tuple(_) | Expr::List(_) | Expr::Set(_)),
        );
        match expr {
            Expr::Name(node) if matches!(node.id.as_str(), "True" | "False" | "None") => {
                match self.minor {
                    PyMinor::Py311 | PyMinor::Py312 => {}
                    PyMinor::Py313 | PyMinor::Py314 => {
                        self.fail(expr, "identifier field cannot represent a constant");
                    }
                }
            }
            Expr::Starred(_) if !star => self.fail(expr, "starred expression is not allowed here"),
            Expr::Named(node) => {
                let prefix = self
                    .source
                    .get(expr.start().to_usize()..node.target.start().to_usize())
                    .unwrap_or("");
                self.work.charge(prefix.len());
                if prefix.contains('(') {
                    self.fail(expr, "assignment expression target cannot be parenthesized");
                }
                if self.restricted {
                    self.fail(expr, "assignment expression in an annotation scope");
                }
                visitor::walk_expr(self, expr);
            }
            Expr::Yield(_) | Expr::YieldFrom(_) | Expr::Await(_) if self.restricted => {
                self.fail(expr, "yield or await in an annotation scope");
            }
            Expr::Lambda(node) => {
                if let Some(params) = &node.parameters {
                    self.visit_parameters(params);
                }
                let old = std::mem::replace(&mut self.restricted, false);
                self.visit_expr(&node.body);
                self.restricted = old;
            }
            _ => visitor::walk_expr(self, expr),
        }
        self.star = star;
        self.depth -= 1;
    }

    fn visit_arguments(&mut self, arguments: &'a Arguments) {
        self.arguments(arguments);
        for argument in &arguments.args {
            if !self.work.charge(1) {
                break;
            }
            self.star = true;
            self.visit_expr(argument);
            self.star = false;
        }
        for keyword in &arguments.keywords {
            if !self.work.charge(1) {
                break;
            }
            self.visit_expr(&keyword.value);
        }
    }

    fn visit_annotation(&mut self, expr: &'a Expr) {
        self.annotation(expr);
    }

    fn visit_parameters(&mut self, params: &'a ruff_python_ast::Parameters) {
        let mut names = HashSet::new();
        for param in params.iter() {
            if !self.work.charge(
                param
                    .name()
                    .as_str()
                    .len()
                    .saturating_add(self.private.as_deref().map_or(0, str::len))
                    .saturating_add(1),
            ) {
                break;
            }
            let name = param.name().as_str();
            let private = self
                .private
                .as_deref()
                .unwrap_or("")
                .trim_start_matches('_');
            let mangled = if !private.is_empty() && name.starts_with("__") && !name.ends_with("__")
            {
                format!("_{private}{name}")
            } else {
                name.to_owned()
            };
            if !names.insert(mangled) {
                self.fail(params, "duplicate parameter name");
            }
        }
        visitor::walk_parameters(self, params);
    }
}

#[cfg(test)]
#[path = "compilercheck_tests.rs"]
mod tests;
