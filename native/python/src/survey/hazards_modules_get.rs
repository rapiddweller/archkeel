// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A `sys.modules.get("text")` whose value is only compared by identity or tested for truth is no
//! import-system change (#2197). The lookup reads the table. It writes nothing, and the value
//! reaches no code: `is` and `is not` run no method, and a truth test of a module object runs
//! none either.
//!
//! The value is safe when each use of it is one of:
//! - an operand of `is` or `is not` (`sys.modules.get("x") is None`, `value is found`);
//! - the whole of a test of an `if`, `elif`, `while`, `assert` or conditional expression, or an
//!   operand of `not`, `and` or `or` inside such a test.
//!
//! The lookup is read in one of two forms: inline in such a use, or bound by one statement
//! `found = sys.modules.get("text")` of a function body whose name has one binding in the module
//! and no `global` or `nonlocal`, and each load of `found` in the function is such a use. Other
//! forms keep the site: a call or an attribute on the value (`.attr`), `==` (it can run `__eq__`), a
//! return, an argument, a store, a lookup with a computed key or a default, `setdefault`, `pop`,
//! `update`, an item write or delete. `sys` must be the standard module, bound once (`Names::sys`),
//! and a lookup at module level keeps its site, because another module can import its name.

use std::collections::HashSet;

use ruff_python_ast::helpers::any_over_body;
use ruff_python_ast::name::Name;
use ruff_python_ast::{CmpOp, Expr, ExprContext, Stmt, StmtFunctionDef, UnaryOp};
use ruff_text_size::{Ranged, TextRange};

use super::walk::{child_bodies, name_of, on_name, positional};

/// The names that the proof reads.
pub(super) struct Names<'a> {
    /// The names bound once to the standard module `sys`.
    pub sys: &'a HashSet<String>,
    /// The names that the module binds exactly once anywhere.
    pub single: &'a HashSet<String>,
    /// The names that a `global` or `nonlocal` statement names.
    pub declared: &'a HashSet<String>,
}

/// Adds the range of the callee `sys.modules.get` of each safe lookup to `found`: the walk of the
/// hazards reports the whole attribute chain.
pub(super) fn lookups(facts: &Names, body: &[Stmt], found: &mut HashSet<TextRange>) {
    let mut safe: HashSet<TextRange> = HashSet::new();
    truth_tests(body, &mut safe);
    any_over_body(body, |expr| {
        in_position(expr, &mut safe);
        false
    });
    any_over_body(body, |expr| {
        if let Some(table) = lookup(facts, expr) {
            if safe.contains(&expr.range()) {
                found.insert(table);
            }
        }
        false
    });
    functions(facts, body, &safe, found);
}

/// The range of the callee in `sys.modules.get("text")`, on the real `sys`.
fn lookup(facts: &Names, expr: &Expr) -> Option<TextRange> {
    let Expr::Call(call) = expr else { return None };
    let Expr::Attribute(get) = &*call.func else {
        return None;
    };
    let table = &*get.value;
    let key = matches!(positional(call)?, [Expr::StringLiteral(_)]);
    let on_sys = on_name(table, "modules").is_some_and(|name| facts.sys.contains(name));
    (get.attr.as_str() == "get" && get.ctx == ExprContext::Load && key && on_sys)
        .then(|| call.func.range())
}

/// Marks `expr` as only tested: it is the test, or an operand of `not`, `and` or `or` in it.
fn truth(expr: &Expr, safe: &mut HashSet<TextRange>) {
    safe.insert(expr.range());
    match expr {
        Expr::BoolOp(node) => node.values.iter().for_each(|value| truth(value, safe)),
        Expr::UnaryOp(node) if node.op == UnaryOp::Not => truth(&node.operand, safe),
        _ => {}
    }
}

/// The tests of the compound statements, at any depth.
fn truth_tests(body: &[Stmt], safe: &mut HashSet<TextRange>) {
    for stmt in body {
        match stmt {
            Stmt::If(node) => {
                truth(&node.test, safe);
                for clause in &node.elif_else_clauses {
                    clause.test.iter().for_each(|test| truth(test, safe));
                }
            }
            Stmt::While(node) => truth(&node.test, safe),
            Stmt::Assert(node) => truth(&node.test, safe),
            _ => {}
        }
        child_bodies(stmt)
            .into_iter()
            .for_each(|inner| truth_tests(inner, safe));
    }
}

/// The expressions that are a safe use wherever they stand: the operands of a chain of `is` and
/// `is not`, the test of a conditional expression, and the operand of `not`.
fn in_position(expr: &Expr, safe: &mut HashSet<TextRange>) {
    match expr {
        Expr::Compare(node)
            if node
                .ops
                .iter()
                .all(|op| matches!(op, CmpOp::Is | CmpOp::IsNot)) =>
        {
            node.operands.iter().for_each(|side| {
                safe.insert(side.range());
            });
        }
        Expr::If(node) => truth(&node.test, safe),
        Expr::UnaryOp(node) if node.op == UnaryOp::Not => truth(&node.operand, safe),
        _ => {}
    }
}

/// Each function at any depth: `found = sys.modules.get("text")` as a statement of its body.
fn functions(
    facts: &Names,
    body: &[Stmt],
    safe: &HashSet<TextRange>,
    found: &mut HashSet<TextRange>,
) {
    for stmt in body {
        if let Stmt::FunctionDef(def) = stmt {
            bound(facts, def, safe, found);
        }
        child_bodies(stmt)
            .into_iter()
            .for_each(|inner| functions(facts, inner, safe, found));
    }
}

fn bound(
    facts: &Names,
    def: &StmtFunctionDef,
    safe: &HashSet<TextRange>,
    found: &mut HashSet<TextRange>,
) {
    for stmt in &def.body {
        let Stmt::Assign(node) = stmt else { continue };
        let ([Expr::Name(target)], Some(table)) =
            (node.targets.as_slice(), lookup(facts, &node.value))
        else {
            continue;
        };
        let id = Name::as_str(&target.id);
        let local = facts.single.contains(id) && !facts.declared.contains(id);
        if local && every_load_is_safe(def, id, safe) {
            found.insert(table);
        }
    }
}

/// True when each load of the name `id` in the function is a safe use.
fn every_load_is_safe(def: &StmtFunctionDef, id: &str, safe: &HashSet<TextRange>) -> bool {
    let mut ok = true;
    any_over_body(&def.body, |expr| {
        if let Expr::Name(node) = expr {
            if node.ctx == ExprContext::Load && name_of(expr) == Some(id) {
                ok &= safe.contains(&node.range());
            }
        }
        false
    });
    ok
}
