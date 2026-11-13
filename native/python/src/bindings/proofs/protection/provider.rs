// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Native factory headers consume explicit provider escapes, never a spelling guess.

use super::super::super::environment::{resolve, Env};
use super::super::super::scan::{Result, Scan};
use super::super::super::{names, statements};
use super::super::{classes, methods, types};
use super::type_refs;
use crate::pyast::Node;
use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use std::collections::HashSet;

const TYPED: &[&str] = &["typing.TypedDict", "typing_extensions.TypedDict"];
const OPTIONS: &[&str] = &[
    "init",
    "repr",
    "eq",
    "order",
    "unsafe_hash",
    "frozen",
    "match_args",
    "kw_only",
    "slots",
    "weakref_slot",
];
const FRAMEWORKS: &[&str] = &[
    "object",
    "builtins.object",
    "abc.ABC",
    "enum.Enum",
    "enum.IntEnum",
    "enum.StrEnum",
    "pydantic.BaseModel",
    "typing.Generic",
    "typing.Protocol",
    "typing_extensions.Protocol",
];

pub(super) fn typed(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
) -> Result<bool> {
    let Stmt::ClassDef(n) = stmt else {
        return Ok(false);
    };
    if !methods::direct(env, stmt)
        || !env.unique.contains(n.name.as_str())
        || !env.stable.contains(n.name.as_str())
        || !n.decorator_list.is_empty()
    {
        return Ok(false);
    }
    let Some(args) = n.arguments.as_deref() else {
        return Ok(false);
    };
    if args.args.len() != 1 || args.keywords.len() > 1 {
        return Ok(false);
    }
    if let Some(kw) = args.keywords.first() {
        if kw.arg.as_ref().map(|n| n.as_str()) != Some("total")
            || !matches!(kw.value, Expr::BooleanLiteral(_))
        {
            return Ok(false);
        }
    }
    let Some(base) = args.args.first() else {
        return Ok(false);
    };
    let root = match base {
        Expr::Attribute(n) => &*n.value,
        n => n,
    };
    let Expr::Name(root) = root else {
        return Ok(false);
    };
    let origin = resolve(scan, env.module, base)?;
    Ok(env.unique.contains(root.id.as_str())
        && TYPED.contains(&origin.as_str())
        && !unsafe_names.contains(origin.rsplit_once('.').map_or("", |(p, _)| p))
        && !escaped.contains(root.id.as_str())
        && methods::proven(scan, env, base, stmt, None, &[&origin])?)
}

pub(super) fn dataclass(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    unsafe_names: &HashSet<String>,
) -> Result<bool> {
    let Stmt::ClassDef(n) = stmt else {
        return Ok(false);
    };
    if !methods::direct(env, stmt)
        || n.arguments
            .as_ref()
            .is_some_and(|a| !a.args.is_empty() || !a.keywords.is_empty())
        || n.decorator_list.len() != 1
        || unsafe_names.contains("dataclasses")
    {
        return Ok(false);
    }
    let Some(decorator) = n.decorator_list.first() else {
        return Ok(false);
    };
    let expression = &decorator.expression;
    let target = match expression {
        Expr::Call(n) => &*n.func,
        n => n,
    };
    let Expr::Name(target) = target else {
        return Ok(false);
    };
    if !env.unique.contains(target.id.as_str())
        || !methods::proven(
            scan,
            env,
            expression,
            stmt,
            None,
            &["dataclasses.dataclass"],
        )?
    {
        return Ok(false);
    }
    if let Expr::Call(call) = expression {
        if !call.arguments.args.is_empty() {
            return Ok(false);
        }
        for kw in &call.arguments.keywords {
            scan.tick(1)?;
            if !kw
                .arg
                .as_ref()
                .is_some_and(|n| OPTIONS.contains(&n.as_str()))
                || !matches!(kw.value, Expr::BooleanLiteral(_))
            {
                return Ok(false);
            }
        }
    }
    Ok(true)
}

pub(super) fn native(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
) -> Result<bool> {
    if !methods::direct(env, stmt) {
        return Ok(false);
    }
    if dataclass(scan, env, stmt, unsafe_names)? {
        return classes::native_body(scan, env, stmt);
    }
    if !typed(scan, env, stmt, unsafe_names, escaped)? {
        return Ok(false);
    }
    let Stmt::ClassDef(n) = stmt else {
        return Err("native header lost its class".into());
    };
    for child in &n.body {
        scan.tick(1)?;
        if !typed_item(scan, env, child)? {
            return Ok(false);
        }
    }
    Ok(true)
}

