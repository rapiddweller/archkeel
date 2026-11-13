// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Import-local proofs, before cross-module member convergence (AD-404).

use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{Expr, ExprContext, Stmt};
use serde_json::{json, Value};

use super::environment::Env;
use super::scan::{counts, name, Result, Scan, Table};
use super::{closure, names, namespace, scopes};
use crate::module::Module;
use crate::pyast::Node;

mod classes;
mod methods;
mod protection;
mod types;

#[cfg(feature = "dump")]
pub fn protection_table(module: &Module, minor: PyMinor) -> Table {
    super::scan::table(module, minor, |module, scan| {
        let (env, nodes, _) = prepare(module, scan)?;
        protection::collect(scan, &env, &nodes)
    })
}

pub fn table(module: &Module, minor: PyMinor) -> Table {
    super::scan::table(module, minor, collect)
}

fn collect(module: &Module, scan: &mut Scan) -> Result<Value> {
    let (env, nodes, stable_without_imports) = prepare(module, scan)?;
    let (methods, classes) = definitions(scan, &env, &nodes)?;
    let types = types::table(scan, &env, &nodes)?;
    Ok(
        json!({"stable": env.stable, "stable_without_imports":stable_without_imports,
        "unique": env.unique, "methods": methods, "classes": classes, "types": types}),
    )
}

fn prepare<'a>(
    module: &'a Module,
    scan: &mut Scan,
) -> Result<(Env<'a>, Vec<Node<'a>>, BTreeSet<String>)> {
    scan.tick(module.tree.body.len())?;
    let mut pending: VecDeque<_> = module.tree.body.iter().map(Node::Stmt).collect();
    let mut nodes = Vec::new();
    while let Some(node) = pending.pop_front() {
        scan.tick(1)?;
        pending.extend(scan.children(&node)?);
        nodes.push(node);
    }
    let scope = scopes::module_scope(scan, &module.tree.body)?;
    aliases(scan, module, &scope)?;
    let stable_without_imports = stable(scan, module, &nodes, &scope, false)?;
    let stable = stable(scan, module, &nodes, &scope, true)?;
    let bound_values = names::bound(scan, &nodes)?;
    let bound_counts = counts(scan, bound_values)?;
    let mut opaque = false;
    for node in &nodes {
        scan.tick(1)?;
        opaque |= names::star(node) || matches!(node, Node::TypeParam(_));
    }
    let mut unique = BTreeSet::new();
    for stmt in &module.tree.body {
        scan.tick(1)?;
        let mut direct = crate::module::import_bindings(stmt);
        direct.extend(name(&Node::Stmt(stmt)).map(str::to_owned));
        for name in direct {
            scan.tick(1)?;
            if !opaque && bound_counts.get(&name) == Some(&1) {
                unique.insert(name);
            }
        }
    }
    scan.tick(bound_counts.len())?;
    let env = Env {
        module,
        stable,
        unique,
        bound: bound_counts.into_keys().collect(),
        opaque,
    };
    Ok((env, nodes, stable_without_imports))
}

fn definitions(
    scan: &mut Scan,
    env: &Env<'_>,
    nodes: &[Node<'_>],
) -> Result<(Vec<Value>, Vec<Value>)> {
    let mut methods = Vec::new();
    let mut classes = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(stmt) = node else {
            continue;
        };
        methods::append(scan, env, stmt, &mut methods)?;
        if let Stmt::ClassDef(class) = stmt {
            let row = self::classes::row(scan, env, stmt, class)?;
            scan.keep(&mut classes, row)?;
        }
    }
    Ok((methods, classes))
}

