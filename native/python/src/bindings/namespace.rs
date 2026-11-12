// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Namespace checks on the CPython tree, including the member surface and import switch.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{CmpOp, Expr, ExprContext, Stmt};

use super::scan::{Result, Scan};
use crate::module::namespace_tables::{CONTAINERS, GLOBAL, GLOBALS, LOCAL, OWN, TYPE_READERS};
use crate::pyast::Node;

pub(super) struct Env<'a, 'n> {
    pub blocked: HashSet<&'n str>,
    pub opaque: bool,
    pub parents: &'n HashMap<*const Expr, Node<'a>>,
}

pub(super) fn flags(scan: &mut Scan, node: &Node<'_>) -> Result<Vec<bool>> {
    let mut row = Vec::new();
    for (local, member, imports) in [
        (false, false, false),
        (false, false, true),
        (false, true, false),
        (false, true, true),
        (true, false, false),
        (true, false, true),
        (true, true, false),
        (true, true, true),
    ] {
        scan.tick(1)?;
        row.push(exposes(scan, node, local, member, imports)?);
    }
    Ok(row)
}

pub(super) fn dotted(scan: &mut Scan, expr: &Expr) -> Result<Option<String>> {
    let mut parts = Vec::new();
    let mut current = expr;
    while let Expr::Attribute(n) = current {
        scan.tick(1)?;
        parts.push(n.attr.as_str());
        current = &n.value;
    }
    if let Expr::Name(n) = current {
        parts.push(n.id.as_str());
        scan.tick(parts.len())?;
        parts.reverse();
        Ok(Some(parts.join(".")))
    } else {
        Ok(None)
    }
}

fn target<'a>(node: &Node<'a>, load_only: bool) -> Option<(&'a Expr, bool)> {
    match node {
        Node::Expr(Expr::Call(n)) => Some((&n.func, n.arguments.args.is_empty())),
        Node::Stmt(Stmt::Assign(n)) if reference(&n.value, false) => Some((&n.value, true)),
        Node::Stmt(Stmt::AnnAssign(n)) => n
            .value
            .as_deref()
            .filter(|n| reference(n, false))
            .map(|n| (n, true)),
        Node::Expr(n) if reference(n, load_only) => Some((n, true)),
        _ => None,
    }
}

fn reference(expr: &Expr, load: bool) -> bool {
    match expr {
        Expr::Name(n) => !load || n.ctx == ExprContext::Load,
        Expr::Attribute(n) => !load || n.ctx == ExprContext::Load,
        _ => false,
    }
}

pub(super) fn exposes(
    scan: &mut Scan,
    node: &Node<'_>,
    local: bool,
    member: bool,
    imports: bool,
) -> Result<bool> {
    if member
        && matches!(node,
        Node::Expr(Expr::Name(n)) if n.ctx == ExprContext::Load && n.id.as_str() == "__annotations__")
    {
        return Ok(true);
    }
    if member
        && matches!(node,
        Node::Expr(Expr::Attribute(n)) if n.ctx == ExprContext::Load && matches!(n.attr.as_str(), "f_globals" | "f_locals" | "f_builtins"))
    {
        return Ok(true);
    }
    let Some((expr, access)) = target(node, true) else {
        return Ok(false);
    };
    let Some(name) = dotted(scan, expr)? else {
        return Ok(false);
    };
    if member && TYPE_READERS.contains(&name.as_str()) {
        return Ok(true);
    }
    if matches!(name.as_str(), "__import__" | "builtins.__import__") {
        return Ok(imports);
    }
    Ok(GLOBAL.contains(&name.as_str()) || local && access && LOCAL.contains(&name.as_str()))
}

pub(super) fn own_only(scan: &mut Scan, node: &Node<'_>) -> Result<bool> {
    if matches!(node, Node::Expr(Expr::Name(n)) if n.id.as_str() == "__annotations__") {
        return Ok(true);
    }
    let Some((expr, _)) = target(node, false) else {
        return Ok(false);
    };
    Ok(dotted(scan, expr)?.is_some_and(|name| OWN.contains(&name.as_str())))
}

