// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compiler limits and expression contexts that the Ruff grammar does not enforce.

use super::work::Work;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    visitor::{self, Visitor},
    Arguments, Expr, ModModule, Stmt,
};
use ruff_text_size::Ranged;
use std::collections::HashSet;

#[path = "annotationcheck.rs"]
mod annotationcheck;

struct Check<'a> {
    source: &'a str,
    minor: PyMinor,
    work: Work,
    depth: usize,
    blocks: usize,
    star: bool,
    restricted: bool,
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
        reason: None,
    };
    check.visit_body(&module.body);
    check
        .reason
        .or_else(|| check.work.failure().map(|reason| (0, reason)))
}

impl Check<'_> {
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
            let cleanup = usize::from(handler.name.is_some() || node.is_star);
            self.body(&handler.body, finally + 1 + cleanup);
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
            if let Some(name) = &keyword.arg {
                if !names.insert(name.as_str()) {
                    self.fail(keyword, "keyword argument repeated");
                }
            }
        }
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
            Stmt::FunctionDef(node) => {
                self.type_parameters(node.type_params.as_deref());
                for decorator in &node.decorator_list {
                    if !self.work.charge(1) {
                        break;
                    }
                    self.visit_expr(&decorator.expression);
                }
                self.visit_parameters(&node.parameters);
                if let Some(expr) = &node.returns {
                    self.visit_annotation(expr);
                }
                let old = std::mem::replace(&mut self.blocks, usize::from(node.is_async));
                self.visit_body(&node.body);
                self.blocks = old;
            }
            Stmt::ClassDef(node) => {
                self.type_parameters(node.type_params.as_deref());
                if let Some(args) = &node.arguments {
                    self.visit_arguments(args);
                }
                for decorator in &node.decorator_list {
                    if !self.work.charge(1) {
                        break;
                    }
                    self.visit_expr(&decorator.expression);
                }
                let old = std::mem::replace(&mut self.blocks, 0);
                self.visit_body(&node.body);
                self.blocks = old;
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
            Stmt::With(node) => {
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
}

#[cfg(test)]
#[path = "compilercheck_tests.rs"]
mod tests;
