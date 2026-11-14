// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Partial CPython checks after the grammar. Known unchecked classes keep #1072 open.
use super::work::Work;
use ruff_python_ast::{
    visitor::{self, Visitor},
    Expr, ModModule, Parameters, Stmt,
};
use ruff_text_size::Ranged;
use std::collections::HashSet;

const MAX_DEPTH: usize = 1000;
use super::scopecheck::LexicalScope as Scope;
struct Check {
    work: Work,
    depth: usize,
    scope: Scope,
    loops: usize,
    seen: HashSet<String>,
    globals: HashSet<String>,
    nonlocals: HashSet<String>,
    except_star: Option<usize>,
    in_call: bool,
    debug_attribute: bool,
    reason: Option<&'static str>,
    offset: usize,
    minor: archkeel_facts::pyminor::PyMinor,
    source: String,
    outer: Vec<super::scopecheck::ScopeBindings>,
}

/// A named refusal with its source offset. The visitor stops before a depth or work limit.
pub(super) fn check(
    module: &ModModule,
    source: &str,
    minor: archkeel_facts::pyminor::PyMinor,
) -> Option<(usize, &'static str)> {
    let mut check = Check {
        work: Work::new(),
        depth: 0,
        scope: Scope::Module,
        loops: 0,
        seen: HashSet::new(),
        globals: HashSet::new(),
        nonlocals: HashSet::new(),
        except_star: None,
        in_call: false,
        debug_attribute: false,
        reason: None,
        offset: 0,
        minor,
        source: source.to_owned(),
        outer: Vec::new(),
    };
    check.visit_body(&module.body);
    check
        .reason
        .or_else(|| check.work.failure())
        .map(|reason| (check.offset, reason))
}

impl Check {
    fn async_allowed(&self, asynchronous: bool) -> bool {
        !asynchronous || self.scope == Scope::Async
    }
    fn loop_control_allowed(&self) -> bool {
        self.loops > 0 && self.except_star.is_none_or(|floor| self.loops > floor)
    }
    fn fail(&mut self, reason: &'static str) {
        if self.reason.is_none() {
            self.reason = Some(reason);
        }
    }

    fn enter(&mut self, node: &impl Ranged) -> bool {
        if self.reason.is_some() {
            return false;
        }
        self.offset = node.start().to_usize();
        if !self.work.charge(1) {
            self.fail("CPython validation work limit exceeded");
            return false;
        }
        if self.depth >= MAX_DEPTH {
            self.fail("CPython validation depth limit exceeded");
            return false;
        }
        self.depth += 1;
        true
    }

    fn scoped(&mut self, scope: Scope, body: &[Stmt], parameters: Option<&Parameters>) {
        let old = (
            self.scope,
            self.loops,
            std::mem::take(&mut self.seen),
            std::mem::take(&mut self.globals),
            std::mem::take(&mut self.nonlocals),
            self.except_star.take(),
        );
        self.scope = scope;
        self.loops = 0;
        self.parameter_names(parameters);
        let mut bindings = super::scopecheck::bindings(body, &mut self.work);
        if scope == Scope::Class {
            bindings.names.clear();
        }
        if scope == Scope::Async && bindings.yielded && bindings.return_value {
            self.fail("return value inside an async generator");
        }
        bindings.names.extend(self.seen.iter().cloned());
        self.outer.push(bindings);
        self.visit_body(body);
        self.outer.pop();
        (
            self.scope,
            self.loops,
            self.seen,
            self.globals,
            self.nonlocals,
            self.except_star,
        ) = old;
    }

    fn comprehension(&mut self, expr: &Expr) {
        let Some((generators, values)) = super::expressioncheck::comprehension_parts(expr) else {
            return;
        };
        if let Some(first) = generators.first() {
            self.visit_expr(&first.iter);
        }
        let old = (self.scope, std::mem::take(&mut self.seen));
        if matches!(expr, Expr::Generator(_)) {
            self.scope = Scope::Async;
        }
        for (index, generator) in generators.iter().enumerate() {
            if !self.work.charge(1) {
                break;
            }
            if generator.is_async && self.scope != Scope::Async {
                self.fail("asynchronous comprehension outside an async function");
            }
            self.visit_expr(&generator.target);
            if index > 0 {
                self.visit_expr(&generator.iter);
            }
            if !self.work.charge(generator.ifs.len()) {
                break;
            }
            for condition in &generator.ifs {
                self.visit_expr(condition);
            }
        }
        self.work.charge(values.len());
        for value in values {
            self.visit_expr(value);
        }
        (self.scope, self.seen) = old;
    }

    fn parameter_names(&mut self, parameters: Option<&Parameters>) {
        if let Some(reason) = super::expressioncheck::parameters(parameters, &mut self.work) {
            self.fail(reason);
        }
        let Some(parameters) = parameters else {
            return;
        };
        if !self.work.charge(parameters.len()) {
            return;
        }
        self.seen.extend(
            parameters
                .iter()
                .map(|parameter| parameter.name().to_string()),
        );
    }

