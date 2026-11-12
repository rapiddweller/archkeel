// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Lexical definitions and the complete unused-binding records, with their source evidence.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use archkeel_facts::identity::{stable_id, Part};
use ruff_python_ast::{Expr, ExprContext, Stmt, StmtFunctionDef};
use serde_json::{json, Value};

use super::scan::{constant, sorted, Result, Scan};
use super::{class, names, scopes};
use crate::module::{definition::Def, EvidenceMap, Module};
use crate::pyast::Node;

fn params(scan: &mut Scan, n: &StmtFunctionDef) -> Result<Vec<String>> {
    let p = &n.parameters;
    scan.tick(p.len())?;
    Ok(p.posonlyargs
        .iter()
        .chain(&p.args)
        .chain(&p.kwonlyargs)
        .map(|p| p.parameter.name.to_string())
        .chain(p.vararg.iter().chain(&p.kwarg).map(|p| p.name.to_string()))
        .collect())
}

fn class_owners(
    scan: &mut Scan,
    module: &Module,
) -> Result<HashMap<*const StmtFunctionDef, String>> {
    let mut out = HashMap::new();
    scan.tick(module.tree.body.len())?;
    let mut pending: Vec<_> = module
        .tree
        .body
        .iter()
        .map(|s| (Node::Stmt(s), None::<String>))
        .collect();
    while let Some((node, owner)) = pending.pop() {
        scan.tick(1)?;
        let owner = match &node {
            Node::Stmt(Stmt::ClassDef(n)) => Some(format!(
                "{}.{}",
                owner.as_deref().unwrap_or(&module.name),
                n.name
            )),
            Node::Stmt(Stmt::FunctionDef(n)) => {
                if let Some(owner) = &owner {
                    out.insert(std::ptr::from_ref(n), owner.clone());
                }
                owner
            }
            _ => owner,
        };
        for child in scan.children(&node)? {
            scan.tick(1)?;
            pending.push((child, owner.clone()));
        }
    }
    Ok(out)
}

pub(super) fn definitions(
    scan: &mut Scan,
    module: &Module,
    nodes: &[Node<'_>],
) -> Result<Vec<Value>> {
    let owners = class_owners(scan, module)?;
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let def = match node {
            Node::Stmt(Stmt::ClassDef(n)) => Def::Class(n),
            Node::Stmt(Stmt::FunctionDef(n)) => Def::Function(n),
            _ => continue,
        };
        let own = scopes::own(scan, def.body())?;
        let mut lexical = names::bound(scan, &own)?;
        if let Def::Function(n) = def {
            lexical.extend(params(scan, n)?);
        }
        scan.tick(own.len().saturating_add(lexical.len()))?;
        let mut item = json!({
            "name": def.name(), "line": module.location(&def.range(module.text())).line,
            "own": own.iter().map(Node::kind).collect::<Vec<_>>(), "lexical": sorted(lexical),
        });
        match def {
            Def::Class(n) => {
                let fields = class::data(scan, n, module.text())?;
                let (Some(fields), Some(item)) = (fields.as_object(), item.as_object_mut()) else {
                    return Err("class record shape unseen".into());
                };
                item.extend(fields.clone());
            }
            Def::Function(n) => {
                if let Some(item) = item.as_object_mut() {
                    item.insert(
                        "class_owner".into(),
                        json!(owners.get(&std::ptr::from_ref(n))),
                    );
                }
            }
        }
        out.push(item);
    }
    Ok(out)
}

fn loaded(scan: &mut Scan, node: &StmtFunctionDef) -> Result<BTreeSet<String>> {
    let mut out = BTreeSet::new();
    // Match ast.walk(function), including its arguments, defaults, decorators and nested scopes.
    let mut nodes = vec![Node::Arguments(Some(&node.parameters))];
    scan.tick(node.body.len().saturating_add(node.decorator_list.len()))?;
    nodes.extend(node.body.iter().map(Node::Stmt));
    nodes.extend(
        node.decorator_list
            .iter()
            .map(|d| Node::Expr(&d.expression)),
    );
    nodes.extend(node.returns.as_deref().map(Node::Expr));
    if let Some(params) = &node.type_params {
        scan.tick(params.type_params.len())?;
        nodes.extend(params.type_params.iter().map(Node::TypeParam));
    }
    for root in nodes {
        scan.tick(1)?;
        for n in scan.walk(root)? {
            scan.tick(1)?;
            match n {
                Node::Expr(Expr::Name(n)) if n.ctx != ExprContext::Store => {
                    out.insert(n.id.to_string());
                }
                Node::Stmt(Stmt::Global(n)) => {
                    scan.tick(n.names.len())?;
                    out.extend(n.names.iter().map(ToString::to_string));
                }
                Node::Stmt(Stmt::Nonlocal(n)) => {
                    scan.tick(n.names.len())?;
                    out.extend(n.names.iter().map(ToString::to_string));
                }
                _ => {}
            }
        }
    }
    Ok(out)
}

