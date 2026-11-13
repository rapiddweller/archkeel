// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class state and ordered function traces. Symbol flags and node selections are explicit inputs.

use std::collections::{BTreeSet, HashMap, VecDeque};

use ruff_python_ast::{Expr, ExprContext, Stmt, StmtClassDef};
use serde_json::{json, Value};

use super::scan::{Result, Scan};
use crate::module::{definition::Def, EvidenceMap, Module};
use crate::pyast::Node;

mod classes;
mod events;

fn mutating(name: &str) -> bool {
    matches!(
        name,
        "add"
            | "append"
            | "clear"
            | "discard"
            | "extend"
            | "insert"
            | "pop"
            | "popitem"
            | "remove"
            | "reverse"
            | "setdefault"
            | "sort"
            | "update"
    )
}

fn text(scan: &mut Scan, module: &Module, node: Option<&Expr>) -> Result<Option<String>> {
    node.map(|n| super::class::text(scan, n, module.text()))
        .transpose()
        .map(Option::flatten)
}

fn array<'a>(input: &'a Value, key: &str) -> Result<&'a [Value]> {
    match input.get(key) {
        None => Ok(&[]),
        Some(v) => v
            .as_array()
            .map(Vec::as_slice)
            .ok_or_else(|| format!("invalid state {key}")),
    }
}

pub(super) fn collect(module: &Module, scan: &mut Scan, input: &Value) -> Result<Value> {
    let mut nodes = Vec::new();
    scan.tick(module.tree.body.len())?;
    let mut pending: VecDeque<_> = module.tree.body.iter().map(Node::Stmt).collect();
    let mut class_nodes = HashMap::new();
    while let Some(node) = pending.pop_front() {
        scan.tick(1)?;
        pending.extend(scan.children(&node)?);
        if let Node::Stmt(Stmt::ClassDef(n)) = &node {
            let loc = module.location(&Def::Class(n).range(module.text()));
            class_nodes.insert((loc.line, loc.column), n);
        }
        nodes.push(node);
    }
    let mut symbols = HashMap::new();
    for symbol in array(input, "symbols")? {
        scan.tick(1)?;
        let data = symbol.get("data").ok_or("state symbol data unseen")?;
        if let Some(name) = data.get("qualified_name").and_then(Value::as_str) {
            symbols.insert(name, data);
        }
    }
    let mut evidence = EvidenceMap::new();
    let mut classes = Vec::new();
    for site in array(input, "symbol_sites")? {
        scan.tick(1)?;
        let name = site
            .get("qualified_name")
            .and_then(Value::as_str)
            .ok_or("state symbol name unseen")?;
        let line = site
            .get("line")
            .and_then(Value::as_i64)
            .ok_or("state symbol line unseen")?;
        let column = site
            .get("column")
            .and_then(Value::as_i64)
            .ok_or("state symbol column unseen")?;
        let Some(node) = class_nodes.get(&(line, column)) else {
            continue;
        };
        let symbol = symbols.get(name);
        let frozen = match symbol.and_then(|d| d.get("frozen_object")) {
            None | Some(Value::Null) => false,
            Some(Value::Bool(value)) => *value,
            _ => return Err("invalid state frozen flag".into()),
        };
        let protocol = symbol
            .and_then(|d| d.get("class_kind"))
            .and_then(Value::as_str)
            == Some("protocol");
        let class = classes::collect(scan, module, name, node, frozen, protocol, &mut evidence)?;
        scan.keep(&mut classes, class)?;
    }
    let owners = super::records::class_owners(scan, module)?;
    let mut functions = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(stmt @ Stmt::FunctionDef(n)) = node else {
            continue;
        };
        let class_owner = owners.get(&std::ptr::from_ref(n)).map(|n| n.as_ref());
        let qualified = scan.owner(class_owner.unwrap_or(&module.name), n.name.as_str())?;
        let mut parameters = Vec::new();
        for p in n
            .parameters
            .posonlyargs
            .iter()
            .chain(&n.parameters.args)
            .chain(&n.parameters.kwonlyargs)
        {
            scan.tick(1)?;
            let row = json!({"name": p.parameter.name.as_str(), "annotation": text(scan,module,p.parameter.annotation.as_deref())?});
            scan.keep(&mut parameters, row)?;
        }
        let events = events::collect(scan, module, stmt, &mut evidence)?;
        let row = json!({"scope": qualified.as_ref(), "module": module.name, "class_owner": class_owner,
            "receiver": n.parameters.args.first().map(|p| p.parameter.name.as_str()), "parameters": parameters, "events": events});
        scan.keep(&mut functions, row)?;
    }
    scan.tick(evidence.len())?;
    Ok(
        json!({"state": {"classes": classes, "functions": functions}, "evidence": evidence.into_values().collect::<Vec<_>>()}),
    )
}

fn attribute_path<'a>(scan: &mut Scan, expr: &'a Expr) -> Result<Option<(&'a str, Vec<&'a str>)>> {
    let mut expr = expr;
    let mut parts = Vec::new();
    while let Expr::Attribute(n) = expr {
        scan.tick(1)?;
        parts.push(n.attr.as_str());
        expr = &n.value;
    }
    let Expr::Name(n) = expr else {
        return Ok(None);
    };
    scan.tick(parts.len())?;
    parts.reverse();
    Ok(Some((n.id.as_str(), parts)))
}
