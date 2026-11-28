// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shapes of expressions that the annotation rules read: names and assignments.

use ruff_python_ast::{Expr, Identifier, Stmt};

/// True for `Literal` and `typing.Literal`: its strings are values, no annotation.
pub(in crate::survey::hazards) fn literal(value: &Expr) -> bool {
    named(value, "Literal")
}

pub(super) fn named(value: &Expr, name: &str) -> bool {
    match value {
        Expr::Name(node) => node.id.as_str() == name,
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == name,
        _ => false,
    }
}

pub(super) fn last(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(node) => Some(node.id.as_str()),
        Expr::Attribute(node) => Some(Identifier::as_str(&node.attr)),
        _ => None,
    }
}

/// Each `target = value` of a statement: an assignment, or an annotated assignment with a value.
pub(super) fn assigned<'a>(stmt: &'a Stmt, mut each: impl FnMut(&'a Expr, &'a Expr)) {
    match stmt {
        Stmt::Assign(node) => node.targets.iter().for_each(|t| each(t, &node.value)),
        Stmt::AnnAssign(node) => node.value.iter().for_each(|v| each(&node.target, v)),
        _ => {}
    }
}