fn empty(scan: &mut Scan, n: &StmtFunctionDef) -> Result<bool> {
    scan.tick(n.body.len())?;
    Ok(n.body
        .iter()
        .all(|s| matches!(s, Stmt::Pass(_)) || matches!(s, Stmt::Expr(n) if constant(&n.value))))
}

pub(super) fn unused(
    scan: &mut Scan,
    module: &Module,
) -> Result<(Vec<Value>, Vec<archkeel_facts::envelope::Evidence>)> {
    let mut records = BTreeMap::new();
    let mut evidence = EvidenceMap::new();
    scan.tick(module.tree.body.len())?;
    let mut pending: Vec<_> = module
        .tree
        .body
        .iter()
        .rev()
        .map(|s| (Node::Stmt(s), module.name.clone(), false))
        .collect();
    while let Some((node, mut owner, mut inherits)) = pending.pop() {
        scan.tick(1)?;
        match &node {
            Node::Stmt(Stmt::ClassDef(n)) => {
                owner = format!("{owner}.{}", n.name);
                inherits = n.arguments.as_ref().is_some_and(|a| !a.args.is_empty());
            }
            Node::Stmt(Stmt::FunctionDef(n)) => {
                owner = format!("{owner}.{}", n.name);
                function(
                    scan,
                    module,
                    n,
                    (&owner, inherits),
                    &mut records,
                    &mut evidence,
                )?;
            }
            _ => {}
        }
        for child in scan.children(&node)?.into_iter().rev() {
            scan.tick(1)?;
            pending.push((child, owner.clone(), inherits));
        }
    }
    scan.tick(records.len().saturating_add(evidence.len()))?;
    Ok((
        records.into_values().collect(),
        evidence.into_values().collect(),
    ))
}

fn function(
    scan: &mut Scan,
    module: &Module,
    node: &StmtFunctionDef,
    context: (&str, bool),
    records: &mut BTreeMap<String, Value>,
    evidence: &mut EvidenceMap,
) -> Result<()> {
    let (owner, inherits) = context;
    let loaded = loaded(scan, node)?;
    let mut groups = Vec::new();
    if !inherits && node.decorator_list.is_empty() && !empty(scan, node)? {
        groups.push(("parameter", params(scan, node)?));
    }
    let own = scopes::own(scan, &node.body)?;
    scan.tick(own.len())?;
    let locals = own
        .iter()
        .filter_map(|n| match n {
            Node::Expr(Expr::Name(n)) if n.ctx == ExprContext::Store => Some(n.id.to_string()),
            _ => None,
        })
        .collect();
    groups.push(("local", locals));
    for (binding, names) in groups {
        scan.tick(1)?;
        for name in sorted(names) {
            scan.tick(1)?;
            if !name.starts_with('_')
                && !matches!(name.as_str(), "self" | "cls")
                && !loaded.contains(&name)
            {
                let range = Def::Function(node).range(module.text());
                let location = module.location(&range);
                let evidence_id = module.evidence(evidence, &range);
                let id = stable_id(
                    "BIND",
                    &[
                        Part::Text(&module.rel),
                        Part::Number(location.line),
                        Part::Number(location.column),
                        Part::Text(binding),
                        Part::Text(&name),
                    ],
                );
                let mut subjects = vec![owner, &module.name];
                subjects.sort();
                subjects.dedup();
                records.insert(id.clone(), json!({
                    "id": id, "evidence_class": "FACT", "area": "repository_topology",
                    "kind": format!("unused_{binding}"), "title": format!("{owner} never reads {name}"),
                    "subjects": subjects, "evidence_ids": [evidence_id],
                    "rule_ids": [], "fact_ids": [], "provenance": [],
                    "data": {"owner": owner, "module": module.name, "name": name, "binding": binding},
                }));
            }
        }
    }
    Ok(())
}
