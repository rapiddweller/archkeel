// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! References which do not expose the defining owner namespace.

use std::collections::HashSet;
use ruff_python_ast::{Expr, ExprContext, Stmt};
use super::super::super::environment::Env;
use super::super::super::scan::{Result, Scan};
use super::super::super::{scopes, values};
use super::{provider, type_refs};
use super::type_refs::{key, Refs};
use crate::pyast::Node;

pub(super) fn protected(scan: &mut Scan, env: &Env<'_>, unsafe_names: &HashSet<String>, escaped: &HashSet<String>) -> Result<Refs> {
    let mut plain = HashSet::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        if let Stmt::ClassDef(n) = stmt {
            if n.bases().len() == 0 && n.decorator_list.is_empty() && n.arguments.as_ref().is_none_or(|a| a.keywords.is_empty()) && env.unique.contains(n.name.as_str()) && provider::creation(scan, env, stmt, true, &HashSet::new(), escaped)? { plain.insert(n.name.as_str()); }
        }
    }
    let mut protected = Refs::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::ClassDef(n) = stmt else { continue };
        let parameters = super::super::types::generic(scan, env, stmt, n)?;
        for base_expr in n.bases() {
            scan.tick(1)?;
            let Expr::Subscript(base) = base_expr else { continue };
            let args = match &*base.slice { Expr::Tuple(n) => n.elts.as_slice(), n => std::slice::from_ref(n) };
            let mut admitted = true;
            for arg in args {
                scan.tick(1)?;
                admitted &= matches!(arg, Expr::Name(n) if plain.contains(n.id.as_str()) || parameters.contains(&n.id.to_string()));
            }
            if admitted && provider::generic(scan, env, base_expr, stmt, unsafe_names, escaped, &mut HashSet::new(), 0)? {
                for arg in args { scan.tick(1)?; protected.insert(key(&Node::Expr(arg))); }
            }
        }
    }
    for node in scopes::module_scope(scan, &env.module.tree.body)? {
        scan.tick(1)?;
        match node {
            Node::Expr(Expr::Attribute(n)) if n.ctx != ExprContext::Load && !n.attr.starts_with("__") => {
                if matches!(&*n.value, Expr::Name(n) if plain.contains(n.id.as_str())) { protected.insert(key(&Node::Expr(&n.value))); }
            }
            Node::Stmt(Stmt::FunctionDef(n)) => {
                for p in n.parameters.posonlyargs.iter().chain(&n.parameters.args).chain(&n.parameters.kwonlyargs) {
                    scan.tick(1)?;
                    if let Some(value @ Expr::Name(name)) = p.default.as_deref() {
                        if plain.contains(name.id.as_str()) { protected.insert(key(&Node::Expr(value))); }
                    }
                }
            }
            Node::Expr(Expr::Call(n)) if type_refs::bare(env, &n.func, &["setattr"]) && n.arguments.args.len() == 3 && n.arguments.keywords.is_empty() => {
                if let [owner @ Expr::Name(name), Expr::StringLiteral(attr), value] = n.arguments.args.as_ref() {
                    if plain.contains(name.id.as_str()) && !attr.value.to_str().starts_with("__") && (matches!(value, Expr::Name(_)) || values::inert(scan, value, 0)?) { protected.insert(key(&Node::Expr(owner))); }
                }
            }
            _ => {}
        }
    }
    Ok(protected)
}
