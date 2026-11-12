// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared bounded walk, below each binding consumer.

use std::collections::BTreeSet;
use std::rc::Rc;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{Expr, Stmt};

use super::output::Output;
use crate::parse::work::Work;
use crate::pyast::{child_nodes, walk, Node};

pub(super) const MAX_BINDING_WORK: usize = 64_000_000;

pub(super) type Result<T> = std::result::Result<T, String>;

pub(super) struct Scan {
    pub minor: PyMinor,
    pub work: Work,
    pub output: Output,
}

impl Scan {
    pub fn new(minor: PyMinor) -> Self {
        Self {
            minor,
            work: Work::with_limit(MAX_BINDING_WORK),
            output: Output::new(),
        }
    }

    pub fn owner(&mut self, parent: &str, name: &str) -> Result<Rc<str>> {
        let bytes = parent.len().saturating_add(name.len()).saturating_add(1);
        self.tick(bytes.saturating_mul(2))?;
        Ok(Rc::from(format!("{parent}.{name}")))
    }

    pub fn tick(&mut self, count: usize) -> Result<()> {
        if self.work.charge(count) {
            Ok(())
        } else {
            Err("binding work limit exceeded".to_owned())
        }
    }

    pub fn walk<'a>(&mut self, root: Node<'a>) -> Result<Vec<Node<'a>>> {
        let mut nodes = Vec::new();
        for node in walk(root, self.minor) {
            self.tick(1)?;
            nodes.push(node);
        }
        Ok(nodes)
    }

    pub fn children<'a>(&mut self, node: &Node<'a>) -> Result<Vec<Node<'a>>> {
        let children = child_nodes(node, self.minor);
        self.tick(children.len())?;
        Ok(children)
    }
}

pub(super) fn sorted(values: impl IntoIterator<Item = String>) -> Vec<String> {
    values
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

pub(super) fn name<'a>(node: &Node<'a>) -> Option<&'a str> {
    match node {
        Node::Stmt(Stmt::ClassDef(n)) => Some(n.name.as_str()),
        Node::Stmt(Stmt::FunctionDef(n)) => Some(n.name.as_str()),
        _ => None,
    }
}

pub(super) fn constant(expr: &Expr) -> bool {
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
