// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Type-alias seeds and explicit Generic parameters for import proofs.

use super::super::scan::{Result, Scan};
use super::super::{class, names, scopes};
use super::{methods, resolve, Env};
use crate::pyast::Node;
use ruff_python_ast::{Expr, Operator, Stmt, StmtClassDef};
use serde_json::{json, Value};
use std::collections::{BTreeSet, HashSet};

fn static_alias(scan: &mut Scan, env: &Env<'_>, expr: &Expr) -> Result<bool> {
    Ok(match expr {
        Expr::Name(_) => true,
        Expr::BinOp(n) if n.op == Operator::BitOr => true,
        Expr::Subscript(n) => matches!(
            resolve(scan, env.module, &n.value)?.as_str(),
            "typing.Annotated"
                | "typing.Literal"
                | "typing.Optional"
                | "typing.Union"
                | "typing_extensions.Annotated"
                | "typing_extensions.Literal"
                | "typing_extensions.TypeAliasType"
                | "dict"
                | "list"
                | "set"
                | "tuple"
                | "frozenset"
        ),
        _ => false,
    })
}

fn admitted<'a>(scan: &mut Scan, env: &Env<'_>, stmt: &'a Stmt) -> Result<Option<&'a Expr>> {
    if !methods::direct(env, stmt) {
        return Ok(None);
    }
    match stmt {
        Stmt::Assign(n) if n.targets.len() == 1 => {
            if let Some(Expr::Name(target)) = n.targets.first() {
                if target.id.chars().next().is_some_and(char::is_uppercase)
                    && static_alias(scan, env, &n.value)?
                {
                    return Ok(Some(&n.value));
                }
            }
        }
        Stmt::AnnAssign(n) if matches!(&*n.target, Expr::Name(_)) => {
            if n.value.is_some() && resolve(scan, env.module, &n.annotation)? == "typing.TypeAlias"
            {
                return Ok(n.value.as_deref());
            }
        }
        Stmt::TypeAlias(n)
            if n.type_params
                .as_ref()
                .is_none_or(|n| n.type_params.is_empty()) =>
        {
            return Ok(Some(&n.value))
        }
        _ => {}
    }
    Ok(None)
}

fn nullable(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<BTreeSet<String>> {
    let bound = names::bound(scan, nodes)?;
    let counts = super::counts(scan, bound)?;
    let mut out = BTreeSet::new();
    let opaque = env.opaque;
    // Only a direct assignment can be admitted; module_scope_bindings can repeat its name.
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Some(Expr::BinOp(n)) = admitted(scan, env, stmt)? else {
            continue;
        };
        let Expr::Name(root) = &*n.left else {
            continue;
        };
        if n.op != Operator::BitOr
            || root.id.as_str() != "str"
            || opaque
            || env.bound.contains("str")
            || !matches!(&*n.right, Expr::NoneLiteral(_))
        {
            continue;
        }
        let targets = match stmt {
            Stmt::TypeAlias(n) => vec![&*n.name],
            _ => names::targets(stmt),
        };
        let bindings = names::stored_names(scan, targets)?;
        for name in bindings {
            scan.tick(1)?;
            if env.stable.contains(&name) && counts.get(&name) == Some(&1) {
                out.insert(name);
            }
        }
    }
    Ok(out)
}

fn root(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(n) => Some(n.id.as_str()),
        Expr::Attribute(n) => match &*n.value {
            Expr::Name(n) => Some(n.id.as_str()),
            _ => None,
        },
        _ => None,
    }
}

fn generic(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    class: &StmtClassDef,
) -> Result<Vec<String>> {
    let mut bases = Vec::new();
    for base in class.bases() {
        scan.tick(1)?;
        if let Expr::Subscript(n) = base {
            if matches!(
                resolve(scan, env.module, &n.value)?.as_str(),
                "typing.Generic" | "typing_extensions.Generic"
            ) {
                bases.push(n);
            }
        }
    }
    if bases.len() != 1 {
        return Ok(Vec::new());
    }
    let mut typevars = HashSet::new();
    for statement in &env.module.tree.body {
        scan.tick(1)?;
        let targets = names::targets(statement);
        if targets.len() != 1 {
            continue;
        }
        let Some(Expr::Name(name)) = targets.first().copied() else {
            continue;
        };
        let value = match statement {
            Stmt::Assign(n) => Some(&*n.value),
            Stmt::AnnAssign(n) => n.value.as_deref(),
            _ => None,
        };
        let Some(Expr::Call(value)) = value else {
            continue;
        };
        let Some(root) = root(&value.func) else {
            continue;
        };
        if names::once_before(scan, &env.module.tree.body, statement, root)?
            && matches!(
                resolve(scan, env.module, &value.func)?.as_str(),
                "typing.TypeVar" | "typing_extensions.TypeVar"
            )
            && matches!(value.arguments.args.first(), Some(Expr::StringLiteral(n)) if n.value.to_str() == name.id.as_str())
            && names::once_before(scan, &env.module.tree.body, stmt, name.id.as_str())?
        {
            typevars.insert(name.id.as_str());
        }
    }
    let Some(base) = bases.first() else {
        return Ok(Vec::new());
    };
    let Some(root) = root(&base.value) else {
        return Ok(Vec::new());
    };
    if !names::once_before(scan, &env.module.tree.body, stmt, root)? {
        return Ok(Vec::new());
    }
    let args = match &*base.slice {
        Expr::Tuple(n) => n.elts.as_slice(),
        n => std::slice::from_ref(n),
    };
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for arg in args {
        scan.tick(1)?;
        let Expr::Name(n) = arg else {
            return Ok(Vec::new());
        };
        if !typevars.contains(n.id.as_str()) || !seen.insert(n.id.as_str()) {
            return Ok(Vec::new());
        }
        out.push(n.id.to_string());
    }
    Ok(out)
}

