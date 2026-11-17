// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a function body hides and uses (AD-520, rules 2 and 3).
//!
//! A name that the function binds in any form, or that a parameter of the function, of a lambda
//! or of a def inside it binds, never means a symbol of the module there. `Bound` is the one
//! reader of binding statements; this file adds only the parameters, which it skips.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Expr, ExprCall, ExprContext, ExprName, Parameter, Stmt, StmtFunctionDef, TypeParam,
};
use ruff_text_size::{Ranged, TextSize};

use super::reader::Reader;
use crate::survey::bound::Bound;

/// The names of every parameter of the function and of each lambda and def inside it.
pub(super) fn parameters(node: &StmtFunctionDef) -> HashSet<String> {
    let mut found = Params::default();
    if let Some(params) = &node.type_params {
        found.visit_type_params(params);
    }
    found.visit_parameters(&node.parameters);
    found.visit_body(&node.body);
    found.names
}

/// True when the direct, undecorated function definition is the only binder of `name` in `node`.
pub(super) fn direct_local_function(node: &StmtFunctionDef, name: &str) -> bool {
    let bound = Bound::of(&node.body);
    node.body.iter().any(|statement| {
        let Stmt::FunctionDef(function) = statement else {
            return false;
        };
        function.name.as_str() == name
            && function.decorator_list.is_empty()
            && bound.sole(name, statement.range().start())
    })
}

/// The names that the type parameters of a def bind (PEP 695): they hide in its annotations too.
pub(super) fn type_names(node: &StmtFunctionDef) -> HashSet<String> {
    let mut found = Params::default();
    if let Some(params) = &node.type_params {
        found.visit_type_params(params);
    }
    found.names
}

#[derive(Default)]
struct Params {
    names: HashSet<String>,
}

impl<'a> Visitor<'a> for Params {
    /// A type parameter of a def (PEP 695) binds its name in the annotations and the body.
    fn visit_type_param(&mut self, param: &'a TypeParam) {
        let name = match param {
            TypeParam::TypeVar(item) => &item.name,
            TypeParam::ParamSpec(item) => &item.name,
            TypeParam::TypeVarTuple(item) => &item.name,
        };
        self.names.insert(name.to_string());
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.names.insert(parameter.name.to_string());
    }
}

/// The calls and the names that a function body reads, outside the defs, classes and lambdas
/// inside it, in source order. A site is `dead` under a constant-false test or after a statement
/// that leaves the block: Python never runs it, so the survey never states it as met (AD-520).
#[derive(Default)]
pub(super) struct Uses<'a> {
    pub calls: Vec<(&'a ExprCall, bool)>,
    pub names: Vec<(&'a ExprName, bool)>,
    callees: HashSet<usize>,
    dead: bool,
}

impl<'a> Uses<'a> {
    pub(super) fn of(node: &'a StmtFunctionDef) -> Self {
        let mut found = Uses::default();
        found.visit_body(&node.body);
        found
    }

    /// Visit `body` as dead when `dead` is true.
    fn within(&mut self, dead: bool, body: &'a [Stmt]) {
        let before = self.dead;
        self.dead |= dead;
        self.visit_body(body);
        self.dead = before;
    }
}

/// True for a test that is false whenever it is evaluated: `False`, `0`, `None`, `""`,
/// `TYPE_CHECKING` and `typing.TYPE_CHECKING`.
fn never(test: &Expr) -> bool {
    match test {
        Expr::BooleanLiteral(node) => !node.value,
        Expr::NoneLiteral(_) => true,
        Expr::NumberLiteral(node) => is_zero(node),
        Expr::StringLiteral(node) => node.value.to_str().is_empty(),
        Expr::Name(node) => node.id.as_str() == "TYPE_CHECKING",
        Expr::Attribute(node) => node.attr.as_str() == "TYPE_CHECKING",
        _ => false,
    }
}

fn is_zero(node: &ruff_python_ast::ExprNumberLiteral) -> bool {
    match &node.value {
        ruff_python_ast::Number::Int(value) => value.to_string() == "0",
        ruff_python_ast::Number::Float(value) => *value == 0.0,
        ruff_python_ast::Number::Complex { .. } => false,
    }
}

impl<'a> Visitor<'a> for Uses<'a> {
    fn visit_body(&mut self, body: &'a [Stmt]) {
        let before = self.dead;
        for stmt in body {
            self.visit_stmt(stmt);
            if matches!(
                stmt,
                Stmt::Return(_) | Stmt::Raise(_) | Stmt::Continue(_) | Stmt::Break(_)
            ) {
                self.dead = true;
            }
        }
        self.dead = before;
    }

    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {}
            Stmt::If(node) => {
                self.visit_expr(&node.test);
                self.within(never(&node.test), &node.body);
                for clause in &node.elif_else_clauses {
                    let dead = clause.test.as_ref().is_some_and(never);
                    clause.test.iter().for_each(|test| self.visit_expr(test));
                    self.within(dead, &clause.body);
                }
            }
            Stmt::While(node) => {
                self.visit_expr(&node.test);
                self.within(never(&node.test), &node.body);
                self.visit_body(&node.orelse);
            }
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Lambda(_) => return,
            Expr::Call(call) => {
                self.calls.push((call, self.dead));
                if let Expr::Name(callee) = &*call.func {
                    self.callees.insert(std::ptr::from_ref(callee).addr());
                }
            }
            Expr::Name(name)
                if name.ctx == ExprContext::Load
                    && !self.callees.contains(&std::ptr::from_ref(name).addr()) =>
            {
                self.names.push((name, self.dead));
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

/// A result binding: the name that `name = call()` stores, its annotation and its statement.
pub(super) struct Stored<'a> {
    pub name: &'a str,
    pub annotation: Option<String>,
    pub statement: &'a Stmt,
    pub initializer: String,
}

/// The direct statements `name = call()` and `name: T = call()` of a function body, by the start
/// of the call. `name` is written once in the function (`Bound::sole`) and no parameter shares it.
pub(super) fn stored<'a>(
    node: &'a StmtFunctionDef,
    reader: &Reader<'_, '_>,
    params: &HashSet<String>,
) -> HashMap<TextSize, Stored<'a>> {
    let bound = Bound::of(&node.body);
    let mut found = HashMap::new();
    for statement in &node.body {
        let (target, value, annotation) = match statement {
            Stmt::Assign(item) if item.targets.len() == 1 => (&item.targets[0], &*item.value, None),
            Stmt::AnnAssign(item) => match item.value.as_deref() {
                Some(value) => (&*item.target, value, Some(&*item.annotation)),
                None => continue,
            },
            _ => continue,
        };
        let (Expr::Name(name), Expr::Call(_)) = (target, value) else {
            continue;
        };
        let text = annotation.map(|expr| reader.text(Some(expr)));
        let annotation = match text {
            Some(Ok(text)) => text,
            Some(Err(_)) => continue,
            None => None,
        };
        let Ok(Some(initializer)) = reader.text(Some(value)) else {
            continue;
        };
        let name = name.id.as_str();
        if bound.sole(name, statement.range().start()) && !params.contains(name) {
            found.insert(
                value.range().start(),
                Stored {
                    name,
                    annotation,
                    statement,
                    initializer,
                },
            );
        }
    }
    found
}
