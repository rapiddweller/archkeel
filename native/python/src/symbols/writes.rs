// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `source_proofs.class_instance_member_write_names`: the members that the methods of a class
//! write or delete on their receiver, and `*` when the receiver escapes.
//!
//! The walk is the one of `_instance_member_write_nodes`: depth first in field order, with the
//! aliases of the receiver that the statements before bind. It keeps its work on a heap stack.

use std::collections::{BTreeSet, HashSet};

use ruff_python_ast::{Expr, ExprContext, Stmt, StmtClassDef, StmtFunctionDef};

use crate::pyast::{child_nodes, walk, Node};

/// The sorted member names of `class_instance_member_write_names`.
pub(super) fn instance_member_writes(
    node: &StmtClassDef,
    minor: archkeel_facts::pyminor::PyMinor,
) -> Vec<String> {
    let mut names = BTreeSet::new();
    for child in &node.body {
        if let Stmt::FunctionDef(method) = child {
            names.extend(method_writes(method, minor));
        }
    }
    names.into_iter().collect()
}

fn contains_alias(
    node: &Node<'_>,
    aliases: &HashSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) -> bool {
    walk(node.clone(), minor).any(|child| {
        matches!(child.expr(), Some(Expr::Name(name)) if aliases.contains(name.id.as_str()))
    })
}

fn expr_contains(
    expr: &Expr,
    aliases: &HashSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) -> bool {
    contains_alias(&Node::Expr(expr), aliases, minor)
}

/// `_receiver_escapes_in_value`, with its recursion over a display bounded by the parse depth.
fn escapes(
    value: &Expr,
    aliases: &HashSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) -> bool {
    let mut pending = vec![value];
    while let Some(value) = pending.pop() {
        let found = match value {
            Expr::Name(name) => aliases.contains(name.id.as_str()),
            Expr::Tuple(node) => {
                pending.extend(node.elts.iter());
                false
            }
            Expr::List(node) => {
                pending.extend(node.elts.iter());
                false
            }
            Expr::Set(node) => {
                pending.extend(node.elts.iter());
                false
            }
            Expr::Subscript(node) => expr_contains(&node.value, aliases, minor),
            Expr::Dict(node) => {
                pending.extend(node.items.iter().filter_map(|item| item.key.as_ref()));
                pending.extend(node.items.iter().map(|item| &item.value));
                false
            }
            Expr::If(node) => {
                pending.extend([&*node.body, &*node.orelse]);
                false
            }
            Expr::Lambda(node) => expr_contains(&node.body, aliases, minor),
            Expr::Call(node) => {
                node.arguments
                    .args
                    .iter()
                    .any(|arg| expr_contains(arg, aliases, minor))
                    || node
                        .arguments
                        .keywords
                        .iter()
                        .any(|keyword| expr_contains(&keyword.value, aliases, minor))
            }
            _ => false,
        };
        if found {
            return true;
        }
    }
    false
}

/// The names of `Name` nodes with a `Store` context, in walk order.
pub(super) fn store_names(
    targets: &[Expr],
    minor: archkeel_facts::pyminor::PyMinor,
) -> Vec<String> {
    targets
        .iter()
        .flat_map(|target| walk(Node::Expr(target), minor))
        .filter_map(|node| match node.expr() {
            Some(Expr::Name(name)) if name.ctx == ExprContext::Store => Some(name.id.to_string()),
            _ => None,
        })
        .collect()
}

fn is_scope(node: &Node<'_>) -> bool {
    matches!(
        node,
        Node::Stmt(Stmt::FunctionDef(_) | Stmt::ClassDef(_)) | Node::Expr(Expr::Lambda(_))
    )
}

