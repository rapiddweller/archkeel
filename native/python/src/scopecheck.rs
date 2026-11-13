// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Lexical bindings for the enclosing-function check of a nonlocal declaration.

use super::work::Work;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    visitor::{self, Visitor},
    Expr, ExprContext, Stmt,
};
use std::collections::HashSet;

pub fn is_future(node: &ruff_python_ast::StmtImportFrom, minor: PyMinor) -> bool {
    let relative = match minor {
        PyMinor::Py311 | PyMinor::Py312 => true,
        PyMinor::Py313 | PyMinor::Py314 => false,
    };
    (node.level == 0 || relative)
        && node
            .module
            .as_ref()
            .is_some_and(|name| name == "__future__")
}

pub fn imported_name(alias: &ruff_python_ast::Alias) -> &str {
    alias
        .asname
        .as_ref()
        .unwrap_or(&alias.name)
        .as_str()
        .split('.')
        .next()
        .unwrap_or("")
}

#[derive(Clone, Copy, PartialEq)]
pub enum AnnotationScope {
    Outer,
    Annotation,
    Type,
}

pub fn future_annotations(
    node: &ruff_python_ast::StmtImportFrom,
    minor: PyMinor,
    work: &mut Work,
) -> bool {
    if !is_future(node, minor) {
        return false;
    }
    let mut found = false;
    for alias in &node.names {
        if !work.charge(1) {
            break;
        }
        found |= alias.name.as_str() == "annotations";
    }
    found
}

#[derive(Clone, Copy, PartialEq)]
pub enum LexicalScope {
    Module,
    Class,
    Function,
    Async,
}

pub struct ScopeBindings {
    pub names: HashSet<String>,
    pub globals: HashSet<String>,
    pub yielded: bool,
    pub return_value: bool,
}

pub fn resolves(frame: &ScopeBindings, name: &str) -> Option<bool> {
    if frame.globals.contains(name) {
        Some(false)
    } else {
        frame.names.contains(name).then_some(true)
    }
}

pub fn bindings(body: &[Stmt], work: &mut Work) -> ScopeBindings {
    let mut scan = Bindings {
        names: HashSet::new(),
        globals: HashSet::new(),
        work,
        depth: 0,
        yielded: false,
        return_value: false,
    };
    scan.visit_body(body);
    scan.work.charge(scan.names.len());
    scan.names.retain(|name| !scan.globals.contains(name));
    ScopeBindings {
        names: scan.names,
        globals: scan.globals,
        yielded: scan.yielded,
        return_value: scan.return_value,
    }
}

struct Bindings<'a> {
    names: HashSet<String>,
    globals: HashSet<String>,
    work: &'a mut Work,
    depth: usize,
    yielded: bool,
    return_value: bool,
}

impl Bindings<'_> {
    fn enter(&mut self) -> bool {
        if !self.work.charge(1) {
            return false;
        }
        if self.depth >= 200 {
            self.work.charge(usize::MAX);
            return false;
        }
        self.depth += 1;
        true
    }

    fn imports(&mut self, aliases: &[ruff_python_ast::Alias]) {
        for alias in aliases {
            if !self.work.charge(1) {
                break;
            }
            self.names.insert(imported_name(alias).to_owned());
        }
    }

    fn global(&mut self, names: &[ruff_python_ast::Identifier]) {
        for name in names {
            if !self.work.charge(1) {
                break;
            }
            self.globals.insert(name.to_string());
        }
    }
}

impl<'a> Visitor<'a> for Bindings<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if !self.enter() {
            return;
        }
        match stmt {
            Stmt::FunctionDef(node) => {
                self.names.insert(node.name.to_string());
            }
            Stmt::ClassDef(node) => {
                self.names.insert(node.name.to_string());
            }
            Stmt::Import(node) => self.imports(&node.names),
            Stmt::ImportFrom(node) => self.imports(&node.names),
            Stmt::Global(node) => self.global(&node.names),
            Stmt::Return(node) => {
                self.return_value |= node.value.is_some();
                visitor::walk_stmt(self, stmt);
            }
            _ => visitor::walk_stmt(self, stmt),
        }
        self.depth -= 1;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if !self.enter() {
            return;
        }
        match expr {
            Expr::Name(node) if matches!(node.ctx, ExprContext::Store | ExprContext::Del) => {
                self.names.insert(node.id.to_string());
            }
            Expr::Lambda(_) => {}
            Expr::Yield(_) | Expr::YieldFrom(_) => {
                self.yielded = true;
                visitor::walk_expr(self, expr);
            }
            _ => visitor::walk_expr(self, expr),
        }
        self.depth -= 1;
    }

    fn visit_comprehension(&mut self, node: &'a ruff_python_ast::Comprehension) {
        // Targets bind in the implicit scope; assignment expressions bind outside it.
        self.visit_expr(&node.iter);
        for condition in &node.ifs {
            if !self.work.charge(1) {
                break;
            }
            self.visit_expr(condition);
        }
    }

    fn visit_except_handler(&mut self, handler: &'a ruff_python_ast::ExceptHandler) {
        if !self.enter() {
            return;
        }
        let ruff_python_ast::ExceptHandler::ExceptHandler(node) = handler;
        self.names
            .extend(node.name.as_ref().map(ToString::to_string));
        visitor::walk_except_handler(self, handler);
        self.depth -= 1;
    }

    fn visit_pattern(&mut self, pattern: &'a ruff_python_ast::Pattern) {
        if !self.enter() {
            return;
        }
        self.names
            .extend(super::patterncheck::capture(pattern).map(str::to_owned));
        visitor::walk_pattern(self, pattern);
        self.depth -= 1;
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn comprehension_conditions_have_an_exact_work_charge() {
        let tree = crate::test_tree("[x for x in values if a if b]", 14).unwrap();
        let mut work = super::Work::new();
        let bindings = super::bindings(&tree.body, &mut work);
        assert!(bindings.names.is_empty());
        assert_eq!(work.used(), 8);
    }
}
