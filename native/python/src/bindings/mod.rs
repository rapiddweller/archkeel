// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Definition binding inputs before import convergence. No incomplete section enters a reply.

use std::collections::HashMap;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::Expr;
use serde_json::{json, Value};

use crate::module::Module;
use crate::parse::work::Work;
use crate::pyast::Node;

mod class;
mod closure;
mod names;
mod namespace;
mod records;
mod scan;
mod scopes;
mod statements;

use scan::{Result, Scan};

pub fn table(module: &Module, minor: PyMinor) -> Result<(Value, usize)> {
    let mut scan = Scan {
        minor,
        work: Work::new(),
    };
    let mut nodes = Vec::new();
    // A Module walk first yields all direct statements, then their children breadth first.
    let mut pending = std::collections::VecDeque::new();
    scan.tick(module.tree.body.len())?;
    pending.extend(module.tree.body.iter().map(Node::Stmt));
    while let Some(node) = pending.pop_front() {
        scan.tick(1)?;
        pending.extend(scan.children(&node)?);
        nodes.push(node);
    }
    let scope = scopes::module_scope(&mut scan, &module.tree.body)?;
    let bound = names::bound(&mut scan, &nodes)?;
    let scope_bound = names::bound(&mut scan, &scope)?;
    let mut parents = HashMap::new();
    for node in &nodes {
        scan.tick(1)?;
        for child in scan.children(node)? {
            scan.tick(1)?;
            if let Node::Expr(expr) = child {
                parents.insert(std::ptr::from_ref(expr), node.clone());
            }
        }
    }
    scan.tick(bound.len().saturating_add(nodes.len()))?;
    let env = namespace::Env {
        blocked: bound.iter().map(String::as_str).collect(),
        opaque: nodes
            .iter()
            .any(|n| names::star(n) || matches!(n, Node::TypeParam(_))),
        parents: &parents,
    };
    let mut flags = Vec::new();
    let mut own_only = Vec::new();
    let mut read_names = Vec::new();
    for node in &nodes {
        scan.tick(1)?;
        flags.push(namespace::flags(&mut scan, node)?);
        own_only.push(namespace::own_only(&mut scan, node)?);
        read_names.push(namespace::read_names(&mut scan, node, &env)?);
    }
    let rebind = [
        namespace::rebind(&mut scan, &nodes, &scope, &env, false)?,
        namespace::rebind(&mut scan, &nodes, &scope, &env, true)?,
    ];
    let definitions = records::definitions(&mut scan, module, &nodes)?;
    let (bindings, evidence) = records::unused(&mut scan, module)?;
    let mut queries = Vec::new();
    for name in ["object", "alias", "property", "x"] {
        scan.tick(1)?;
        let mut row = vec![names::may_exist(&mut scan, &module.tree.body, None, name)?];
        for stop in module
            .tree
            .body
            .first()
            .into_iter()
            .chain(module.tree.body.last())
        {
            scan.tick(1)?;
            row.push(names::once_before(
                &mut scan,
                &module.tree.body,
                stop,
                name,
            )?);
            row.push(names::may_exist(
                &mut scan,
                &module.tree.body,
                Some(stop),
                name,
            )?);
        }
        queries.push(row);
    }
    let events = names::events(&mut scan, module, &scope)?;
    let mut statement_bindings = Vec::new();
    for node in &nodes {
        scan.tick(1)?;
        if matches!(
            node,
            Node::Stmt(_) | Node::Elif(_) | Node::Expr(Expr::Named(_))
        ) {
            statement_bindings.push(statements::binding(&mut scan, node, module.text())?);
        }
    }
    let (closures, configured_closure) = closure::tables(&mut scan, &nodes, &scope_bound)?;
    let scope_kinds: Vec<_> = scope.iter().map(Node::kind).collect();
    scan.tick(scope.len())?;
    Ok((
        json!({
            "bound": bound, "scope": scope_kinds, "scope_bound": scope_bound,
            "events": events, "definitions": definitions, "queries": queries,
            "flags": flags, "own_only": own_only, "read_names": read_names, "rebind": rebind,
            "bindings": bindings, "evidence": evidence,
            "statement_bindings": statement_bindings, "closures": closures,
            "configured_closure": configured_closure,
        }),
        scan.work.used(),
    ))
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_binding_table_keeps_complete_records_and_its_work_count() {
        let text = "def f(x):\n    local = 1\n    return 2\n";
        let module = crate::module::Module::new(
            "app/probe.py".into(),
            "app.probe".into(),
            text.into(),
            crate::test_tree(text, 11).expect("fixture parses"),
        );
        let (table, work) =
            super::table(&module, crate::test_minor(11)).expect("fixture is in scope");
        assert_eq!(table["bound"], serde_json::json!(["local", "x", "f"]));
        assert_eq!(table["bindings"].as_array().expect("records").len(), 2);
        assert!(work > 0 && work < crate::parse::work::MAX_WORK);
    }
}
