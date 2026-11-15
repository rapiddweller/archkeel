// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `globals()` writes of the function `__getattr__` (AD-560): `globals()[key] = value` and the
//! same through a local that is bound only to `globals()`, when the key is an atom.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ExprSubscript, Stmt};
use ruff_text_size::{Ranged, TextRange};

use super::binds::Abs;
use super::flow::Scope;

pub(super) struct Writes<'a> {
    scope: &'a Scope<'a>,
    guarded: bool,
    direct: Vec<TextRange>,
    /// `alias = globals()`: the aliases and the range of the `globals` name.
    pending: Vec<(Vec<String>, TextRange)>,
    used: HashMap<String, usize>,
    total: HashMap<String, usize>,
    invalid: HashSet<String>,
}

impl Writes<'_> {
    /// The ranges of the `globals` names that only write the keys that the table gives.
    pub(super) fn run(scope: &Scope<'_>, body: &[Stmt]) -> Vec<TextRange> {
        let mut found = Writes {
            scope,
            guarded: false,
            direct: Vec::new(),
            pending: Vec::new(),
            used: HashMap::new(),
            total: HashMap::new(),
            invalid: HashSet::new(),
        };
        for (index, stmt) in body.iter().enumerate() {
            found.guarded = scope.guard.is_some_and(|at| index > at);
            found.visit_stmt(stmt);
        }
        let valid = |name: &String| {
            !found.invalid.contains(name) && found.used.get(name) == found.total.get(name)
        };
        let mut out = found.direct.clone();
        for (names, range) in &found.pending {
            if names.iter().all(valid) {
                out.push(*range);
            }
        }
        out
    }

    fn is_globals(expr: &Expr) -> Option<TextRange> {
        let Expr::Call(call) = expr else { return None };
        let empty = call.arguments.args.is_empty() && call.arguments.keywords.is_empty();
        match &*call.func {
            Expr::Name(node) if empty && node.id.as_str() == "globals" => Some(node.range()),
            _ => None,
        }
    }

    fn alias(&self, name: &str) -> bool {
        let all = self.scope.map.get(name);
        all.is_some_and(|all| all.iter().all(|abs| *abs == Abs::Globals))
    }

    fn key_ok(&self, slice: &Expr) -> bool {
        matches!(slice, Expr::Name(key) if self.scope.atom(key.id.as_str(), self.guarded).is_some())
    }

    /// `globals()[key] = value` or `alias[key] = value`.
    fn store(&mut self, target: &ExprSubscript) {
        let ok = self.key_ok(&target.slice);
        if let Some(range) = Self::is_globals(&target.value) {
            if ok {
                self.direct.push(range);
            }
            return;
        }
        let Expr::Name(base) = &*target.value else {
            return;
        };
        if self.alias(base.id.as_str()) {
            *self.used.entry(base.id.to_string()).or_default() += 1;
            if !ok {
                self.invalid.insert(base.id.to_string());
            }
        }
    }

    /// `alias = globals()`.
    fn bind(&mut self, targets: &[Expr], range: TextRange) {
        let mut names = Vec::new();
        for target in targets {
            let Expr::Name(name) = target else { continue };
            if self.alias(name.id.as_str()) {
                *self.used.entry(name.id.to_string()).or_default() += 1;
                names.push(name.id.to_string());
            }
        }
        if names.len() == targets.len() {
            self.pending.push((names, range));
        }
    }
}

impl<'a> Visitor<'a> for Writes<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::Assign(node) = stmt {
            match node.targets.as_slice() {
                [Expr::Subscript(target)] if target.ctx == ExprContext::Store => self.store(target),
                targets => {
                    let range = Self::is_globals(&node.value);
                    range
                        .into_iter()
                        .for_each(|range| self.bind(targets, range));
                }
            }
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if self.alias(node.id.as_str()) {
                *self.total.entry(node.id.to_string()).or_default() += 1;
            }
        }
        visitor::walk_expr(self, expr);
    }
}
