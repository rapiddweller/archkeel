// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Ordered binder inventories and binding checks. A lookup never enters a function body.

use std::collections::BTreeMap;

use ruff_python_ast::{ExceptHandler, Expr, ExprContext, Pattern, Stmt};
use ruff_text_size::Ranged;
use serde_json::{json, Value};

use super::scan::{name, Result, Scan};
use super::scopes;
use crate::module::{import_bindings as imports, Module};
use crate::pyast::Node;

pub(super) fn star(node: &Node<'_>) -> bool {
    matches!(node, Node::Stmt(Stmt::ImportFrom(n)) if n.names.iter().any(|a| a.name.as_str() == "*"))
}

pub(super) fn capture<'a>(node: &Node<'a>) -> Option<&'a str> {
    match node {
        Node::Handler(ExceptHandler::ExceptHandler(n)) => n.name.as_ref().map(|n| n.as_str()),
        Node::Pattern(Pattern::MatchAs(n)) => n.name.as_ref().map(|n| n.as_str()),
        Node::Pattern(Pattern::MatchStar(n)) => n.name.as_ref().map(|n| n.as_str()),
        Node::Pattern(Pattern::MatchMapping(n)) => n.rest.as_ref().map(|n| n.as_str()),
        _ => None,
    }
}

pub(super) fn bound(scan: &mut Scan, nodes: &[Node<'_>]) -> Result<Vec<String>> {
    let mut groups: BTreeMap<u8, Vec<String>> = BTreeMap::new();
    for node in nodes {
        scan.tick(1)?;
        let (group, values) = match node {
            Node::Expr(Expr::Name(n)) if n.ctx != ExprContext::Load => (0, vec![n.id.to_string()]),
            Node::Arg(n) => (1, vec![n.name.to_string()]),
            Node::Stmt(Stmt::FunctionDef(n)) => (2, vec![n.name.to_string()]),
            Node::Stmt(Stmt::ClassDef(n)) => (2, vec![n.name.to_string()]),
            Node::Stmt(stmt @ (Stmt::Import(_) | Stmt::ImportFrom(_))) => (3, imports(stmt)),
            Node::Handler(_) => (4, capture(node).map(str::to_owned).into_iter().collect()),
            Node::Pattern(Pattern::MatchAs(_)) => {
                (5, capture(node).map(str::to_owned).into_iter().collect())
            }
            Node::Pattern(Pattern::MatchStar(_)) => {
                (6, capture(node).map(str::to_owned).into_iter().collect())
            }
            Node::Pattern(Pattern::MatchMapping(_)) => {
                (7, capture(node).map(str::to_owned).into_iter().collect())
            }
            Node::Stmt(Stmt::Global(n)) => (8, n.names.iter().map(ToString::to_string).collect()),
            Node::Stmt(Stmt::Nonlocal(n)) => (8, n.names.iter().map(ToString::to_string).collect()),
            _ => continue,
        };
        scan.tick(values.len())?;
        groups.entry(group).or_default().extend(values);
    }
    scan.tick(groups.len())?;
    Ok(groups.into_values().flatten().collect())
}

pub(super) fn stored_names(scan: &mut Scan, targets: Vec<&Expr>) -> Result<Vec<String>> {
    let mut out = Vec::new();
    for target in targets {
        scan.tick(1)?;
        for child in scan.walk(Node::Expr(target))? {
            scan.tick(1)?;
            let Node::Expr(Expr::Name(n)) = child else {
                continue;
            };
            if n.ctx == ExprContext::Store {
                out.push(n.id.to_string());
            }
        }
    }
    Ok(out)
}

pub(super) fn targets(stmt: &Stmt) -> Vec<&Expr> {
    match stmt {
        Stmt::Assign(n) => n.targets.iter().collect(),
        Stmt::AnnAssign(n) => vec![&n.target],
        Stmt::AugAssign(n) => vec![&n.target],
        _ => Vec::new(),
    }
}

pub(super) fn events(scan: &mut Scan, module: &Module, nodes: &[Node<'_>]) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let mut values = Vec::new();
        let range = match node {
            Node::Stmt(stmt) => {
                values = statement_events(scan, module, stmt)?;
                match stmt {
                    Stmt::ClassDef(n) => {
                        crate::module::definition::Def::Class(n).range(module.text())
                    }
                    Stmt::FunctionDef(n) => {
                        crate::module::definition::Def::Function(n).range(module.text())
                    }
                    _ => stmt.range(),
                }
            }
            Node::Expr(Expr::Named(n)) => {
                values = stored_names(scan, vec![&n.target])?;
                n.range
            }
            Node::Handler(n) => n.range(),
            Node::Pattern(n) => n.range(),
            _ => continue,
        };
        values.extend(capture(node).map(str::to_owned));
        let location = module.location(&range);
        for value in values {
            scan.tick(1)?;
            let item = json!([
                node.kind(),
                location.line,
                location.end_line,
                location.column,
                value
            ]);
            scan.output.value(&item)?;
            out.push(item);
        }
    }
    Ok(out)
}

fn statement_events(scan: &mut Scan, module: &Module, stmt: &Stmt) -> Result<Vec<String>> {
    match stmt {
        Stmt::AnnAssign(n) if n.value.is_none() => Ok(Vec::new()),
        Stmt::Assign(_) | Stmt::AnnAssign(_) | Stmt::AugAssign(_) => {
            stored_names(scan, targets(stmt))
        }
        Stmt::For(n) => stored_names(scan, vec![&n.target]),
        Stmt::With(n) => {
            scan.tick(n.items.len())?;
            stored_names(
                scan,
                n.items
                    .iter()
                    .filter_map(|i| i.optional_vars.as_deref())
                    .collect(),
            )
        }
        Stmt::TypeAlias(n) => Ok(match &*n.name {
            Expr::Name(n) => vec![n.id.to_string()],
            _ => Vec::new(),
        }),
        Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {
            // Direct membership is constant-time from the statement's source range.
            let direct = crate::module::direct(module, stmt);
            Ok(if direct {
                Vec::new()
            } else {
                name(&Node::Stmt(stmt))
                    .map(str::to_owned)
                    .into_iter()
                    .collect()
            })
        }
        _ => Ok(Vec::new()),
    }
}

pub(super) fn may_exist(
    scan: &mut Scan,
    body: &[Stmt],
    stop: Option<&Stmt>,
    wanted: &str,
) -> Result<bool> {
    scan.tick(body.len())?;
    let mut pending: Vec<_> = body
        .iter()
        .take_while(|stmt| !stop.is_some_and(|stop| std::ptr::eq(*stmt, stop)))
        .map(Node::Stmt)
        .collect();
    while let Some(node) = pending.pop() {
        scan.tick(1)?;
        if name(&node) == Some(wanted) || capture(&node) == Some(wanted) || star(&node) {
            return Ok(true);
        }
        match &node {
            Node::Expr(Expr::Name(n)) if n.id.as_str() == wanted && n.ctx != ExprContext::Load => {
                return Ok(true)
            }
            Node::Stmt(stmt @ (Stmt::Import(_) | Stmt::ImportFrom(_))) => {
                let values = imports(stmt);
                scan.tick(values.len())?;
                if values.iter().any(|n| n == wanted) {
                    return Ok(true);
                }
            }
            Node::Stmt(Stmt::ClassDef(_)) if declares_global(scan, node.clone(), wanted)? => {
                return Ok(true)
            }
            _ => {}
        }
        // Lookup differs from module_scope only for comprehension targets, which do bind here.
        let children = match &node {
            Node::Comprehension(_) => scan.children(&node)?,
            _ => scopes::evaluated(scan, &node)?,
        };
        pending.extend(children);
    }
    Ok(false)
}

pub(super) fn once_before(
    scan: &mut Scan,
    body: &[Stmt],
    stop: &Stmt,
    wanted: &str,
) -> Result<bool> {
    let mut count: usize = 0;
    for stmt in body {
        scan.tick(1)?;
        if std::ptr::eq(stmt, stop) {
            return Ok(count == 1);
        }
        if star(&Node::Stmt(stmt)) {
            return Ok(false);
        }
        let values = match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => name(&Node::Stmt(stmt))
                .map(str::to_owned)
                .into_iter()
                .collect(),
            Stmt::Import(_) | Stmt::ImportFrom(_) => imports(stmt),
            Stmt::Assign(_) | Stmt::AnnAssign(_) => stored_names(scan, targets(stmt))?,
            _ => {
                if stores_name(scan, stmt, wanted)? {
                    return Ok(false);
                }
                continue;
            }
        };
        scan.tick(values.len())?;
        count = count.saturating_add(values.iter().filter(|n| n.as_str() == wanted).count());
        if count > 1 {
            return Ok(false);
        }
    }
    Ok(false)
}

