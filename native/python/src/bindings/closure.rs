// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Linear propagation of changed member bindings through assignment aliases.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, Stmt};

use super::names;
use super::scan::{sorted, Result, Scan};
use crate::pyast::Node;

pub(super) struct Inputs<'a> {
    pub roots: &'a [&'a str],
    pub members: bool,
    pub contained: &'a [(&'a str, &'a str)],
    pub local_references: &'a HashSet<*const Expr>,
    pub namespace_owners: &'a [&'a str],
    pub namespace_bindings: &'a [String],
}

pub(super) fn closure(
    scan: &mut Scan,
    nodes: &[Node<'_>],
    input: &Inputs<'_>,
) -> Result<Vec<String>> {
    if input.roots.is_empty() {
        return Ok(Vec::new());
    }
    let mut edges: HashMap<String, HashSet<String>> = HashMap::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(stmt) = node else {
            continue;
        };
        let value = match stmt {
            Stmt::Assign(n) => &*n.value,
            Stmt::AnnAssign(n) => match n.value.as_deref() {
                Some(n) => n,
                None => continue,
            },
            _ => continue,
        };
        if !matches!(value, Expr::Name(_))
            && !(input.members && matches!(value, Expr::Attribute(_)))
        {
            continue;
        }
        for target in names::targets(stmt) {
            scan.tick(1)?;
            if input.local_references.contains(&std::ptr::from_ref(target)) {
                continue;
            }
            let Expr::Name(target) = target else {
                continue;
            };
            connect(
                scan,
                &mut edges,
                target.id.as_str(),
                value,
                input.local_references,
            )?;
        }
    }
    for (owner, value) in input.contained {
        scan.tick(1)?;
        edges
            .entry((*owner).to_owned())
            .or_default()
            .insert((*value).to_owned());
    }
    scan.tick(
        input
            .roots
            .len()
            .saturating_add(input.namespace_owners.len()),
    )?;
    let namespace_owners: HashSet<_> = input.namespace_owners.iter().copied().collect();
    let mut changed: HashSet<_> = input.roots.iter().map(|n| (*n).to_owned()).collect();
    let mut pending: Vec<_> = changed.iter().cloned().collect();
    let mut expanded = false;
    while let Some(current) = pending.pop() {
        scan.tick(1)?;
        if !expanded && namespace_owners.contains(current.as_str()) {
            expanded = true;
            expand(scan, input.namespace_bindings, &mut changed, &mut pending)?;
        }
        let Some(values) = edges.get(&current) else {
            continue;
        };
        for value in values {
            scan.tick(1)?;
            if changed.insert(value.clone()) {
                pending.push(value.clone());
            }
        }
    }
    scan.tick(changed.len())?;
    Ok(sorted(changed))
}

fn connect(
    scan: &mut Scan,
    edges: &mut HashMap<String, HashSet<String>>,
    target: &str,
    value: &Expr,
    local: &HashSet<*const Expr>,
) -> Result<()> {
    for value in scan.walk(Node::Expr(value))? {
        scan.tick(1)?;
        if value
            .expr()
            .is_some_and(|e| local.contains(&std::ptr::from_ref(e)))
        {
            continue;
        }
        let Node::Expr(Expr::Name(value)) = value else {
            continue;
        };
        edges
            .entry(target.to_owned())
            .or_default()
            .insert(value.id.to_string());
        edges
            .entry(value.id.to_string())
            .or_default()
            .insert(target.to_owned());
    }
    Ok(())
}

fn expand(
    scan: &mut Scan,
    values: &[String],
    changed: &mut HashSet<String>,
    pending: &mut Vec<String>,
) -> Result<()> {
    for value in values {
        scan.tick(1)?;
        if changed.insert(value.clone()) {
            pending.push(value.clone());
        }
    }
    Ok(())
}

pub(super) fn tables(
    scan: &mut Scan,
    nodes: &[Node<'_>],
    scope_bound: &[String],
) -> Result<(Vec<Vec<String>>, Vec<String>)> {
    let mut closures = Vec::new();
    for member in [false, true] {
        for root in ["alias", "object", "x"] {
            scan.tick(1)?;
            closures.push(closure(
                scan,
                nodes,
                &Inputs {
                    roots: &[root],
                    members: member,
                    contained: &[],
                    local_references: &HashSet::new(),
                    namespace_owners: &[],
                    namespace_bindings: &[],
                },
            )?);
        }
    }
    scan.tick(nodes.len())?;
    let local_references = nodes
        .iter()
        .filter_map(|n| match n {
            Node::Expr(e @ Expr::Name(n)) if n.id.as_str() == "local" => {
                Some(std::ptr::from_ref(*e))
            }
            _ => None,
        })
        .collect();
    let configured = closure(
        scan,
        nodes,
        &Inputs {
            roots: &["x"],
            members: true,
            contained: &[("x", "alias")],
            local_references: &local_references,
            namespace_owners: &["alias"],
            namespace_bindings: scope_bound,
        },
    )?;
    Ok((closures, configured))
}
