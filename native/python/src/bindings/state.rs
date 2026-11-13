// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class state and ordered function traces. Symbol flags and node selections are explicit inputs.

use std::collections::HashMap;

use ruff_python_ast::Stmt;
use serde_json::{json, Value};

use super::scan::{input_array as array, Result, Scan};
use crate::module::{definition::Def, EvidenceMap, Module};
use crate::pyast::Node;

mod classes;
mod events;
mod paths;

use paths::text;

pub(super) fn collect(module: &Module, scan: &mut Scan, input: &Value) -> Result<Value> {
    let nodes = scan.module_nodes(module)?;
    let mut class_nodes = HashMap::new();
    for node in &nodes {
        scan.tick(1)?;
        if let Node::Stmt(Stmt::ClassDef(n)) = node {
            let loc = module.location(&Def::Class(n).range(module.text()));
            class_nodes.insert((loc.line, loc.column), n);
        }
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
