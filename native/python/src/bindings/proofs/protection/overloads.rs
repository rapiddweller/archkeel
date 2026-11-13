// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Only complete contiguous native overload groups retain provider identity.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};
use super::super::super::environment::{resolve, Env};
use super::super::super::scan::{Result, Scan};
use super::super::super::{names, namespace, scopes};
use super::super::methods;
use super::type_refs;
use crate::pyast::Node;

fn group(scan: &mut Scan, env: &Env<'_>, group: &[(usize, &Stmt, &StmtFunctionDef)], generic: &HashSet<String>) -> Result<bool> {
    let Some((_, _, implementation)) = group.last() else { return Ok(false) };
    if !implementation.decorator_list.is_empty() { return Ok(false); }
    for (_, stmt, function) in group {
        scan.tick(1)?;
        if function.is_async != implementation.is_async { return Ok(false); }
        let children = scan.walk(Node::Stmt(stmt))?;
        for annotation in type_refs::annotations(scan, &children)? {
            scan.tick(1)?;
            for node in scan.walk(Node::Expr(annotation))? { scan.tick(1)?; if matches!(node, Node::Expr(Expr::Name(n)) if generic.contains(n.id.as_str())) { return Ok(false); } }
        }
    }
    for (_, stmt, n) in group.iter().take(group.len().saturating_sub(1)) {
        scan.tick(1)?;
        let Some(decorator) = n.decorator_list.first() else { return Ok(false) };
        if n.decorator_list.len() != 1 || matches!(decorator.expression, Expr::Call(_)) || !methods::proven(scan, env, &decorator.expression, stmt, None, &["typing.overload", "typing_extensions.overload"])? { return Ok(false); }
        for stmt in &n.body {
            scan.tick(1)?;
            if !matches!(stmt, Stmt::Pass(_)) && !matches!(stmt, Stmt::Expr(n) if matches!(&*n.value, Expr::EllipsisLiteral(_))) { return Ok(false); }
        }
    }
    Ok(true)
}

pub(super) fn collect(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>], escaped: &HashSet<String>) -> Result<BTreeSet<String>> {
    let mut groups: BTreeMap<&str, Vec<_>> = BTreeMap::new();
    for (index, stmt) in env.module.tree.body.iter().enumerate() {
        scan.tick(1)?;
        if let Stmt::FunctionDef(n) = stmt { groups.entry(n.name.as_str()).or_default().push((index, stmt, n)); }
    }
    scan.tick(groups.len())?;
    if env.opaque || !groups.values().any(|sites| sites.len() >= 3) { return Ok(BTreeSet::new()); }
    let scope = scopes::module_scope(scan, &env.module.tree.body)?;
    let mut globals = HashSet::new();
    let mut parents = HashMap::new();
    for node in nodes {
        scan.tick(1)?;
        if let Node::Stmt(Stmt::Global(n)) = node { for name in &n.names { scan.tick(1)?; globals.insert(name.as_str()); } }
        for child in scan.children(node)? { scan.tick(1)?; if let Node::Expr(n) = child { parents.insert(std::ptr::from_ref(n), node.clone()); } }
    }
    scan.tick(env.bound.len())?;
    let namespace = namespace::Env { blocked: env.bound.iter().map(String::as_str).collect(), opaque: env.opaque, parents: &parents };
    if namespace::rebind(scan, nodes, &scope, &namespace, true)? { return Ok(BTreeSet::new()); }
    let bindings = names::bound(scan, &scope)?;
    let counts = super::super::super::scan::counts(scan, bindings)?;
    let mut generic = HashSet::new();
    for node in &scope {
        scan.tick(1)?;
        let (targets, value) = super::super::super::statements::assignment(node);
        let Some(Expr::Call(call)) = value else { continue };
        if !matches!(node, Node::Stmt(Stmt::Assign(_) | Stmt::AnnAssign(_))) { continue; }
        if matches!(resolve(scan, env.module, &call.func)?.as_str(), "typing.TypeVar" | "typing_extensions.TypeVar" | "typing.ParamSpec" | "typing_extensions.ParamSpec" | "typing.TypeVarTuple" | "typing_extensions.TypeVarTuple") {
            generic.extend(names::stored_names(scan, targets)?);
        }
    }
    let mut proven = BTreeSet::new();
    for (name, sites) in groups {
        scan.tick(1)?;
        let (Some(first), Some(last)) = (sites.first(), sites.last()) else { continue };
        if sites.len() >= 3 && !globals.contains(name) && !escaped.contains(name) && counts.get(name) == Some(&sites.len()) && last.0 - first.0 + 1 == sites.len() && group(scan, env, &sites, &generic)? { proven.insert(name.to_owned()); }
    }
    Ok(proven)
}
