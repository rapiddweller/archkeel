// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Escape sites retain their AST identity until the closure consumes them.

use super::super::super::environment::Env;
use super::super::super::scan::{Result, Scan};
use super::super::{classes, methods, types};
use super::type_refs::{key, Refs};
use super::{owner_refs, provider, type_refs};
use crate::pyast::Node;
use ruff_python_ast::{Expr, ExprContext, Stmt};
use std::collections::HashSet;

fn merge(scan: &mut Scan, protected: &mut Refs, other: Refs) -> Result<()> {
    scan.tick(other.len())?;
    protected.extend(other);
    Ok(())
}

fn decorators(
    scan: &mut Scan,
    protected: &mut Refs,
    n: &ruff_python_ast::StmtFunctionDef,
) -> Result<()> {
    for decorator in &n.decorator_list {
        scan.tick(1)?;
        for node in scan.walk(Node::Expr(&decorator.expression))? {
            scan.tick(1)?;
            protected.insert(key(&node));
        }
    }
    Ok(())
}

fn properties(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt) -> Result<Refs> {
    let Stmt::ClassDef(n) = stmt else {
        return Ok(Refs::new());
    };
    let properties = methods::properties(scan, env, stmt)?;
    let mut protected = Refs::new();
    for stmt in &n.body {
        scan.tick(1)?;
        let Stmt::FunctionDef(n) = stmt else { continue };
        if properties.contains_key(&std::ptr::from_ref(n)) {
            decorators(scan, &mut protected, n)?;
        }
    }
    let mut bases = Vec::new();
    for base in n.bases() {
        scan.tick(1)?;
        bases.push(base);
    }
    let references = type_refs::references(scan, env, &bases)?;
    merge(scan, &mut protected, references)?;
    Ok(protected)
}

fn callable_head(scan: &mut Scan, expr: &Expr) -> Result<bool> {
    if matches!(expr, Expr::Name(_)) {
        return Ok(true);
    }
    if !matches!(expr, Expr::Attribute(_)) || type_refs::root(scan, expr)?.is_none() {
        return Ok(false);
    }
    let mut expr = expr;
    while let Expr::Attribute(n) = expr {
        scan.tick(1)?;
        if n.attr.starts_with("__") {
            return Ok(false);
        }
        expr = &n.value;
    }
    Ok(true)
}

fn owner_expressions<'a>(scan: &mut Scan, nodes: &[Node<'a>]) -> Result<Vec<&'a Expr>> {
    let mut expressions = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let expr = match node {
            Node::Expr(Expr::Call(n)) if callable_head(scan, &n.func)? => Some(&*n.func),
            Node::Stmt(Stmt::If(n)) => Some(&*n.test),
            Node::Elif(clauses) => clauses.first().and_then(|n| n.test.as_ref()),
            Node::Stmt(Stmt::While(n)) => Some(&*n.test),
            Node::Expr(Expr::If(n)) => Some(&*n.test),
            _ => None,
        };
        expressions.extend(expr);
        let decorators = match node {
            Node::Stmt(Stmt::ClassDef(n)) => n.decorator_list.as_slice(),
            Node::Stmt(Stmt::FunctionDef(n)) => n.decorator_list.as_slice(),
            _ => &[],
        };
        for d in decorators {
            scan.tick(1)?;
            expressions.push(&d.expression);
        }
    }
    Ok(expressions)
}

pub(super) fn protected(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
    owner: bool,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
) -> Result<Refs> {
    let annotations = type_refs::annotations(scan, nodes)?;
    let mut protected = type_refs::references(scan, env, &annotations)?;
    for node in nodes {
        scan.tick(1)?;
        if let Node::Stmt(stmt @ Stmt::ClassDef(_)) = node {
            let references = properties(scan, env, stmt)?;
            merge(scan, &mut protected, references)?;
        }
    }
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let (targets, value) = super::super::super::statements::assignment(&Node::Stmt(stmt));
        let Some(value @ Expr::Name(_)) = value else {
            continue;
        };
        scan.tick(targets.len())?;
        if targets.iter().all(|t| matches!(t, Expr::Name(_))) {
            protected.insert(key(&Node::Expr(value)));
        }
    }
    if owner {
        let references = owner_refs::protected(scan, env, unsafe_names, escaped)?;
        merge(scan, &mut protected, references)?;
        let expressions = owner_expressions(scan, nodes)?;
        let references = type_refs::references(scan, env, &expressions)?;
        merge(scan, &mut protected, references)?;
    }
    Ok(protected)
}

