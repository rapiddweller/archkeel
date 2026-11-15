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
use ruff_python_ast::{Expr, ExprCall, ExprContext, ExprName, Parameter, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextSize};

use super::reader::Reader;
use crate::survey::bound::Bound;

/// The names of every parameter of the function and of each lambda and def inside it.
pub(super) fn parameters(node: &StmtFunctionDef) -> HashSet<String> {
    let mut found = Params::default();
    found.visit_parameters(&node.parameters);
    found.visit_body(&node.body);
    found.names
}

#[derive(Default)]
struct Params {
    names: HashSet<String>,
}

impl<'a> Visitor<'a> for Params {
    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.names.insert(parameter.name.to_string());
    }
}

/// The calls and the names that a function body reads, outside the defs, classes and lambdas
/// inside it, in source order.
#[derive(Default)]
pub(super) struct Uses<'a> {
    pub calls: Vec<&'a ExprCall>,
    pub names: Vec<&'a ExprName>,
    callees: HashSet<usize>,
}

impl<'a> Uses<'a> {
    pub(super) fn of(node: &'a StmtFunctionDef) -> Self {
        let mut found = Uses::default();
        found.visit_body(&node.body);
        found
    }
}

impl<'a> Visitor<'a> for Uses<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if !matches!(stmt, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            visitor::walk_stmt(self, stmt);
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Lambda(_) => return,
            Expr::Call(call) => {
                self.calls.push(call);
                if let Expr::Name(callee) = &*call.func {
                    self.callees.insert(std::ptr::from_ref(callee).addr());
                }
            }
            Expr::Name(name)
                if name.ctx == ExprContext::Load
                    && !self.callees.contains(&std::ptr::from_ref(name).addr()) =>
            {
                self.names.push(name);
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
