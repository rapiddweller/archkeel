// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The fields of a function that need only its own node (`symbols.py`): `_function_signature`,
//! `_parameters_contained`, `_stored_field_writes` and `_shape`.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExprContext, Parameter, Stmt, StmtFunctionDef};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use super::scan::Scan;
use crate::pyast::{walk, Node};

fn address(expr: &Expr) -> usize {
    std::ptr::from_ref(expr).addr()
}

/// `_parameters_contained`: each read of a parameter in the body (nested scopes included) is an
/// operand of a comparison or the index of a subscript, and no subscript is a target.
pub(super) fn parameters_contained(
    node: &StmtFunctionDef,
    minor: archkeel_facts::pyminor::PyMinor,
) -> bool {
    let params = &node.parameters;
    let names: HashSet<&str> = params
        .iter()
        .map(|param| param.as_parameter().name.as_str())
        .collect();
    let children: Vec<Node<'_>> = node
        .body
        .iter()
        .flat_map(|stmt| walk(Node::Stmt(stmt), minor))
        .collect();
    let mut allowed: HashSet<usize> = HashSet::new();
    for child in &children {
        match child.expr() {
            Some(Expr::Compare(compare)) => allowed.extend(compare.operands.iter().map(address)),
            Some(Expr::Subscript(subscript)) => {
                if subscript.ctx != ExprContext::Load {
                    return false;
                }
                allowed.insert(address(&subscript.slice));
            }
            _ => {}
        }
    }
    children.iter().all(|child| match child.expr() {
        Some(expr @ Expr::Name(name)) if names.contains(name.id.as_str()) => {
            allowed.contains(&address(expr))
        }
        _ => true,
    })
}

/// `_stored_field_writes` of an `__init__`: `<receiver>.<field> = <parameter>` in the top-level
/// body, where the parameter is positional and not the first one.
pub(super) fn stored_field_writes(scan: &mut Scan<'_>, node: &StmtFunctionDef) -> Value {
    let params = &node.parameters;
    let parameters: HashMap<&str, &Parameter> = params
        .posonlyargs
        .iter()
        .chain(&params.args)
        .skip(1)
        .map(|item| (item.parameter.name.as_str(), &item.parameter))
        .collect();
    let mut writes = Vec::new();
    for statement in &node.body {
        let (targets, value): (Vec<&Expr>, Option<&Expr>) = match statement {
            Stmt::Assign(assign) => (assign.targets.iter().collect(), Some(&*assign.value)),
            Stmt::AnnAssign(assign) => (vec![&*assign.target], assign.value.as_deref()),
            _ => continue,
        };
        let Some(Expr::Name(value)) = value else {
            continue;
        };
        let Some(param) = parameters.get(value.id.as_str()) else {
            continue;
        };
        for target in targets {
            let Expr::Attribute(attribute) = target else {
                continue;
            };
            let Expr::Name(receiver) = &*attribute.value else {
                continue;
            };
            let annotation = param
                .annotation
                .as_deref()
                .map(|annotation| scan.evidence(annotation));
            writes.push(json!({
                "field": attribute.attr.as_str(),
                "receiver": receiver.id.as_str(),
                "parameter": value.id.as_str(),
                "evidence_id": scan.evidence(statement),
                "annotation_evidence_id": annotation,
            }));
        }
    }
    Value::Array(writes)
}

/// `_shape`: the class names of the body (without a leading docstring) in walk order, digested.
pub(super) fn shape(
    node: &StmtFunctionDef,
    minor: archkeel_facts::pyminor::PyMinor,
) -> (String, usize) {
    let mut body: &[Stmt] = &node.body;
    if let Some(Stmt::Expr(first)) = body.first() {
        if is_constant(&first.value) {
            body = &body[1..];
        }
    }
    let kinds: Vec<&str> = body
        .iter()
        .flat_map(|stmt| walk(Node::Stmt(stmt), minor))
        .map(|node| node.kind())
        .collect();
    let digest = Sha256::digest(kinds.join("\n").as_bytes());
    let hex: String = digest
        .iter()
        .take(8)
        .map(|byte| format!("{byte:02x}"))
        .collect();
    (hex, kinds.len())
}

fn is_constant(expr: &Expr) -> bool {
    matches!(
        expr,
        Expr::StringLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::EllipsisLiteral(_)
    )
}
