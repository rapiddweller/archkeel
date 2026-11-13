// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Syntax-only type protection; executable operands stay unprotected.

use super::super::super::environment::Env;
use super::super::super::scan::{Result, Scan};
use super::super::types;
use crate::pyast::Node;
use ruff_python_ast::{Expr, Operator, Stmt};
use std::collections::HashSet;

pub(super) type Refs = HashSet<(&'static str, usize)>;

pub(super) fn key(node: &Node<'_>) -> (&'static str, usize) {
    let pointer = match node {
        Node::Expr(n) => std::ptr::from_ref(*n).cast::<()>() as usize,
        Node::Arg(n) => std::ptr::from_ref(*n).cast::<()>() as usize,
        Node::Keyword(n) => std::ptr::from_ref(*n).cast::<()>() as usize,
        Node::Arguments(Some(n)) => std::ptr::from_ref(*n).cast::<()>() as usize,
        _ => 0,
    };
    (node.kind(), pointer)
}

pub(super) fn annotations<'a>(scan: &mut Scan, nodes: &[Node<'a>]) -> Result<Vec<&'a Expr>> {
    let mut annotations = Vec::new();
    let mut returns = Vec::new();
    let mut aliases = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        match node {
            Node::Arg(p) => annotations.extend(p.annotation.as_deref()),
            Node::Stmt(Stmt::AnnAssign(n)) => annotations.push(&n.annotation),
            Node::Stmt(Stmt::FunctionDef(n)) => returns.extend(n.returns.as_deref()),
            Node::Stmt(Stmt::TypeAlias(n)) => aliases.push(&*n.value),
            _ => {}
        }
    }
    scan.tick(returns.len().saturating_add(aliases.len()))?;
    annotations.extend(returns);
    annotations.extend(aliases);
    Ok(annotations)
}

pub(super) fn root<'a>(scan: &mut Scan, mut expr: &'a Expr) -> Result<Option<&'a str>> {
    while let Expr::Attribute(n) = expr {
        scan.tick(1)?;
        expr = &n.value;
    }
    Ok(match expr {
        Expr::Name(n) => Some(n.id.as_str()),
        _ => None,
    })
}

pub(super) fn bare(env: &Env<'_>, node: &Expr, names: &[&str]) -> bool {
    matches!(node, Expr::Name(n) if names.contains(&n.id.as_str()) && !env.opaque && !env.bound.contains(n.id.as_str()))
}

pub(super) fn references(scan: &mut Scan, env: &Env<'_>, expressions: &[&Expr]) -> Result<Refs> {
    scan.tick(expressions.len())?;
    let mut pending = expressions.to_vec();
    let mut protected = HashSet::new();
    while let Some(node) = pending.pop() {
        scan.tick(1)?;
        match node {
            Expr::Name(_) => {
                protected.insert(key(&Node::Expr(node)));
            }
            Expr::Attribute(_) if root(scan, node)?.is_some() => {
                for child in scan.walk(Node::Expr(node))? {
                    scan.tick(1)?;
                    protected.insert(key(&child));
                }
            }
            Expr::Subscript(n) => {
                pending.push(&n.value);
                if types::static_alias(scan, env, node)?
                    && root(scan, &n.value)?.is_some_and(|root| {
                        !env.bound.contains(root)
                            || scan.aliases.contains_key(root)
                                && env.stable.contains(root)
                                && env.unique.contains(root)
                    })
                {
                    pending.push(&n.slice);
                }
            }
            Expr::Tuple(n) => {
                scan.tick(n.elts.len())?;
                pending.extend(&n.elts);
            }
            Expr::List(n) => {
                scan.tick(n.elts.len())?;
                pending.extend(&n.elts);
            }
            Expr::BinOp(n)
                if n.op == Operator::BitOr
                    && (matches!(&*n.left, Expr::NoneLiteral(_))
                        || matches!(&*n.right, Expr::NoneLiteral(_))) =>
            {
                pending.extend([&*n.left, &*n.right]);
            }
            _ => {}
        }
    }
    Ok(protected)
}

pub(super) fn sites(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
    selected: &Refs,
) -> Result<Vec<(i64, i64, i64)>> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    for node in nodes {
        scan.tick(1)?;
        let key = key(node);
        if selected.contains(&key) && seen.insert(key) {
            let at = match node {
                Node::Expr(n) => env.module.location(*n),
                Node::Arg(n) => env.module.location(*n),
                Node::Keyword(n) => env.module.location(*n),
                _ => {
                    out.push((1, 1, 0));
                    continue;
                }
            };
            out.push((at.line, at.end_line, at.column));
        }
    }
    out.sort_unstable();
    Ok(out)
}