fn declares_global(scan: &mut Scan, node: Node<'_>, wanted: &str) -> Result<bool> {
    for child in scan.walk(node)? {
        scan.tick(1)?;
        if let Node::Stmt(Stmt::Global(n)) = child {
            scan.tick(n.names.len())?;
            if n.names.iter().any(|n| n.as_str() == wanted) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn stores_name(scan: &mut Scan, stmt: &Stmt, wanted: &str) -> Result<bool> {
    for child in scan.walk(Node::Stmt(stmt))? {
        scan.tick(1)?;
        if matches!(child, Node::Expr(Expr::Name(n)) if n.id.as_str() == wanted && n.ctx != ExprContext::Load)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(super) fn ordered_checks(scan: &mut Scan, body: &[Stmt]) -> Result<Vec<Vec<bool>>> {
    let mut queries = Vec::new();
    for name in ["object", "alias", "property", "x"] {
        scan.tick(1)?;
        let mut row = vec![may_exist(scan, body, None, name)?];
        for stop in body.first().into_iter().chain(body.last()) {
            scan.tick(1)?;
            row.push(once_before(scan, body, stop, name)?);
            row.push(may_exist(scan, body, Some(stop), name)?);
        }
        queries.push(row);
    }
    Ok(queries)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_global_declaration_step_is_charged_beside_the_walk() {
        let tree =
            crate::test_tree("class C:\n    def f():\n        global x\n", 11).expect("fixture");
        let node = Node::Stmt(tree.body.first().expect("class"));
        let minor = crate::test_minor(11);
        let visits = crate::pyast::walk(node.clone(), minor).count();
        let mut scan = Scan::new(minor);
        let before = scan.work.used();
        assert!(!declares_global(&mut scan, node, "missing").expect("in scope"));
        assert_eq!(scan.work.used() - before, visits * 2 + 1);
    }
}