pub(super) fn read_names(scan: &mut Scan, node: &Node<'_>, env: &Env<'_, '_>) -> Result<bool> {
    let Node::Expr(Expr::Call(call)) = node else {
        return Ok(false);
    };
    if !call.arguments.args.is_empty()
        || !dotted(scan, &call.func)?.is_some_and(|n| GLOBALS.contains(&n.as_str()))
    {
        return Ok(false);
    }
    consumed(scan, node, env)
}

fn consumed(scan: &mut Scan, node: &Node<'_>, env: &Env<'_, '_>) -> Result<bool> {
    let Some(mut expr) = node.expr() else {
        return Ok(false);
    };
    while let Some(parent) = env.parents.get(&std::ptr::from_ref(expr)) {
        scan.tick(1)?;
        match parent {
            Node::Expr(Expr::Attribute(n)) if n.attr.as_str() == "keys" => {
                let attribute = parent.expr().ok_or("parent expression unseen")?;
                let Some(call_node @ Node::Expr(Expr::Call(call))) =
                    env.parents.get(&std::ptr::from_ref(attribute))
                else {
                    return Ok(false);
                };
                if !std::ptr::eq(&*call.func, attribute) {
                    return Ok(false);
                }
                expr = call_node.expr().ok_or("call expression unseen")?;
            }
            Node::Expr(Expr::Call(n)) => {
                let sole = n.arguments.args.len() == 1
                    && n.arguments
                        .args
                        .first()
                        .is_some_and(|n| std::ptr::eq(n, expr));
                return Ok(sole && bare_builtin(&n.func, env));
            }
            Node::Expr(Expr::Compare(n)) => {
                return Ok(n
                    .comparators()
                    .last()
                    .is_some_and(|n| std::ptr::eq(n, expr))
                    && matches!(n.ops.last(), Some(CmpOp::In | CmpOp::NotIn)))
            }
            Node::Stmt(Stmt::For(n)) => return Ok(std::ptr::eq(&*n.iter, expr)),
            Node::Comprehension(n) => return Ok(std::ptr::eq(&n.iter, expr)),
            _ => return Ok(false),
        }
    }
    Ok(false)
}

fn bare_builtin(expr: &Expr, env: &Env<'_, '_>) -> bool {
    let Expr::Name(n) = expr else {
        return false;
    };
    CONTAINERS.contains(&n.id.as_str()) && !env.opaque && !env.blocked.contains(n.id.as_str())
}

pub(super) fn rebind(
    scan: &mut Scan,
    nodes: &[Node<'_>],
    scope: &[Node<'_>],
    env: &Env<'_, '_>,
    imports: bool,
) -> Result<bool> {
    for (nodes, local) in [(nodes, false), (scope, true)] {
        for node in nodes {
            scan.tick(1)?;
            if !exposes(scan, node, local, false, imports)? {
                continue;
            }
            let read = match node
                .expr()
                .and_then(|e| env.parents.get(&std::ptr::from_ref(e)))
            {
                Some(parent @ Node::Expr(Expr::Call(call)))
                    if node.expr().is_some_and(|e| std::ptr::eq(&*call.func, e)) =>
                {
                    parent
                }
                _ => node,
            };
            if !read_names(scan, read, env)? {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_namespace_consumer_step_costs_one_unit() {
        let tree = crate::test_tree("list(globals().keys().keys())\n", 11).expect("fixture");
        let minor = crate::test_minor(11);
        let mut parents = HashMap::new();
        let mut target = None;
        let root = Node::Stmt(tree.body.first().expect("statement"));
        for node in crate::pyast::walk(root, minor) {
            parents.extend(
                crate::pyast::child_nodes(&node, minor)
                    .into_iter()
                    .filter_map(|child| {
                        child
                            .expr()
                            .map(|expr| (std::ptr::from_ref(expr), node.clone()))
                    }),
            );
            if matches!(&node, Node::Expr(Expr::Call(call)) if matches!(&*call.func, Expr::Name(n) if n.id.as_str() == "globals"))
            {
                target = Some(node);
            }
        }
        let env = Env {
            blocked: HashSet::new(),
            opaque: false,
            parents: &parents,
        };
        let mut scan = Scan::new(minor);
        let before = scan.work.used();
        assert!(consumed(&mut scan, &target.expect("globals call"), &env).expect("in scope"));
        assert_eq!(scan.work.used() - before, 3);
    }
}
