// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Local inert constructors and class-value expression admission, before provider candidates.

use super::super::super::environment::Env;
use super::super::super::scan::{Result, Scan};
use super::super::super::{names, scopes, statements, values};
use super::super::classes;
use super::type_refs;
use crate::pyast::Node;
use ruff_python_ast::{Expr, ExprContext, Stmt, StmtFunctionDef};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashSet};

const BUILTIN: &[&str] = &["str", "int", "float", "bool", "bytes", "object"];

fn shadowed(
    scan: &mut Scan,
    env: &Env<'_>,
    body: &[Stmt],
    stmt: &Stmt,
    value: &Expr,
) -> Result<bool> {
    for node in scan.walk(Node::Expr(value))? {
        scan.tick(1)?;
        let Node::Expr(Expr::Name(name)) = node else {
            continue;
        };
        if name.ctx == ExprContext::Load
            && env.may_exist(scan, body, Some(stmt), name.id.as_str())?
        {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(super) fn class_values(scan: &mut Scan, env: &Env<'_>) -> Result<Vec<(i64, i64, i64)>> {
    let mut out = Vec::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::ClassDef(n) = stmt else { continue };
        for stmt in &n.body {
            scan.tick(1)?;
            let (_, value) = statements::assignment(&Node::Stmt(stmt));
            let Some(value) = value else { continue };
            if values::inert(scan, value, 0)? {
                continue;
            }
            if !shadowed(scan, env, &n.body, stmt, value)? {
                let at = env.module.location(value);
                out.push((at.line, at.end_line, at.column));
            }
        }
    }
    out.sort_unstable();
    Ok(out)
}

fn inert_classes<'a>(scan: &mut Scan, env: &'a Env<'_>) -> Result<BTreeMap<&'a str, i64>> {
    let mut classes = BTreeMap::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::ClassDef(n) = stmt else { continue };
        if !env.stable.contains(n.name.as_str())
            || !env.unique.contains(n.name.as_str())
            || !n.decorator_list.is_empty()
            || n.arguments
                .as_ref()
                .is_some_and(|a| !a.args.is_empty() || !a.keywords.is_empty())
        {
            continue;
        }
        let mut inert = true;
        for stmt in &n.body {
            scan.tick(1)?;
            inert &= match stmt {
                Stmt::Pass(_) => true,
                Stmt::Expr(n) => matches!(&*n.value, Expr::StringLiteral(_)),
                Stmt::AnnAssign(n) => {
                    matches!(&*n.target, Expr::Name(_))
                        && n.value.is_none()
                        && (values::inert(scan, &n.annotation, 0)?
                            || type_refs::bare(env, &n.annotation, BUILTIN))
                }
                _ => false,
            };
            if !inert {
                break;
            }
        }
        if inert {
            classes.insert(
                n.name.as_str(),
                env.module
                    .location(&crate::module::definition::Def::Class(n).range(env.module.text()))
                    .line,
            );
        }
    }
    Ok(classes)
}

fn header(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    n: &StmtFunctionDef,
    classes: &BTreeMap<&str, i64>,
) -> Result<Option<BTreeSet<String>>> {
    let line = super::super::methods::line(env, n);
    let mut inert = true;
    for arg in n
        .parameters
        .posonlyargs
        .iter()
        .chain(&n.parameters.args)
        .chain(&n.parameters.kwonlyargs)
    {
        scan.tick(1)?;
        if let Some(default) = arg.default.as_deref() {
            inert &= values::inert(scan, default, 0)?;
        }
    }
    if !inert {
        return Ok(None);
    }
    let mut annotations = vec![Node::Stmt(stmt)];
    for arg in n.parameters.iter() {
        scan.tick(1)?;
        annotations.push(Node::Arg(arg.as_parameter()));
    }
    let annotations = type_refs::annotations(scan, &annotations)?;
    let mut header_names = BTreeSet::new();
    for expr in &annotations {
        scan.tick(1)?;
        let Expr::Name(n) = expr else { continue };
        if classes.get(n.id.as_str()).is_some_and(|l| *l < line) {
            header_names.insert(n.id.to_string());
        }
    }
    for expr in annotations {
        scan.tick(1)?;
        if !classes::deferred(scan, env, expr)?
            && !values::inert(scan, expr, 0)?
            && !type_refs::bare(env, expr, BUILTIN)
            && !matches!(expr, Expr::Name(n) if header_names.contains(n.id.as_str()))
        {
            inert = false;
            break;
        }
    }
    if !inert {
        return Ok(None);
    }
    Ok(Some(header_names))
}

pub(super) fn candidates(scan: &mut Scan, env: &Env<'_>) -> Result<Vec<Value>> {
    let classes = inert_classes(scan, env)?;
    let mut out = Vec::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::FunctionDef(n) = stmt else { continue };
        if !env.stable.contains(n.name.as_str())
            || !env.unique.contains(n.name.as_str())
            || !n.decorator_list.is_empty()
        {
            continue;
        }
        let Some(header_names) = header(scan, env, stmt, n, &classes)? else {
            continue;
        };
        let line = super::super::methods::line(env, n);
        let own = scopes::own(scan, &n.body)?;
        let bound = names::bound(scan, &own)?;
        scan.tick(bound.len())?;
        let mut shadowed: HashSet<_> = bound.into_iter().collect();
        for arg in n.parameters.iter() {
            scan.tick(1)?;
            shadowed.insert(arg.name().to_string());
        }
        for stmt in &n.body {
            scan.tick(1)?;
            let Stmt::Return(returned) = stmt else {
                continue;
            };
            let Some(Expr::Call(call)) = returned.value.as_deref() else {
                continue;
            };
            let Expr::Name(owner) = &*call.func else {
                continue;
            };
            if !call.arguments.args.is_empty()
                || !call.arguments.keywords.is_empty()
                || !classes.get(owner.id.as_str()).is_some_and(|l| *l < line)
                || shadowed.contains(owner.id.as_str())
            {
                continue;
            }
            scan.tick(header_names.len())?;
            let mut deps: BTreeSet<_> = header_names
                .iter()
                .map(|name| (env.module.name.clone(), name.clone()))
                .collect();
            deps.insert((env.module.name.clone(), owner.id.to_string()));
            deps.insert((env.module.name.clone(), n.name.to_string()));
            let at = env.module.location(call);
            scan.keep(&mut out, json!([[at.line, at.end_line, at.column], deps]))?;
        }
    }
    Ok(out)
}