fn typed_item(scan: &mut Scan, env: &Env<'_>, child: &Stmt) -> Result<bool> {
    Ok(match child {
        Stmt::Pass(_) => true,
        Stmt::Expr(n) => matches!(&*n.value, Expr::StringLiteral(_)),
        Stmt::AnnAssign(_) => {
            let Some(annotation) = statements::annotation_field(child) else {
                return Ok(false);
            };
            classes::deferred(scan, env, annotation)?
                || type_refs::bare(
                    env,
                    annotation,
                    &["str", "int", "float", "bool", "bytes", "object"],
                )
        }
        _ => false,
    })
}

pub(super) fn bases(scan: &mut Scan, env: &Env<'_>, n: &StmtClassDef) -> Result<bool> {
    let mut custom = 0;
    for base in n.bases() {
        scan.tick(1)?;
        let head = match base {
            Expr::Subscript(n) => &*n.value,
            n => n,
        };
        let root = type_refs::root(scan, head)?;
        if !(FRAMEWORKS.contains(&resolve(scan, env.module, head)?.as_str())
            && root.is_some_and(|r| {
                !env.bound.contains(r)
                    || scan.aliases.contains_key(r)
                        && env.stable.contains(r)
                        && env.unique.contains(r)
            }))
        {
            custom += 1;
        }
    }
    Ok(custom <= 1)
}

pub(super) fn creation(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    owner: bool,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
) -> Result<bool> {
    let Stmt::ClassDef(n) = stmt else {
        return Ok(false);
    };
    if n.bases().len() == 1 {
        if let Some(base) = n.bases().first() {
            if TYPED.contains(&resolve(scan, env.module, base)?.as_str()) {
                return native(scan, env, stmt, unsafe_names, escaped);
            }
        }
    }
    Ok((n.decorator_list.is_empty()
        && n.arguments.as_ref().is_none_or(|a| a.keywords.is_empty())
        && !classes::unproven(scan, env, stmt, false)?
        && bases(scan, env, n)?)
        || owner && native(scan, env, stmt, unsafe_names, escaped)?)
}

pub(super) fn generic(
    scan: &mut Scan,
    env: &Env<'_>,
    expr: &Expr,
    stmt: &Stmt,
    unsafe_names: &HashSet<String>,
    escaped: &HashSet<String>,
    visited: &mut HashSet<String>,
) -> Result<bool> {
    if visited.len() >= 100 {
        return Err("generic proof depth limit exceeded (100 levels)".into());
    }
    if unsafe_names.contains("typing") {
        return Ok(false);
    }
    let head = match expr {
        Expr::Subscript(n) => &*n.value,
        n => n,
    };
    if methods::proven(scan, env, head, stmt, None, &["typing.Generic"])? {
        return Ok(true);
    }
    let Expr::Name(head) = head else {
        return Ok(false);
    };
    if visited.contains(head.id.as_str()) {
        return Ok(false);
    }
    let mut definitions = Vec::new();
    for node in &env.module.tree.body {
        scan.tick(1)?;
        if let Stmt::ClassDef(n) = node {
            if n.name.as_str() == head.id.as_str() {
                definitions.push((node, n));
            }
        }
    }
    if definitions.len() != 1
        || !names::once_before(scan, &env.module.tree.body, stmt, head.id.as_str())?
    {
        return Ok(false);
    }
    let Some((definition, n)) = definitions.first().copied() else {
        return Ok(false);
    };
    if types::generic(scan, env, definition, n)?.is_empty()
        || !creation(scan, env, definition, true, unsafe_names, escaped)?
    {
        return Ok(false);
    }
    for child in &n.body {
        scan.tick(1)?;
        let bindings = statements::binding(scan, &Node::Stmt(child), env.module.text())?;
        let Some(names) = bindings.get(0).and_then(serde_json::Value::as_array) else {
            continue;
        };
        for name in names {
            scan.tick(1)?;
            if name.as_str().is_some_and(|s| s.starts_with("__")) {
                return Ok(false);
            }
        }
    }
    visited.insert(head.id.to_string());
    let mut proven = true;
    for base in n.bases() {
        scan.tick(1)?;
        if !generic(scan, env, base, definition, unsafe_names, escaped, visited)? {
            proven = false;
            break;
        }
    }
    visited.remove(head.id.as_str());
    Ok(proven)
}
