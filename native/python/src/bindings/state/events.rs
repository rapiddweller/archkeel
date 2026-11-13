// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Function events retain ast.walk order, including nested definitions.

use ruff_python_ast::{Expr, ExprContext, Stmt};
use serde_json::{json, Value};

use super::paths::{attribute_path, mutating, text};
use crate::bindings::scan::{Result, Scan};
use crate::module::{EvidenceMap, Module};
use crate::pyast::Node;

pub(super) fn collect(
    scan: &mut Scan,
    module: &Module,
    stmt: &Stmt,
    evidence: &mut EvidenceMap,
) -> Result<Vec<Value>> {
    let nodes = scan.walk(Node::Stmt(stmt))?;
    let parents = super::super::scan::parents(scan, &nodes)?;
    let mut events = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        if let Some(row) = assignment(scan, module, &node)? {
            scan.keep(&mut events, row)?;
        }
        let Node::Expr(expr) = node else {
            continue;
        };
        if let Some(row) = attribute(
            scan,
            module,
            expr,
            parents.get(&std::ptr::from_ref(expr)),
            evidence,
        )? {
            scan.keep(&mut events, row)?;
        }
        if let Expr::Call(n) = expr {
            arguments(scan, module, n, evidence, &mut events)?;
        }
    }
    Ok(events)
}

fn assignment(scan: &mut Scan, module: &Module, node: &Node<'_>) -> Result<Option<Value>> {
    let (targets, value, annotation) = match node {
        Node::Stmt(Stmt::Assign(n)) => (n.targets.as_slice(), Some(&*n.value), None),
        Node::Stmt(Stmt::AnnAssign(n)) => (
            std::slice::from_ref(&*n.target),
            n.value.as_deref(),
            Some(&*n.annotation),
        ),
        _ => return Ok(None),
    };
    let mut names = Vec::new();
    for target in targets {
        scan.tick(1)?;
        if let Expr::Name(n) = target {
            names.push(n.id.as_str());
        }
    }
    let constructor = match value {
        Some(Expr::Call(n)) => text(scan, module, Some(&n.func))?,
        _ => None,
    };
    let alias = match value {
        Some(Expr::Name(n)) => Some(n.id.as_str()),
        _ => None,
    };
    Ok(Some(
        json!({"kind":"assignment","targets":names,"constructor":constructor,
        "annotation":text(scan,module,annotation)?,"alias":alias}),
    ))
}

fn attribute(
    scan: &mut Scan,
    module: &Module,
    expr: &Expr,
    parent: Option<&Node<'_>>,
    evidence: &mut EvidenceMap,
) -> Result<Option<Value>> {
    let Expr::Attribute(n) = expr else {
        return Ok(None);
    };
    if matches!(parent,Some(Node::Expr(Expr::Attribute(p))) if std::ptr::eq(&*p.value,expr)) {
        return Ok(None);
    }
    let Some((binding, path)) = attribute_path(scan, expr)? else {
        return Ok(None);
    };
    let access = if matches!(n.ctx, ExprContext::Store | ExprContext::Del) {
        "write"
    } else {
        "read"
    };
    let mutation = match parent {
        Some(Node::Expr(Expr::Call(call)))
            if std::ptr::eq(&*call.func, expr)
                && path.len() > 1
                && path.last().is_some_and(|n| mutating(n)) =>
        {
            Some(call)
        }
        _ => None,
    };
    let (access, evidence_id) = match mutation {
        Some(call) => ("mutation", module.evidence(evidence, call)),
        None => (access, module.evidence(evidence, n)),
    };
    Ok(Some(
        json!({"kind":"attribute","binding":binding,"path":path,"access":access,"evidence_id":evidence_id}),
    ))
}

fn arguments(
    scan: &mut Scan,
    module: &Module,
    call: &ruff_python_ast::ExprCall,
    evidence: &mut EvidenceMap,
    events: &mut Vec<Value>,
) -> Result<()> {
    for argument in call
        .arguments
        .args
        .iter()
        .chain(call.arguments.keywords.iter().map(|k| &k.value))
    {
        scan.tick(1)?;
        let Expr::Name(p) = argument else {
            continue;
        };
        let target = text(scan, module, Some(&call.func))?
            .filter(|t| !t.is_empty())
            .unwrap_or_else(|| "<dynamic>".into());
        scan.keep(events,json!({"kind":"pass","binding":p.id.as_str(),"target":target,"evidence_id":module.evidence(evidence,call)}))?;
    }
    Ok(())
}
