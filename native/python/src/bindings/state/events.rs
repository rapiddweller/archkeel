// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Function events retain ast.walk breadth-first order, including nested definitions.

use super::*;

pub(super) fn collect(
    scan: &mut Scan,
    module: &Module,
    stmt: &Stmt,
    evidence: &mut EvidenceMap,
) -> Result<Vec<Value>> {
    let nodes = scan.walk(Node::Stmt(stmt))?;
    let mut parents = HashMap::new();
    for node in &nodes {
        scan.tick(1)?;
        for child in scan.children(node)? {
            scan.tick(1)?;
            if let Node::Expr(n) = child {
                parents.insert(std::ptr::from_ref(n), node.clone());
            }
        }
    }
    let mut events = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let assignment = match &node {
            Node::Stmt(Stmt::Assign(n)) => Some((n.targets.as_slice(), Some(&*n.value), None)),
            Node::Stmt(Stmt::AnnAssign(n)) => Some((
                std::slice::from_ref(&*n.target),
                n.value.as_deref(),
                Some(&*n.annotation),
            )),
            _ => None,
        };
        if let Some((targets, value, annotation)) = assignment {
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
            let row = json!({"kind": "assignment", "targets": names, "constructor": constructor,
                "annotation": text(scan,module,annotation)?, "alias": alias});
            scan.keep(&mut events, row)?;
        }
        if let Node::Expr(expr @ Expr::Attribute(n)) = &node {
            let parent = parents.get(&std::ptr::from_ref(*expr));
            if matches!(parent, Some(Node::Expr(Expr::Attribute(p))) if std::ptr::eq(&*p.value, *expr))
            {
                continue;
            }
            let Some((binding, path)) = attribute_path(scan, expr)? else {
                continue;
            };
            let mut access = if matches!(n.ctx, ExprContext::Store | ExprContext::Del) {
                "write"
            } else {
                "read"
            };
            let evidence_id = if let Some(Node::Expr(Expr::Call(call))) = parent {
                if std::ptr::eq(&*call.func, *expr)
                    && path.len() > 1
                    && path.last().is_some_and(|n| mutating(n))
                {
                    access = "mutation";
                    module.evidence(evidence, call)
                } else {
                    module.evidence(evidence, n)
                }
            } else {
                module.evidence(evidence, n)
            };
            scan.keep(&mut events, json!({"kind": "attribute", "binding": binding, "path": path, "access": access, "evidence_id": evidence_id}))?;
        }
        if let Node::Expr(Expr::Call(n)) = node {
            for argument in n
                .arguments
                .args
                .iter()
                .chain(n.arguments.keywords.iter().map(|k| &k.value))
            {
                scan.tick(1)?;
                if let Expr::Name(p) = argument {
                    let target = text(scan, module, Some(&n.func))?
                        .filter(|t| !t.is_empty())
                        .unwrap_or_else(|| "<dynamic>".into());
                    scan.keep(
                        &mut events,
                        json!({"kind": "pass", "binding": p.id.as_str(), "target": target,
                        "evidence_id": module.evidence(evidence,n)}),
                    )?;
                }
            }
        }
    }
    Ok(events)
}
