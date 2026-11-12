// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class-body inputs for the next binding proof: expressions, literal enum members and allocation.

use std::collections::BTreeMap;

use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use ruff_text_size::Ranged;
use serde_json::{json, Value};

use super::scan::{constant, Result, Scan};
use super::{namespace, scopes};
use crate::pyast::Node;
use crate::unparse::{self, TextFailure};

pub(super) fn text(scan: &mut Scan, expr: &Expr, source: &str) -> Result<Option<String>> {
    // Charge every node visited by the text writer before it runs.
    scan.walk(Node::Expr(expr))?;
    scan.tick(expr.range().len().to_usize())?;
    match unparse::unparse(expr, scan.minor, source) {
        Ok(text) => Ok(Some(text)),
        Err(TextFailure::Invalid) => Ok(None),
        Err(failure) => Err(format!("binding expression text unseen: {failure:?}")),
    }
}

pub(super) fn expressions<'a>(scan: &mut Scan, node: &'a StmtClassDef) -> Result<Vec<Node<'a>>> {
    let mut out = scopes::class_header(scan, node)?;
    for child in &node.body {
        scan.tick(1)?;
        match child {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {
                out.extend(scopes::evaluated(scan, &Node::Stmt(child))?)
            }
            Stmt::AnnAssign(n) => {
                out.extend([Node::Expr(&n.annotation), Node::Expr(&n.target)]);
                out.extend(n.value.as_deref().map(Node::Expr));
            }
            Stmt::Assign(n) => {
                scan.tick(n.targets.len())?;
                out.extend(n.targets.iter().map(Node::Expr));
                out.push(Node::Expr(&n.value));
            }
            Stmt::Expr(n) => out.push(Node::Expr(&n.value)),
            Stmt::Delete(n) => {
                scan.tick(n.targets.len())?;
                out.extend(n.targets.iter().map(Node::Expr));
            }
            _ => {}
        }
    }
    Ok(out)
}

pub(super) fn enum_members(scan: &mut Scan, node: &StmtClassDef) -> Result<Vec<String>> {
    let mut assigned = BTreeMap::new();
    for child in &node.body {
        scan.tick(1)?;
        let (targets, value) = match child {
            Stmt::Assign(n) => (n.targets.iter().collect::<Vec<_>>(), Some(&*n.value)),
            Stmt::AnnAssign(n) => (vec![&*n.target], n.value.as_deref()),
            Stmt::Delete(n) => {
                scan.tick(n.targets.len())?;
                assigned.extend(n.targets.iter().filter_map(|n| match n {
                    Expr::Name(n) => Some((n.id.to_string(), false)),
                    _ => None,
                }));
                continue;
            }
            _ => continue,
        };
        scan.tick(targets.len())?;
        if targets
            .iter()
            .any(|t| matches!(t, Expr::Name(n) if n.id.as_str() == "_ignore_"))
        {
            return Ok(Vec::new());
        }
        if targets.len() != 1 {
            continue;
        }
        if let Some(Expr::Name(n)) = targets.first() {
            if !n.id.starts_with('_') {
                let valid = !assigned.contains_key(n.id.as_str()) && value.is_some_and(constant);
                assigned.insert(n.id.to_string(), valid);
            }
        }
    }
    scan.tick(assigned.len())?;
    Ok(assigned
        .into_iter()
        .filter_map(|(name, valid)| valid.then_some(name))
        .collect())
}

fn frozen_call(scan: &mut Scan, expr: &Expr, pydantic: bool) -> Result<bool> {
    let Expr::Call(n) = expr else {
        return Ok(false);
    };
    let Some(name) = namespace::dotted(scan, &n.func)? else {
        return Ok(false);
    };
    let admitted = if pydantic {
        name == "pydantic.ConfigDict"
    } else {
        matches!(
            name.as_str(),
            "dataclasses.dataclass" | "pydantic.dataclasses.dataclass"
        )
    };
    scan.tick(n.arguments.keywords.len())?;
    Ok(admitted
        && n.arguments.keywords.iter().any(|k| {
            k.arg.as_ref().is_some_and(|a| a.as_str() == "frozen")
                && matches!(k.value, Expr::BooleanLiteral(ref b) if b.value)
        }))
}

pub(super) fn frozen(scan: &mut Scan, node: &StmtClassDef, pydantic: bool) -> Result<bool> {
    for decorator in &node.decorator_list {
        scan.tick(1)?;
        if frozen_call(scan, &decorator.expression, false)? {
            return Ok(true);
        }
    }
    if !pydantic {
        return Ok(false);
    }
    for child in &node.body {
        scan.tick(1)?;
        let value = match child {
            Stmt::Assign(n) => Some(&*n.value),
            Stmt::AnnAssign(n) => n.value.as_deref(),
            _ => None,
        };
        let targets = super::names::targets(child);
        scan.tick(targets.len())?;
        if !targets
            .iter()
            .any(|t| matches!(t, Expr::Name(n) if n.id.as_str() == "model_config"))
        {
            continue;
        }
        let Some(value) = value else {
            continue;
        };
        if frozen_call(scan, value, true)? {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(super) fn default_body(scan: &mut Scan, node: &StmtClassDef) -> Result<bool> {
    for child in &node.body {
        scan.tick(1)?;
        match child {
            Stmt::Pass(_) => {}
            Stmt::Expr(n) if constant(&n.value) => {}
            Stmt::FunctionDef(n) => {
                let p = &n.parameters;
                scan.tick(p.len())?;
                let annotated = p
                    .posonlyargs
                    .iter()
                    .chain(&p.args)
                    .chain(&p.kwonlyargs)
                    .any(|p| p.default.is_some() || p.parameter.annotation.is_some())
                    || p.vararg
                        .iter()
                        .chain(&p.kwarg)
                        .any(|p| p.annotation.is_some());
                if !n.decorator_list.is_empty() || n.returns.is_some() || annotated {
                    return Ok(false);
                }
            }
            _ => return Ok(false),
        }
    }
    Ok(true)
}

pub(super) fn data(scan: &mut Scan, node: &StmtClassDef, source: &str) -> Result<Value> {
    let mut texts = Vec::new();
    for expr in expressions(scan, node)? {
        scan.tick(1)?;
        if let Some(expr) = expr.expr() {
            texts.push(text(scan, expr, source)?);
        }
    }
    Ok(
        json!({"expressions": texts, "enum": enum_members(scan, node)?,
        "frozen": [frozen(scan, node, false)?, frozen(scan, node, true)?],
        "default_body": default_body(scan, node)?}),
    )
}