    fn function(&mut self, node: &ruff_python_ast::StmtFunctionDef) {
        self.definition(node.name.as_str(), &node.decorator_list);
        // Headers evaluate outside the new scope; walk them before the body.
        self.visit_parameters(&node.parameters);
        if let Some(returns) = &node.returns {
            self.visit_expr(returns);
        }
        self.scoped(
            if node.is_async {
                Scope::Async
            } else {
                Scope::Function
            },
            &node.body,
            Some(&node.parameters),
        );
    }

    fn nonlocal(&mut self, names: &[ruff_python_ast::Identifier]) {
        for name in names {
            if !self.work.charge(self.outer.len().saturating_add(1)) {
                break;
            }
            let outer = self
                .outer
                .get(..self.outer.len().saturating_sub(1))
                .unwrap_or(&[]);
            if self.scope == Scope::Module
                || self.seen.contains(name.as_str())
                || self.globals.contains(name.as_str())
                || !outer
                    .iter()
                    .rev()
                    .find_map(|frame| super::scopecheck::resolves(frame, name.as_str()))
                    .unwrap_or(false)
            {
                self.fail("nonlocal declaration has no valid enclosing binding");
            }
            self.nonlocals.insert(name.to_string());
        }
    }

    fn global(&mut self, names: &[ruff_python_ast::Identifier]) {
        for name in names {
            if !self.work.charge(1) {
                break;
            }
            if self.nonlocals.contains(name.as_str())
                || (self.seen.contains(name.as_str()) && !self.globals.contains(name.as_str()))
            {
                self.fail("name used or assigned before global declaration");
            }
            self.globals.insert(name.to_string());
        }
    }

    fn class(&mut self, node: &ruff_python_ast::StmtClassDef) {
        self.definition(node.name.as_str(), &node.decorator_list);
        if let Some(arguments) = &node.arguments {
            let old = std::mem::replace(&mut self.in_call, true);
            self.visit_arguments(arguments);
            self.in_call = old;
        }
        self.scoped(Scope::Class, &node.body, None);
    }

    fn for_loop(&mut self, node: &ruff_python_ast::StmtFor) {
        if !self.async_allowed(node.is_async) {
            self.fail("async for outside an async function");
        }
        if let Some(reason) = super::expressioncheck::target(&node.target, false, &mut self.work, 0)
        {
            self.fail(reason);
        }
        self.visit_expr(&node.iter);
        self.visit_expr(&node.target);
        self.loops += 1;
        self.visit_body(&node.body);
        self.loops -= 1;
        self.visit_body(&node.orelse);
    }

    fn definition(&mut self, name: &str, decorators: &[ruff_python_ast::Decorator]) {
        if name == "__debug__" {
            self.fail("cannot bind __debug__");
        }
        self.seen.insert(name.to_owned());
        for decorator in decorators {
            self.visit_expr(&decorator.expression);
        }
    }

    fn try_star(&mut self, node: &ruff_python_ast::StmtTry) {
        self.visit_body(&node.body);
        for handler in &node.handlers {
            if !self.work.charge(1) {
                break;
            }
            let ruff_python_ast::ExceptHandler::ExceptHandler(handler) = handler;
            if handler
                .name
                .as_ref()
                .is_some_and(|name| name.as_str() == "__debug__")
            {
                self.fail("cannot bind __debug__");
            }
            if let Some(ty) = &handler.type_ {
                self.visit_expr(ty);
            }
            let old = self.except_star.replace(self.loops);
            self.visit_body(&handler.body);
            self.except_star = old;
        }
        self.visit_body(&node.orelse);
        self.visit_body(&node.finalbody);
    }

    fn import_from(&mut self, node: &ruff_python_ast::StmtImportFrom) {
        if !self.work.charge(node.names.len()) {
            return;
        }
        let future = super::scopecheck::is_future(node, self.minor);
        if future && (self.scope != Scope::Module || self.depth != 1) {
            self.fail("future import is not at the start of the module");
        }
        if self.scope != Scope::Module && node.names.iter().any(|alias| alias.name.as_str() == "*")
        {
            self.fail("star import outside module scope");
        }
        for alias in &node.names {
            self.visit_alias(alias);
        }
    }
}

