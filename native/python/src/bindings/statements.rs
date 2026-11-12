// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class statement admission with the default proof inputs, before provider proofs exist.

use ruff_python_ast::{Expr, Stmt};
use serde_json::{json, Value};

use super::scan::{constant, Result, Scan};
use super::{class, names};
use crate::pyast::Node;

pub(super) fn binding(scan: &mut Scan, node: &Node<'_>, source: &str) -> Result<Value> {
    let (targets, value) = match node {
        Node::Stmt(Stmt::Assign(n)) => (n.targets.iter().collect::<Vec<_>>(), Some(&*n.value)),
        Node::Stmt(Stmt::AnnAssign(n)) => (vec![&*n.target], n.value.as_deref()),
        Node::Expr(Expr::Named(n)) => (vec![&*n.target], Some(&*n.value)),
        _ => (Vec::new(), None),
    };
    scan.tick(targets.len())?;
    if let Some(value) = value {
        let admitted = constant(value)
            || matches!(
                value,
                Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) | Expr::Dict(_)
            );
        if !admitted {
            let lambda = matches!(value, Expr::Lambda(_));
            let stored = names::stored_names(scan, targets.clone())?;
            scan.tick(stored.len())?;
            let public = stored
                .iter()
                .any(|n| !n.starts_with('_') || n.starts_with("__") && n.ends_with("__"));
            if !lambda || public {
                return Ok(Value::Null);
            }
        }
    }
    match node {
        Node::Stmt(Stmt::FunctionDef(n)) => {
            let mut overloaded = false;
            for decorator in &n.decorator_list {
                scan.tick(1)?;
                let expr = match &decorator.expression {
                    Expr::Call(n) => &*n.func,
                    n => n,
                };
                overloaded |= class::text(scan, expr, source)?.as_deref() == Some("overload");
            }
            Ok(json!([[n.name.as_str()], true, overloaded]))
        }
        Node::Stmt(Stmt::ClassDef(n)) => Ok(json!([[n.name.as_str()], false, false])),
        Node::Stmt(Stmt::AnnAssign(n)) => {
            let nodes = if n.value.is_some() {
                scan.walk(Node::Expr(&n.target))?
            } else {
                Vec::new()
            };
            scan.tick(nodes.len())?;
            let bound: Vec<_> = nodes
                .iter()
                .filter_map(|n| match n {
                    Node::Expr(Expr::Name(n)) => Some(n.id.as_str()),
                    _ => None,
                })
                .collect();
            Ok(json!([bound, false, false]))
        }
        Node::Stmt(Stmt::Assign(_)) | Node::Expr(Expr::Named(_)) => {
            Ok(json!([names::stored_names(scan, targets)?, false, false]))
        }
        Node::Stmt(stmt @ (Stmt::Import(_) | Stmt::ImportFrom(_))) => imported(scan, stmt),
        Node::Stmt(Stmt::Delete(_)) => Ok(Value::Null),
        _ => {
            let nodes = scan.walk(node.clone())?;
            Ok(if names::bound(scan, &nodes)?.is_empty() {
                json!([[], false, false])
            } else {
                Value::Null
            })
        }
    }
}

fn imported(scan: &mut Scan, stmt: &Stmt) -> Result<Value> {
    let (aliases, dotted) = match stmt {
        Stmt::Import(n) => (&n.names, true),
        Stmt::ImportFrom(n) => (&n.names, false),
        _ => return Err("class import statement unseen".into()),
    };
    scan.tick(aliases.len().saturating_mul(2))?;
    if aliases
        .iter()
        .any(|n| n.name.as_str() == "*" || dotted && n.asname.is_none() && n.name.contains('.'))
    {
        return Ok(Value::Null);
    }
    Ok(json!([crate::module::import_bindings(stmt), false, false]))
}
