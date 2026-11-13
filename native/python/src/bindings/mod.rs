// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Definition binding inputs before import convergence. No incomplete section enters a reply.

use std::collections::HashMap;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::Expr;
use serde_json::{json, Value};

use crate::module::Module;
use crate::pyast::Node;

mod class;
mod closure;
mod environment;
mod lexical;
mod names;
mod namespace;
mod output;
mod proofs;
mod records;
mod scan;
mod scopes;
mod state;
mod statements;
mod typing;
mod values;

#[cfg(feature = "dump")]
pub use output::check as check_output;
#[cfg(feature = "dump")]
pub use proofs::table as proof_table;
pub use scan::Table;
use scan::{Result, Scan};

pub enum FactBoundary {
    Lexical,
    Typing,
    State,
}

pub fn source_fact_table(
    module: &Module,
    minor: PyMinor,
    boundary: FactBoundary,
    input: &Value,
) -> Table {
    scan::table(module, minor, |module, scan| {
        if let Some(limit) = input.get("work_limit") {
            let limit = limit
                .as_u64()
                .and_then(|n| usize::try_from(n).ok())
                .ok_or("invalid fact work limit")?;
            scan.work = crate::parse::work::Work::with_limit(limit.min(scan::MAX_BINDING_WORK));
        }
        match boundary {
            FactBoundary::Lexical => lexical::collect(module, scan, input),
            FactBoundary::Typing => typing::collect(module, scan, input),
            FactBoundary::State => state::collect(module, scan, input),
        }
    })
}

pub fn table(module: &Module, minor: PyMinor) -> Table {
    scan::table(module, minor, collect)
}

fn collect(module: &Module, scan: &mut Scan) -> Result<Value> {
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
    let scope = scopes::module_scope(scan, &module.tree.body)?;
    let bound = names::bound(scan, &nodes)?;
    let scope_bound = names::bound(scan, &scope)?;
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
        flags.push(namespace::flags(scan, node)?);
        own_only.push(namespace::own_only(scan, node)?);
        read_names.push(namespace::read_names(scan, node, &env)?);
    }
    let rebind = [
        namespace::rebind(scan, &nodes, &scope, &env, false)?,
        namespace::rebind(scan, &nodes, &scope, &env, true)?,
    ];
    let definitions = records::definitions(scan, module, &nodes)?;
    let (bindings, evidence) = records::unused(scan, module)?;
    let queries = names::ordered_checks(scan, &module.tree.body)?;
    let events = names::events(scan, module, &scope)?;
    let mut statement_bindings = Vec::new();
    for node in &nodes {
        scan.tick(1)?;
        if matches!(
            node,
            Node::Stmt(_) | Node::Elif(_) | Node::Expr(Expr::Named(_))
        ) {
            let item = statements::binding(scan, node, module.text())?;
            scan.output.value(&item)?;
            statement_bindings.push(item);
        }
    }
    let (closures, configured_closure) = closure::tables(scan, &nodes, &scope_bound)?;
    let scope_kinds: Vec<_> = scope.iter().map(Node::kind).collect();
    scan.tick(scope.len())?;
    Ok(json!({
        "bound": bound, "scope": scope_kinds, "scope_bound": scope_bound,
        "events": events, "definitions": definitions, "queries": queries,
        "flags": flags, "own_only": own_only, "read_names": read_names, "rebind": rebind,
        "bindings": bindings, "evidence": evidence,
        "statement_bindings": statement_bindings, "closures": closures,
        "configured_closure": configured_closure,
    }))
}

#[cfg(test)]
mod tests {
    #[test]
    fn source_fact_work_bounds_are_inclusive_and_keep_no_partial_data() {
        use super::FactBoundary;
        let module = crate::test_module("def f(a: Any):\n return a.x\n", 11);
        for boundary in [
            FactBoundary::Lexical,
            FactBoundary::Typing,
            FactBoundary::State,
        ] {
            let table = super::source_fact_table(
                &module,
                crate::test_minor(11),
                boundary,
                &serde_json::json!({}),
            );
            assert!(table.data.is_ok());
            assert!(table.work > 0);
        }
        let table = super::source_fact_table(
            &module,
            crate::test_minor(11),
            FactBoundary::Typing,
            &serde_json::json!({"work_limit": 0}),
        );
        assert!(table.data.is_err());
        assert_eq!(table.work, 0);
    }
    #[test]
    fn the_binding_table_keeps_complete_records_and_its_work_count() {
        let text = "def f(x):\n    local = 1\n    return 2\n";
        let module = crate::test_module(text, 11);
        let result = super::table(&module, crate::test_minor(11));
        let table = result.data.expect("fixture is in scope");
        assert_eq!(table["bound"], serde_json::json!(["local", "x", "f"]));
        assert_eq!(table["bindings"].as_array().expect("records").len(), 2);
        assert!(result.work > 0 && result.work < super::scan::MAX_BINDING_WORK);
    }
}
