// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Escape sites retain their AST identity until the closure consumes them.

use std::collections::HashSet;
use ruff_python_ast::{Expr, ExprContext, Stmt};
use super::super::super::environment::Env;
use super::super::super::scan::{Result, Scan};
use super::super::{classes, methods, types};
use super::{owner_refs, provider, type_refs};
use super::type_refs::{key, Refs};
use crate::pyast::Node;

pub(super) fn protected(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>], owner: bool, unsafe_names: &HashSet<String>, escaped: &HashSet<String>) -> Result<Refs> {
    let annotations = type_refs::annotations(scan, nodes)?;
    let mut protected = type_refs::references(scan, env, &annotations)?;
    for node in nodes {
        scan.tick(1)?;
        if let Node::Stmt(stmt @ Stmt::ClassDef(n)) = node {
            let properties = methods::properties(scan, env, stmt)?;
            for stmt in &n.body {
                scan.tick(1)?;
                let Stmt::FunctionDef(n) = stmt else { continue };
                if !properties.contains_key(&std::ptr::from_ref(n)) { continue; }
                for decorator in &n.decorator_list {
                    scan.tick(1)?;
                    for node in scan.walk(Node::Expr(&decorator.expression))? { scan.tick(1)?; protected.insert(key(&node)); }
                }
            }
            let mut bases = Vec::new();
            for base in n.bases() { scan.tick(1)?; bases.push(base); }
            protected.extend(type_refs::references(scan, env, &bases)?);
        }
    }
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let (targets, value) = super::super::super::statements::assignment(&Node::Stmt(stmt));
        let Some(value @ Expr::Name(_)) = value else { continue };
        scan.tick(targets.len())?;
        if targets.iter().all(|t| matches!(t, Expr::Name(_))) { protected.insert(key(&Node::Expr(value))); }
    }
    if owner {
        protected.extend(owner_refs::protected(scan, env, unsafe_names, escaped)?);
        let mut expressions = Vec::new();
        for node in nodes {
            scan.tick(1)?;
            match node {
                Node::Expr(Expr::Call(n)) => {
                    let mut accepted = matches!(&*n.func, Expr::Name(_));
                    if matches!(&*n.func, Expr::Attribute(_)) && type_refs::root(scan, &n.func)?.is_some() {
                        accepted = true;
                        let mut expr = &*n.func;
                        while let Expr::Attribute(n) = expr { scan.tick(1)?; accepted &= !n.attr.starts_with("__"); expr = &n.value; }
                    }
                    if accepted { expressions.push(&*n.func); }
                }
                Node::Stmt(Stmt::ClassDef(n)) => { for d in &n.decorator_list { scan.tick(1)?; expressions.push(&d.expression); } }
                Node::Stmt(Stmt::FunctionDef(n)) => { for d in &n.decorator_list { scan.tick(1)?; expressions.push(&d.expression); } }
                Node::Stmt(Stmt::If(n)) => expressions.push(&n.test),
                Node::Elif(clauses) => { if let Some(n) = clauses.first() { expressions.extend(n.test.as_ref()); } }
                Node::Stmt(Stmt::While(n)) => expressions.push(&n.test),
                Node::Expr(Expr::If(n)) => expressions.push(&n.test),
                _ => {}
            }
        }
        protected.extend(type_refs::references(scan, env, &expressions)?);
    }
    Ok(protected)
}

pub(super) fn locals(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<HashSet<*const Expr>> {
    let sites = types::setters(scan, env)?;
    let mut out = HashSet::new();
    for node in nodes {
        scan.tick(1)?;
        if let Some(n) = node.expr() {
            let at = env.module.location(n);
            if sites.contains(&(at.line, at.end_line, at.column)) { out.insert(std::ptr::from_ref(n)); }
        }
    }
    Ok(out)
}

pub(super) fn references<'a>(scan: &mut Scan, nodes: &[Node<'a>], owner: bool, protected: &Refs, locals: &HashSet<*const Expr>) -> Result<Vec<&'a Expr>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let mut pending = Vec::new();
        match node {
            Node::Expr(Expr::Attribute(n)) if n.ctx != ExprContext::Load => pending.push(Node::Expr(&n.value)),
            Node::Expr(Expr::Call(n)) => {
                scan.tick(n.arguments.args.len().saturating_add(n.arguments.keywords.len()))?;
                pending.extend(n.arguments.args.iter().map(Node::Expr));
                pending.extend(n.arguments.keywords.iter().map(|k| Node::Expr(&k.value)));
                if !owner { pending.push(Node::Expr(&n.func)); }
            }
            Node::Expr(Expr::Name(n)) if n.ctx == ExprContext::Load && !protected.contains(&key(node)) => pending.push(node.clone()),
            _ => continue,
        }
        while let Some(target) = pending.pop() {
            scan.tick(1)?;
            match target {
                Node::Expr(n @ Expr::Name(_)) if !locals.contains(&std::ptr::from_ref(n)) => { if !owner || !protected.contains(&key(&target)) { out.push(n); } }
                Node::Expr(Expr::Name(_)) => {},
                Node::Expr(Expr::Attribute(n)) => pending.push(Node::Expr(&n.value)),
                Node::Expr(Expr::Call(_)) => {},
                _ => pending.extend(scan.children(&target)?),
            }
        }
    }
    Ok(out)
}

pub(super) fn roots(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>], owner: bool, creation: bool, unsafe_names: &HashSet<String>, escaped: &HashSet<String>, locals: &HashSet<*const Expr>) -> Result<HashSet<String>> {
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
                if creation && !provider::creation(scan, env, stmt, owner, unsafe_names, escaped)? || owner && classes::receives(scan, env, stmt)? { roots.insert(n.name.to_string()); }
            }
            Node::Stmt(stmt @ Stmt::FunctionDef(n)) if creation && !properties.contains(&std::ptr::from_ref(n)) => {
                if !methods::signature(scan, env, stmt, None)?.1 { roots.insert(n.name.to_string()); }
            }
            _ => {}
        }
    }
    for expr in references(scan, nodes, owner, &protected, locals)? {
        scan.tick(1)?;
        if let Expr::Name(n) = expr { roots.insert(n.id.to_string()); }
    }
    Ok(roots)
}