fn setters(scan: &mut Scan, env: &Env<'_>) -> Result<BTreeSet<(i64, i64, i64)>> {
    let mut references = BTreeSet::new();
    for owner in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::ClassDef(class) = owner else {
            continue;
        };
        let properties = methods::properties(scan, env, owner)?;
        for stmt in &class.body {
            scan.tick(1)?;
            let Stmt::FunctionDef(method) = stmt else {
                continue;
            };
            let Some(binding) = properties.get(&std::ptr::from_ref(method)) else {
                continue;
            };
            if binding.get("operation").and_then(Value::as_str) != Some("setter") {
                continue;
            }
            setter_references(scan, env, method, &mut references)?;
        }
    }
    Ok(references)
}

fn setter_references(
    scan: &mut Scan,
    env: &Env<'_>,
    method: &ruff_python_ast::StmtFunctionDef,
    references: &mut BTreeSet<(i64, i64, i64)>,
) -> Result<()> {
    let parameters = method
        .parameters
        .posonlyargs
        .iter()
        .chain(&method.parameters.args)
        .skip(1)
        .chain(&method.parameters.kwonlyargs);
    let mut matches = false;
    for parameter in parameters {
        scan.tick(1)?;
        matches |= parameter.parameter.name.as_str() == method.name.as_str();
    }
    if !matches {
        return Ok(());
    }
    let nodes = scopes::own(scan, &method.body)?;
    let mut global = false;
    let mut nested = HashSet::new();
    for node in &nodes {
        scan.tick(1)?;
        let declared = match node {
            Node::Stmt(Stmt::Global(n)) => n.names.as_slice(),
            Node::Stmt(Stmt::Nonlocal(n)) => n.names.as_slice(),
            _ => &[],
        };
        for name in declared {
            scan.tick(1)?;
            global |= name.as_str() == method.name.as_str();
        }
        if !matches!(
            node,
            Node::Expr(
                Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_)
            )
        ) {
            continue;
        }
        for node in scan.walk(node.clone())? {
            scan.tick(1)?;
            let Some(expr) = node.expr() else {
                continue;
            };
            nested.insert(std::ptr::from_ref(expr));
        }
    }
    if global {
        return Ok(());
    }
    for node in nodes {
        scan.tick(1)?;
        if let Node::Expr(expr @ Expr::Name(n)) = node {
            if n.id.as_str() == method.name.as_str() && !nested.contains(&std::ptr::from_ref(expr))
            {
                let at = env.module.location(n);
                references.insert((at.line, at.end_line, at.column));
            }
        }
    }
    Ok(())
}

pub(super) fn table(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<Value> {
    let mut expressions = Vec::new();
    let mut aliases = Vec::new();
    let mut generics = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        match node {
            Node::Expr(
                expr @ (Expr::Name(_) | Expr::Attribute(_) | Expr::Subscript(_) | Expr::BinOp(_)),
            ) => {
                let at = env.module.location(*expr);
                let row = json!([
                    at.line,
                    at.column,
                    resolve(scan, env.module, expr)?,
                    static_alias(scan, env, expr)?
                ]);
                scan.output.value(&row)?;
                expressions.push(row);
            }
            Node::Stmt(stmt) => {
                if let Some(value) = admitted(scan, env, stmt)? {
                    let row = json!([
                        env.module.location(*stmt).line,
                        class::text(scan, value, env.module.text())?
                    ]);
                    scan.output.value(&row)?;
                    aliases.push(row);
                }
                if let Stmt::ClassDef(class) = stmt {
                    let at = env.module.location(
                        &crate::module::definition::Def::Class(class).range(env.module.text()),
                    );
                    let row = json!([at.line, generic(scan, env, stmt, class)?]);
                    scan.output.value(&row)?;
                    generics.push(row);
                }
            }
            _ => {}
        }
    }
    Ok(
        json!({"expressions":expressions, "aliases":aliases, "generics":generics, "nullable":nullable(scan, env, nodes)?, "setters":setters(scan, env)?}),
    )
}
