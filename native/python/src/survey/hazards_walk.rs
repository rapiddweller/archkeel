// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The small readers of the syntax that the proofs of the inert reads share (AD-574, AD-1276).

use ruff_python_ast::name::Name;
use ruff_python_ast::{
    ElifElseClause, ExceptHandler, Expr, ExprCall, ExprContext, Identifier, Keyword, Stmt,
};

/// The name of a plain `Name` expression.
pub(super) fn name_of(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(node) => Some(Name::as_str(&node.id)),
        _ => None,
    }
}

/// The name `base` of the load `base.attr`.
pub(super) fn on_name<'e>(expr: &'e Expr, attr: &str) -> Option<&'e str> {
    match expr {
        Expr::Attribute(node) if Identifier::as_str(&node.attr) == attr => {
            name_of(&node.value).filter(|_| node.ctx == ExprContext::Load)
        }
        _ => None,
    }
}

/// The positional arguments of a call that has no keyword argument.
pub(super) fn positional(call: &ExprCall) -> Option<&[Expr]> {
    let args: &[Expr] = &call.arguments.args;
    let keywords: &[Keyword] = &call.arguments.keywords;
    keywords.is_empty().then_some(args)
}

/// The statement lists that a statement holds.
pub(super) fn child_bodies(stmt: &Stmt) -> Vec<&[Stmt]> {
    match stmt {
        Stmt::FunctionDef(node) => vec![&node.body],
        Stmt::ClassDef(node) => vec![&node.body],
        Stmt::If(node) => {
            let clauses: &[ElifElseClause] = &node.elif_else_clauses;
            let mut found: Vec<&[Stmt]> = vec![&node.body];
            found.extend(clauses.iter().map(|clause| clause.body.as_slice()));
            found
        }
        Stmt::For(node) => vec![&node.body, &node.orelse],
        Stmt::While(node) => vec![&node.body, &node.orelse],
        Stmt::With(node) => vec![&node.body],
        Stmt::Try(node) => {
            let handlers: &[ExceptHandler] = &node.handlers;
            let mut found: Vec<&[Stmt]> = vec![&node.body, &node.orelse, &node.finalbody];
            for ExceptHandler::ExceptHandler(handler) in handlers {
                found.push(&handler.body);
            }
            found
        }
        Stmt::Match(node) => node.cases.iter().map(|case| case.body.as_slice()).collect(),
        _ => Vec::new(),
    }
}
