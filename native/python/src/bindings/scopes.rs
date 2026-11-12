// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python evaluated-module and own-body traversal boundaries.

use ruff_python_ast::{Expr, Parameters, Stmt};

use super::scan::{Result, Scan};
use crate::pyast::Node;

pub(super) fn function_header<'a>(params: &'a Parameters, out: &mut Vec<Node<'a>>) {
    out.extend(
        params
            .posonlyargs
            .iter()
            .chain(&params.args)
            .filter_map(|p| p.default.as_deref())
            .map(Node::Expr),
    );
    out.extend(
        params
            .kwonlyargs
            .iter()
            .filter_map(|p| p.default.as_deref())
            .map(Node::Expr),
    );
    out.extend(
        params
            .posonlyargs
            .iter()
            .chain(&params.args)
            .chain(&params.kwonlyargs)
            .filter_map(|p| p.parameter.annotation.as_deref())
            .map(Node::Expr),
    );
    out.extend(
        params
            .vararg
            .iter()
            .chain(&params.kwarg)
            .filter_map(|p| p.annotation.as_deref())
            .map(Node::Expr),
    );
}

pub(super) fn evaluated<'a>(scan: &mut Scan, node: &Node<'a>) -> Result<Vec<Node<'a>>> {
    let mut children = Vec::new();
    match node {
        Node::Stmt(Stmt::FunctionDef(n)) => {
            scan.tick(
                n.decorator_list
                    .len()
                    .saturating_add(n.parameters.len().saturating_mul(2)),
            )?;
            children.extend(n.decorator_list.iter().map(|d| Node::Expr(&d.expression)));
            function_header(&n.parameters, &mut children);
            children.extend(n.returns.as_deref().map(Node::Expr));
        }
        Node::Stmt(Stmt::ClassDef(n)) => {
            scan.tick(n.decorator_list.len())?;
            children.extend(n.decorator_list.iter().map(|d| Node::Expr(&d.expression)));
            if let Some(args) = &n.arguments {
                scan.tick(args.args.len().saturating_add(args.keywords.len()))?;
                children.extend(args.args.iter().map(Node::Expr));
                children.extend(args.keywords.iter().map(|k| Node::Expr(&k.value)));
            }
        }
        Node::Expr(Expr::Lambda(n)) => {
            if let Some(params) = &n.parameters {
                scan.tick(params.len())?;
                children.extend(
                    params
                        .posonlyargs
                        .iter()
                        .chain(&params.args)
                        .chain(&params.kwonlyargs)
                        .filter_map(|p| p.default.as_deref())
                        .map(Node::Expr),
                );
            }
        }
        Node::Comprehension(n) => {
            scan.tick(n.ifs.len())?;
            children.push(Node::Expr(&n.iter));
            children.extend(n.ifs.iter().map(Node::Expr));
        }
        _ => children = scan.children(node)?,
    }
    Ok(children)
}

pub(super) fn module_scope<'a>(scan: &mut Scan, body: &'a [Stmt]) -> Result<Vec<Node<'a>>> {
    scan.tick(body.len())?;
    let mut pending: Vec<_> = body.iter().rev().map(Node::Stmt).collect();
    let mut out = Vec::new();
    while let Some(node) = pending.pop() {
        scan.tick(1)?;
        pending.extend(evaluated(scan, &node)?.into_iter().rev());
        out.push(node);
    }
    Ok(out)
}

pub(super) fn own<'a>(scan: &mut Scan, body: &'a [Stmt]) -> Result<Vec<Node<'a>>> {
    scan.tick(body.len())?;
    let mut pending: Vec<_> = body.iter().rev().map(Node::Stmt).collect();
    let mut out = Vec::new();
    while let Some(node) = pending.pop() {
        scan.tick(1)?;
        if !matches!(
            node,
            Node::Stmt(Stmt::FunctionDef(_) | Stmt::ClassDef(_)) | Node::Expr(Expr::Lambda(_))
        ) {
            pending.extend(scan.children(&node)?.into_iter().rev());
        }
        out.push(node);
    }
    Ok(out)
}