impl<'a> Visitor<'a> for Check {
    fn visit_body(&mut self, body: &'a [Stmt]) {
        for stmt in body {
            if !self.work.charge(1) {
                break;
            }
            if self.reason.is_some() {
                break;
            }
            self.visit_stmt(stmt);
        }
    }

    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if !self.enter(stmt) {
            return;
        }
        let debug_attribute = std::mem::replace(
            &mut self.debug_attribute,
            matches!(stmt, Stmt::AugAssign(_) | Stmt::Delete(_)),
        );
        match stmt {
            Stmt::FunctionDef(node) => self.function(node),
            Stmt::ClassDef(node) => self.class(node),
            Stmt::Return(_) if self.except_star.is_some() => {
                self.fail("return exits an except-star handler")
            }
            Stmt::Return(_) if !matches!(self.scope, Scope::Function | Scope::Async) => {
                self.fail("return outside a function")
            }
            Stmt::Break(_) | Stmt::Continue(_) if !self.loop_control_allowed() => {
                self.fail("loop control outside a loop")
            }
            Stmt::Nonlocal(node) => self.nonlocal(&node.names),
            Stmt::Global(node) => self.global(&node.names),
            Stmt::ImportFrom(node) => self.import_from(node),
            Stmt::For(node) => self.for_loop(node),
            Stmt::While(node) => {
                self.visit_expr(&node.test);
                self.loops += 1;
                self.visit_body(&node.body);
                self.loops -= 1;
                self.visit_body(&node.orelse);
            }
            Stmt::Assign(node) => {
                if let Some(reason) =
                    super::expressioncheck::assignment(&node.targets, &mut self.work)
                {
                    self.fail(reason);
                }
                visitor::walk_stmt(self, stmt);
            }
            Stmt::Match(node) => {
                if let Some(reason) = super::patterncheck::check(&node.cases, &mut self.work) {
                    self.fail(reason);
                }
                visitor::walk_stmt(self, stmt);
            }
            Stmt::With(node) if !self.async_allowed(node.is_async) => {
                self.fail("async with outside an async function")
            }
            Stmt::AnnAssign(node) if matches!(&*node.target, Expr::Name(name) if self.globals.contains(name.id.as_str()) || self.nonlocals.contains(name.id.as_str())) => {
                self.fail("annotated name is global or nonlocal")
            }
            Stmt::Try(node) if node.is_star => self.try_star(node),
            _ => visitor::walk_stmt(self, stmt),
        }
        self.depth -= 1;
        self.debug_attribute = debug_attribute;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if !self.enter(expr) {
            return;
        }
        let in_call = self.in_call;
        self.in_call = matches!(expr, Expr::Call(_));
        if let Some(reason) =
            super::stringcheck::check(expr, &self.source, self.minor, &mut self.work)
        {
            self.fail(reason);
        }
        if let Some(reason) = super::expressioncheck::check(
            expr,
            self.scope == Scope::Class,
            self.debug_attribute,
            self.minor,
            &mut self.work,
        ) {
            self.fail(reason);
        }
        match expr {
            Expr::Name(node) => {
                self.seen.insert(node.id.to_string());
            }
            Expr::Yield(_) | Expr::YieldFrom(_)
                if !matches!(self.scope, Scope::Function | Scope::Async) =>
            {
                self.fail("yield outside a function")
            }
            Expr::YieldFrom(_) if self.scope == Scope::Async => {
                self.fail("yield from inside an async function")
            }
            Expr::Await(_) if self.scope != Scope::Async => {
                self.fail("await outside an async function")
            }
            Expr::Lambda(node) => {
                if let Some(parameters) = &node.parameters {
                    self.visit_parameters(parameters);
                }
                let old = (self.scope, std::mem::take(&mut self.seen));
                self.scope = Scope::Function;
                self.visit_expr(&node.body);
                (self.scope, self.seen) = old;
            }
            Expr::Generator(_) | Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) => {
                self.comprehension(expr)
            }
            Expr::Starred(node) if !in_call && matches!(&*node.value, Expr::BoolOp(_)) => {
                let source = self.source.get(node.range.to_std_range()).unwrap_or("");
                if !super::expressioncheck::grouped_star(source, &mut self.work) {
                    self.fail(
                        "starred expression cannot contain an unparenthesized boolean expression",
                    );
                }
                visitor::walk_expr(self, expr);
            }
            _ => visitor::walk_expr(self, expr),
        }
        self.depth -= 1;
        self.in_call = in_call;
    }

    fn visit_alias(&mut self, alias: &'a ruff_python_ast::Alias) {
        if !self.work.charge(1) {
            return;
        }
        let name = super::scopecheck::imported_name(alias);
        if name == "__debug__" {
            self.fail("cannot bind __debug__");
        }
    }

    fn visit_keyword(&mut self, keyword: &'a ruff_python_ast::Keyword) {
        if keyword
            .arg
            .as_ref()
            .is_some_and(|name| name.as_str() == "__debug__")
        {
            self.fail("cannot bind __debug__");
        }
        self.visit_expr(&keyword.value);
    }

    fn visit_except_handler(&mut self, handler: &'a ruff_python_ast::ExceptHandler) {
        let ruff_python_ast::ExceptHandler::ExceptHandler(node) = handler;
        if node
            .name
            .as_ref()
            .is_some_and(|name| name.as_str() == "__debug__")
        {
            self.fail("cannot bind __debug__");
        }
        self.seen
            .extend(node.name.as_ref().map(ToString::to_string));
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a ruff_python_ast::Pattern) {
        if !self.enter(pattern) {
            return;
        }
        self.seen
            .extend(super::patterncheck::capture(pattern).map(str::to_owned));
        visitor::walk_pattern(self, pattern);
        self.depth -= 1;
    }
}

#[cfg(test)]
#[path = "postparse_tests.rs"]
mod tests;
