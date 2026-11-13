// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Directed annotation containment and owner namespace propagation.

use super::super::super::environment::Env;
use super::super::super::scan::{name, Result, Scan};
use super::super::super::{closure, names, namespace, scopes, statements};
use super::{provider, type_refs};
use crate::pyast::Node;
use ruff_python_ast::{Expr, ExprContext, Stmt};
use std::collections::{BTreeSet, HashSet};

fn lambda_owners<'a>(
    scan: &mut Scan,
    node: &Node<'a>,
    module_assignment: bool,
) -> Result<Vec<(String, Node<'a>)>> {
    let (targets, value) = statements::assignment(node);
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let mut lambda = false;
    for child in scan.walk(Node::Expr(value))? {
        scan.tick(1)?;
        lambda |= matches!(child, Node::Expr(Expr::Lambda(_)));
    }
    if !lambda {
        return Ok(Vec::new());
    }
    let mut owners = Vec::new();
    names::target_names(scan, targets, |n| {
        if n.ctx == ExprContext::Store || module_assignment {
            owners.push((n.id.to_string(), Node::Expr(value)));
        }
    })?;
    Ok(owners)
}

fn loads(scan: &mut Scan, expr: &Expr) -> Result<Vec<String>> {
    let mut names = Vec::new();
    for target in scan.walk(Node::Expr(expr))? {
        scan.tick(1)?;
        if let Node::Expr(Expr::Name(n)) = target {
            if n.ctx == ExprContext::Load {
                names.push(n.id.to_string());
            }
        }
    }
    Ok(names)
}

pub(super) fn owners<'a>(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'a>],
) -> Result<Vec<(String, Node<'a>)>> {
    let mut owners = Vec::new();
    let mut lambdas = Vec::new();
    let mut aliases = Vec::new();
    let scope = scopes::module_scope(scan, &env.module.tree.body)?;
    let mut module_assignments = HashSet::new();
    for node in scope {
        scan.tick(1)?;
        if let Node::Stmt(n) = node {
            module_assignments.insert(std::ptr::from_ref(n));
        }
    }
    for node in nodes {
        scan.tick(1)?;
        if let Some(name) = name(node) {
            owners.push((name.to_owned(), node.clone()));
        }
        let rows = lambda_owners(
            scan,
            node,
            matches!(node, Node::Stmt(n) if module_assignments.contains(&std::ptr::from_ref(*n))),
        )?;
        scan.tick(rows.len())?;
        lambdas.extend(rows);
        if let Node::Stmt(Stmt::TypeAlias(n)) = node {
            if let Expr::Name(name) = &*n.name {
                aliases.push((name.id.to_string(), node.clone()));
            }
        }
    }
    scan.tick(lambdas.len().saturating_add(aliases.len()))?;
    owners.extend(lambdas);
    owners.extend(aliases);
    Ok(owners)
}

pub(super) fn pairs(
    scan: &mut Scan,
    owners: &[(String, Node<'_>)],
    nodes: &[Node<'_>],
) -> Result<BTreeSet<(String, String)>> {
    let mut contained = BTreeSet::new();
    for (name, owner) in owners {
        scan.tick(1)?;
        let children = scan.walk(owner.clone())?;
        let mut expressions = type_refs::annotations(scan, &children)?;
        if let Node::Stmt(Stmt::ClassDef(n)) = owner {
            for base in n.bases() {
                scan.tick(1)?;
                expressions.push(base);
            }
        }
        for expr in expressions {
            scan.tick(1)?;
            for target in loads(scan, expr)? {
                scan.tick(1)?;
                contained.insert((name.clone(), target));
            }
        }
    }
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(Stmt::ClassDef(n)) = node else {
            continue;
        };
        for base in n.bases() {
            scan.tick(1)?;
            let base = match base {
                Expr::Subscript(n) => &*n.value,
                n => n,
            };
            for target in loads(scan, base)? {
                scan.tick(1)?;
                contained.insert((target, n.name.to_string()));
            }
        }
    }
    Ok(contained)
}

pub(super) fn namespace_owners(
    scan: &mut Scan,
    env: &Env<'_>,
    owners: &[(String, Node<'_>)],
    owner: bool,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
) -> Result<BTreeSet<String>> {
    let mut out = BTreeSet::new();
    for (name, node) in owners {
        scan.tick(1)?;
        let uncertain = match node {
            Node::Stmt(stmt @ Stmt::ClassDef(_)) if owner => {
                !provider::creation(scan, env, stmt, false, unsafe_names, escaped)?
            }
            _ => false,
        };
        if uncertain {
            out.insert(name.clone());
            continue;
        }
        for child in scan.walk(node.clone())? {
            scan.tick(1)?;
            if matches!(
                child,
                Node::Stmt(Stmt::FunctionDef(_)) | Node::Expr(Expr::Lambda(_))
            ) {
                out.insert(name.clone());
                break;
            }
        }
    }
    Ok(out)
}

pub(super) fn close(
    scan: &mut Scan,
    nodes: &[Node<'_>],
    roots: &HashSet<String>,
    contained: &BTreeSet<(String, String)>,
    locals: &HashSet<*const Expr>,
    owners: &BTreeSet<String>,
    bindings: &[String],
) -> Result<BTreeSet<String>> {
    scan.tick(
        roots
            .len()
            .saturating_add(contained.len())
            .saturating_add(owners.len()),
    )?;
    let roots: Vec<_> = roots.iter().map(String::as_str).collect();
    let contained: Vec<_> = contained
        .iter()
        .map(|(a, b)| (a.as_str(), b.as_str()))
        .collect();
    let owners: Vec<_> = owners.iter().map(String::as_str).collect();
    let closed = closure::closure(
        scan,
        nodes,
        &closure::Inputs {
            roots: &roots,
            members: true,
            contained: &contained,
            local_references: locals,
            namespace_owners: &owners,
            namespace_bindings: bindings,
        },
    )?;
    scan.tick(closed.len())?;
    Ok(closed.into_iter().collect())
}

pub(super) fn unproven(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
    roots: &HashSet<String>,
    contained: &BTreeSet<(String, String)>,
    locals: &HashSet<*const Expr>,
    owners: &BTreeSet<String>,
) -> Result<BTreeSet<String>> {
    for node in nodes {
        scan.tick(1)?;
        if namespace::exposes(scan, node, false, true, true)? {
            scan.tick(env.bound.len())?;
            return Ok(env.bound.iter().cloned().collect());
        }
    }
    let scope = scopes::module_scope(scan, &env.module.tree.body)?;
    for node in &scope {
        scan.tick(1)?;
        if namespace::exposes(scan, node, true, false, true)? {
            scan.tick(env.bound.len())?;
            return Ok(env.bound.iter().cloned().collect());
        }
    }
    let bindings = names::bound(scan, &scope)?;
    let mut changed = close(scan, nodes, roots, contained, locals, owners, &bindings)?;
    super::super::super::environment::propagate_origins(scan, nodes, &mut changed)?;
    Ok(changed)
}