pub(super) fn locals(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
) -> Result<HashSet<*const Expr>> {
    let sites = types::setters(scan, env)?;
    let mut out = HashSet::new();
    for node in nodes {
        scan.tick(1)?;
        if let Some(n) = node.expr() {
            let at = env.module.location(n);
            if sites.contains(&(at.line, at.end_line, at.column)) {
                out.insert(std::ptr::from_ref(n));
            }
        }
    }
    Ok(out)
}

pub(super) fn references<'a>(
    scan: &mut Scan,
    nodes: &[Node<'a>],
    owner: bool,
    protected: &Refs,
    locals: &HashSet<*const Expr>,
) -> Result<Vec<&'a Expr>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let mut pending = Vec::new();
        match node {
            Node::Expr(Expr::Attribute(n)) if n.ctx != ExprContext::Load => {
                pending.push(Node::Expr(&n.value))
            }
            Node::Expr(Expr::Call(n)) => {
                scan.tick(
                    n.arguments
                        .args
                        .len()
                        .saturating_add(n.arguments.keywords.len()),
                )?;
                pending.extend(n.arguments.args.iter().map(Node::Expr));
                pending.extend(n.arguments.keywords.iter().map(|k| Node::Expr(&k.value)));
                if !owner {
                    pending.push(Node::Expr(&n.func));
                }
            }
            Node::Expr(Expr::Name(n))
                if n.ctx == ExprContext::Load && !protected.contains(&key(node)) =>
            {
                pending.push(node.clone())
            }
            _ => continue,
        }
        while let Some(target) = pending.pop() {
            scan.tick(1)?;
            match target {
                Node::Expr(n @ Expr::Name(_))
                    if !locals.contains(&std::ptr::from_ref(n))
                        && (!owner || !protected.contains(&key(&target))) =>
                {
                    out.push(n);
                }
                Node::Expr(Expr::Name(_)) => {}
                Node::Expr(Expr::Attribute(n)) => pending.push(Node::Expr(&n.value)),
                Node::Expr(Expr::Call(_)) => {}
                _ => pending.extend(scan.children(&target)?),
            }
        }
    }
    Ok(out)
}

pub(super) fn roots(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
    mode: (bool, bool),
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
    locals: &HashSet<*const Expr>,
) -> Result<HashSet<String>> {
    let (owner, creation) = mode;
    let protected = protected(scan, env, nodes, owner, unsafe_names, escaped)?;
    let mut roots = HashSet::new();
    let mut properties = HashSet::new();
    if creation {
        for node in nodes {
            scan.tick(1)?;
            if let Node::Stmt(stmt @ Stmt::ClassDef(_)) = node {
                let methods = methods::properties(scan, env, stmt)?;
                scan.tick(methods.len())?;
                properties.extend(methods.into_keys());
            }
        }
    }
    for node in nodes {
        scan.tick(1)?;
        match node {
            Node::Stmt(stmt @ Stmt::ClassDef(n)) => {
                if creation && !provider::creation(scan, env, stmt, owner, unsafe_names, escaped)?
                    || owner && classes::receives(scan, env, stmt)?
                {
                    roots.insert(n.name.to_string());
                }
            }
            Node::Stmt(stmt @ Stmt::FunctionDef(n))
                if creation
                    && !properties.contains(&std::ptr::from_ref(n))
                    && !methods::signature(scan, env, stmt, None)?.1 =>
            {
                roots.insert(n.name.to_string());
            }
            _ => {}
        }
    }
    for expr in references(scan, nodes, owner, &protected, locals)? {
        scan.tick(1)?;
        if let Expr::Name(n) = expr {
            roots.insert(n.id.to_string());
        }
    }
    Ok(roots)
}