fn aliases(scan: &mut Scan, module: &Module, scope: &[Node<'_>]) -> Result<()> {
    for node in scope {
        scan.tick(1)?;
        let (items, from, level, head) = match node {
            Node::Stmt(Stmt::Import(n)) => (&n.names, false, 0, ""),
            Node::Stmt(Stmt::ImportFrom(n)) => (
                &n.names,
                true,
                n.level,
                n.module.as_ref().map_or("", |n| n.as_str()),
            ),
            _ => continue,
        };
        let mut anchor = head.to_owned();
        if from && level > 0 {
            let mut base = if module.is_init() {
                module.name.as_str()
            } else {
                module.name.rsplit_once('.').map_or("", |(p, _)| p)
            };
            for _ in 1..level {
                scan.tick(1)?;
                base = base.rsplit_once('.').map_or("", |(p, _)| p);
            }
            anchor = if base.is_empty() {
                scan.tick(level as usize)?;
                format!(
                    "<unresolved:{}{head}:ImportError>",
                    ".".repeat(level as usize)
                )
            } else if head.is_empty() {
                base.to_owned()
            } else {
                format!("{base}.{head}")
            };
        }
        for alias in items {
            scan.tick(1)?;
            let imported = alias.name.as_str();
            if imported == "*" {
                continue;
            }
            let root = crate::module::first_part(imported);
            let binding = alias
                .asname
                .as_ref()
                .map_or(if from { imported } else { root }, |n| n.as_str());
            let target = if from {
                format!("{anchor}.{imported}")
            } else if alias.asname.is_some() {
                imported.to_owned()
            } else {
                root.to_owned()
            };
            scan.tick(binding.len().saturating_add(target.len()))?;
            let module_binding = !from || target == module.name;
            scan.aliases
                .insert(binding.to_owned(), (target, module_binding));
        }
    }
    Ok(())
}

fn stable(
    scan: &mut Scan,
    module: &Module,
    nodes: &[Node<'_>],
    scope: &[Node<'_>],
    imports: bool,
) -> Result<BTreeSet<String>> {
    let bound = names::bound(scan, nodes)?;
    let mut parents = HashMap::new();
    let mut globals = HashSet::new();
    let mut opaque = false;
    for node in nodes {
        scan.tick(1)?;
        opaque |= names::star(node) || matches!(node, Node::TypeParam(_));
        if let Node::Stmt(Stmt::Global(n)) = node {
            scan.tick(n.names.len())?;
            globals.extend(n.names.iter().map(|n| n.as_str()));
        }
        for child in scan.children(node)? {
            scan.tick(1)?;
            if let Node::Expr(expr) = child {
                parents.insert(std::ptr::from_ref(expr), node.clone());
            }
        }
    }
    scan.tick(bound.len())?;
    let env = namespace::Env {
        blocked: bound.iter().map(String::as_str).collect(),
        opaque,
        parents: &parents,
    };
    if namespace::rebind(scan, nodes, scope, &env, imports)? {
        return Ok(BTreeSet::new());
    }
    for node in scope {
        scan.tick(1)?;
        if names::star(node) {
            return Ok(BTreeSet::new());
        }
    }
    let scope_values = names::bound(scan, scope)?;
    let scope_counts = counts(scan, scope_values)?;
    let mut direct = Vec::new();
    for stmt in &module.tree.body {
        scan.tick(1)?;
        if let Some(name) = name(&Node::Stmt(stmt)) {
            direct.push(name.to_owned());
        }
        match stmt {
            Stmt::TypeAlias(n)
                if n.type_params
                    .as_ref()
                    .is_none_or(|p| p.type_params.is_empty()) =>
            {
                if let Expr::Name(n) = &*n.name {
                    direct.push(n.id.to_string());
                }
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                let bindings = crate::module::import_bindings(stmt);
                scan.tick(bindings.len())?;
                direct.extend(bindings);
            }
            Stmt::Assign(_) | Stmt::AnnAssign(_) => {
                for target in names::targets(stmt) {
                    scan.tick(1)?;
                    let target_nodes = scan.walk(Node::Expr(target))?;
                    direct.extend(names::bound(scan, &target_nodes)?);
                }
            }
            _ => {}
        }
    }
    let direct = counts(scan, direct)?;
    let changed = changed(scan, nodes)?;
    let mut out = BTreeSet::new();
    for (name, count) in direct {
        scan.tick(1)?;
        if count == 1
            && scope_counts.get(&name) == Some(&1)
            && !globals.contains(name.as_str())
            && !changed.contains(&name)
        {
            out.insert(name);
        }
    }
    Ok(out)
}

fn changed(scan: &mut Scan, nodes: &[Node<'_>]) -> Result<BTreeSet<String>> {
    let mut roots = HashSet::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Expr(Expr::Attribute(n)) = node else {
            continue;
        };
        if n.ctx == ExprContext::Load {
            continue;
        }
        let mut pending = vec![Node::Expr(&n.value)];
        while let Some(node) = pending.pop() {
            scan.tick(1)?;
            match node {
                Node::Expr(Expr::Name(n)) => {
                    roots.insert(n.id.to_string());
                }
                _ => pending.extend(names::escape_children(scan, &node)?),
            }
        }
    }
    scan.tick(roots.len())?;
    let refs: Vec<_> = roots.iter().map(String::as_str).collect();
    let changed = closure::closure(
        scan,
        nodes,
        &closure::Inputs {
            roots: &refs,
            members: false,
            contained: &[],
            local_references: &HashSet::new(),
            namespace_owners: &[],
            namespace_bindings: &[],
        },
    )?;
    scan.tick(changed.len())?;
    let mut changed: BTreeSet<_> = changed.into_iter().collect();
    super::environment::propagate_origins(scan, nodes, &mut changed)?;
    Ok(changed)
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_proof_adapter_returns_a_complete_table() {
        let module = crate::test_module("class C: pass\n", 11);
        let table = super::table(&module, crate::test_minor(11));
        assert!(table.data.is_ok());
        assert!(table.work > 0);
    }

    #[test]
    fn an_exhausted_scan_keeps_no_partial_proof_table() {
        let text = "class C:\n    @staticmethod\n    def f(): pass\n";
        let module = crate::test_module(text, 11);
        let mut scan = super::Scan::new(crate::test_minor(11));
        scan.work = crate::parse::work::Work::with_limit(1);
        assert_eq!(
            super::collect(&module, &mut scan),
            Err("binding work limit exceeded".into())
        );
        assert_eq!(scan.work.used(), 1);
    }
}
