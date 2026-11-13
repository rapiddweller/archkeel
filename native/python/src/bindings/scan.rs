// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared bounded walk, below each binding consumer.

use std::collections::{BTreeSet, HashMap, VecDeque};
use std::rc::Rc;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{Expr, Stmt};

use super::output::Output;
use crate::module::Module;
use crate::parse::work::Work;
use crate::pyast::{child_nodes, walk, Node};

pub(super) const MAX_BINDING_WORK: usize = 64_000_000;

pub(super) type Result<T> = std::result::Result<T, String>;

pub(super) fn input_array<'a>(
    input: &'a serde_json::Value,
    key: &str,
) -> Result<&'a [serde_json::Value]> {
    match input.get(key) {
        None => Ok(&[]),
        Some(value) => value
            .as_array()
            .map(Vec::as_slice)
            .ok_or_else(|| format!("invalid {key} array")),
    }
}

pub struct Table {
    pub data: Result<serde_json::Value>,
    pub work: usize,
}

pub(super) fn table(
    module: &Module,
    minor: PyMinor,
    collect: impl FnOnce(&Module, &mut Scan) -> Result<serde_json::Value>,
) -> Table {
    let mut scan = Scan::new(minor);
    let data = collect(module, &mut scan).and_then(|data| {
        super::output::check(&data)?;
        Ok(data)
    });
    Table {
        data,
        work: scan.work.used(),
    }
}

pub(super) fn counts(scan: &mut Scan, values: Vec<String>) -> Result<HashMap<String, usize>> {
    let mut out = HashMap::new();
    for value in values {
        scan.tick(1)?;
        *out.entry(value).or_default() += 1;
    }
    Ok(out)
}

pub(super) struct Scan {
    pub minor: PyMinor,
    pub work: Work,
    pub output: Output,
    pub aliases: HashMap<String, (String, bool)>,
}

impl Scan {
    pub fn new(minor: PyMinor) -> Self {
        Self {
            minor,
            work: Work::with_limit(MAX_BINDING_WORK),
            output: Output::new(),
            aliases: HashMap::new(),
        }
    }

    pub fn keep(
        &mut self,
        rows: &mut Vec<serde_json::Value>,
        row: serde_json::Value,
    ) -> Result<()> {
        self.output.value(&row)?;
        rows.push(row);
        Ok(())
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

    pub fn module_nodes<'a>(&mut self, module: &'a Module) -> Result<Vec<Node<'a>>> {
        self.tick(module.tree.body.len())?;
        let mut pending: VecDeque<_> = module.tree.body.iter().map(Node::Stmt).collect();
        let mut nodes = Vec::new();
        while let Some(node) = pending.pop_front() {
            self.tick(1)?;
            pending.extend(self.children(&node)?);
            nodes.push(node);
        }
        Ok(nodes)
    }
}

pub(super) fn parents<'a>(
    scan: &mut Scan,
    nodes: &[Node<'a>],
) -> Result<HashMap<*const Expr, Node<'a>>> {
    let mut parents = HashMap::new();
    for node in nodes {
        scan.tick(1)?;
        for child in scan.children(node)? {
            scan.tick(1)?;
            let Node::Expr(expr) = child else { continue };
            parents.insert(std::ptr::from_ref(expr), node.clone());
        }
    }
    Ok(parents)
}
pub(super) fn future_annotations(scan: &mut Scan, module: &Module) -> Result<bool> {
    for stmt in &module.tree.body {
        scan.tick(1)?;
        let Stmt::ImportFrom(import) = stmt else {
            continue;
        };
        if !import
            .module
            .as_ref()
            .is_some_and(|n| n.as_str() == "__future__")
        {
            continue;
        }
        for alias in &import.names {
            scan.tick(1)?;
            if alias.name.as_str() == "annotations" {
                return Ok(true);
            }
        }
    }
    Ok(false)
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