fn method_writes(
    node: &StmtFunctionDef,
    minor: archkeel_facts::pyminor::PyMinor,
) -> BTreeSet<String> {
    let params = &node.parameters;
    let Some(first) = params.posonlyargs.iter().chain(&params.args).next() else {
        return BTreeSet::new();
    };
    let mut aliases: HashSet<String> = HashSet::from([first.parameter.name.to_string()]);
    let mut writes = BTreeSet::new();
    let mut pending: Vec<Node<'_>> = node.body.iter().rev().map(Node::Stmt).collect();
    while let Some(child) = pending.pop() {
        if is_scope(&child) {
            if contains_alias(&child, &aliases, minor) {
                writes.insert("*".to_owned());
            }
            continue;
        }
        pending.extend(child_nodes(&child, minor).into_iter().rev());
        match &child {
            Node::Stmt(stmt) => statement(stmt, &mut aliases, &mut writes, minor),
            Node::Expr(expr) => expression(expr, &aliases, &mut writes, minor),
            _ => {}
        }
    }
    writes
}

fn statement(
    stmt: &Stmt,
    aliases: &mut HashSet<String>,
    writes: &mut BTreeSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) {
    match stmt {
        Stmt::Assign(node) => {
            let targets = store_names(&node.targets, minor);
            if matches!(&*node.value, Expr::Name(name) if aliases.contains(name.id.as_str())) {
                aliases.extend(targets);
            } else if !targets.is_empty() && escapes(&node.value, aliases, minor) {
                writes.insert("*".to_owned());
            }
        }
        Stmt::AnnAssign(node) => match node.value.as_deref() {
            Some(Expr::Name(value)) if aliases.contains(value.id.as_str()) => {
                if let Expr::Name(target) = &*node.target {
                    aliases.insert(target.id.to_string());
                }
            }
            Some(value) if escapes(value, aliases, minor) => {
                writes.insert("*".to_owned());
            }
            _ => {}
        },
        Stmt::Return(node)
            if node
                .value
                .as_deref()
                .is_some_and(|value| escapes(value, aliases, minor)) =>
        {
            writes.insert("*".to_owned());
        }
        _ => {}
    }
}

fn expression(
    expr: &Expr,
    aliases: &HashSet<String>,
    writes: &mut BTreeSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) {
    match expr {
        Expr::Attribute(node) if node.ctx != ExprContext::Load => {
            if matches!(&*node.value, Expr::Name(name) if aliases.contains(name.id.as_str())) {
                writes.insert(node.attr.to_string());
            } else if expr_contains(&node.value, aliases, minor) {
                writes.insert("*".to_owned());
            }
        }
        Expr::Subscript(node) if node.ctx != ExprContext::Load => {
            if expr_contains(&node.value, aliases, minor) {
                writes.insert("*".to_owned());
            }
        }
        Expr::Yield(node) => {
            if node
                .value
                .as_deref()
                .is_some_and(|value| escapes(value, aliases, minor))
            {
                writes.insert("*".to_owned());
            }
        }
        Expr::YieldFrom(node) => {
            if escapes(&node.value, aliases, minor) {
                writes.insert("*".to_owned());
            }
        }
        Expr::Call(node) => call(node, aliases, writes, minor),
        _ => {}
    }
}

fn call(
    node: &ruff_python_ast::ExprCall,
    aliases: &HashSet<String>,
    writes: &mut BTreeSet<String>,
    minor: archkeel_facts::pyminor::PyMinor,
) {
    let args = &node.arguments.args;
    let reflective =
        matches!(&*node.func, Expr::Name(name) if name.id == "setattr" || name.id == "delattr");
    if reflective {
        let on_alias =
            matches!(args.first(), Some(Expr::Name(name)) if aliases.contains(name.id.as_str()));
        let member = match args.get(1) {
            Some(Expr::StringLiteral(text)) => text.value.to_str().to_owned(),
            _ => "*".to_owned(),
        };
        if on_alias {
            writes.insert(member);
        }
    } else if args.iter().any(|arg| expr_contains(arg, aliases, minor))
        || node
            .arguments
            .keywords
            .iter()
            .any(|keyword| expr_contains(&keyword.value, aliases, minor))
    {
        writes.insert("*".to_owned());
    }
}
