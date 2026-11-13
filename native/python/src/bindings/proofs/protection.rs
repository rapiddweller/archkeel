// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Provider and type protections at the import-local, pre-candidate boundary (AD-410).

use std::collections::{BTreeSet, HashSet};
use ruff_python_ast::{Expr, Operator, Stmt};
use serde_json::{json, Value};
use super::super::environment::Env;
use super::super::scan::{Result, Scan};
use crate::pyast::Node;

mod constructors;
mod containment;
mod escape;
mod overloads;
mod owner_refs;
mod provider;
mod type_refs;

fn quoted(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Expr(expr @ Expr::StringLiteral(n)) = node else { continue };
        let text = n.value.to_str();
        scan.tick(text.len().saturating_mul(2))?;
        let value = if let Some(expr) = crate::parse::quoted_expression(text.trim(), scan.minor) {
            let mut admitted = true;
            for node in scan.walk(Node::Expr(&expr))? {
                scan.tick(1)?;
                if !matches!(node, Node::Expr(Expr::Name(_) | Expr::NoneLiteral(_)) | Node::Expr(Expr::BinOp(ruff_python_ast::ExprBinOp {op: Operator::BitOr, ..})) | Node::Leaf("Load" | "BitOr")) { admitted = false; break; }
            }
            if admitted { super::super::class::text(scan, &expr, text)? } else { None }
        } else { None };
        let at = env.module.location(*expr);
        scan.keep(&mut out, json!([at.line, at.end_line, at.column, value]))?;
    }
    Ok(out)
}

pub(super) fn collect(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<Value> {
    let unsafe_names = HashSet::from([env.module.name.clone()]);
    let locals = escape::locals(scan, env, nodes)?;
    // Explicit escapes do not use creation uncertainty. Generic declarations cannot be native factories.
    let raw = escape::roots(scan, env, nodes, true, false, &HashSet::new(), &env.bound, &locals)?;
    let explicit = containment::close(scan, nodes, &raw, &BTreeSet::new(), &locals, &BTreeSet::new(), &[])?;
    scan.tick(explicit.len())?;
    let escaped: HashSet<_> = explicit.iter().cloned().collect();
    let owners = containment::owners(scan, env, nodes)?;
    let pairs = containment::pairs(scan, &owners, nodes)?;
    let mut owner_rows = Vec::new();
    for (name, node) in &owners {
        scan.tick(1)?;
        let (line, end_line, column) = match node {
            Node::Stmt(Stmt::ClassDef(n)) => { let at = env.module.location(&crate::module::definition::Def::Class(n).range(env.module.text())); (at.line, at.end_line, at.column) },
            Node::Stmt(Stmt::FunctionDef(n)) => { let at = env.module.location(&crate::module::definition::Def::Function(n).range(env.module.text())); (at.line, at.end_line, at.column) },
            Node::Stmt(n) => { let at = env.module.location(*n); (at.line, at.end_line, at.column) },
            Node::Expr(n) => { let at = env.module.location(*n); (at.line, at.end_line, at.column) },
            _ => (1, 1, 0),
        };
        scan.keep(&mut owner_rows, json!([name, line, end_line, column]))?;
    }
    let mut classes = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        if let Node::Stmt(stmt @ Stmt::ClassDef(n)) = node {
            let mut generic = Vec::new();
            for base in n.bases() { scan.tick(1)?; generic.push(provider::generic(scan, env, base, stmt, &unsafe_names, &escaped, &mut HashSet::new(), 0)?); }
            let at = env.module.location(&crate::module::definition::Def::Class(n).range(env.module.text()));
            let row = json!([at.line, {
                "typed_header":provider::typed(scan, env, stmt, &unsafe_names, &escaped)?,
                "base_operands":provider::bases(scan, env, n)?,
                "creation":[provider::creation(scan, env, stmt, false, &unsafe_names, &escaped)?, provider::creation(scan, env, stmt, true, &unsafe_names, &escaped)?],
                "dataclass":provider::dataclass(scan, env, stmt, &unsafe_names)?,
                "native":provider::native(scan, env, stmt, &unsafe_names, &escaped)?, "generic":generic,
            }]);
            scan.keep(&mut classes, row)?;
        }
    }
    let mut modes = Vec::new();
    for owner in [false, true] {
        let namespace_owners = containment::namespace_owners(scan, env, &owners, owner, &unsafe_names, &escaped)?;
        let protected = escape::protected(scan, env, nodes, owner, &unsafe_names, &escaped)?;
        let references = escape::references(scan, nodes, owner, &protected, &locals)?;
        let mut sites = Vec::new();
        for node in references { scan.tick(1)?; let at = env.module.location(node); sites.push((at.line, at.end_line, at.column)); }
        sites.sort_unstable();
        let roots = escape::roots(scan, env, nodes, owner, true, &unsafe_names, &escaped, &locals)?;
        let unproven = containment::unproven(scan, env, nodes, &roots, &pairs, &locals, &namespace_owners)?;
        let row = json!({"contained":pairs, "namespace_owners":namespace_owners, "unproven":unproven, "protected":type_refs::sites(scan, env, nodes, &protected)?, "escapes":sites});
        scan.keep(&mut modes, row)?;
    }
    let annotations = type_refs::annotations(scan, nodes)?;
    let references = type_refs::references(scan, env, &annotations)?;
    let mut typed_providers = Vec::new();
    let bound = super::super::names::bound(scan, nodes)?;
    let mut provider_names = HashSet::new();
    for stmt in &env.module.tree.body {
        scan.tick(1)?;
        let Stmt::ClassDef(n) = stmt else { continue };
        if n.bases().len() != 1 || !provider::typed(scan, env, stmt, &unsafe_names, &escaped)? || !provider::native(scan, env, stmt, &unsafe_names, &escaped)? { continue; }
        let Some(base) = n.bases().first() else { continue };
        for node in scan.walk(Node::Expr(base))? {
            scan.tick(1)?;
            if let Node::Expr(Expr::Name(n)) = node { provider_names.insert(n.id.as_str()); }
        }
    }
    for binding in bound { scan.tick(1)?; if provider_names.contains(binding.as_str()) { typed_providers.push(binding); } }
    typed_providers.sort_unstable();
    Ok(json!({
        "overloads":overloads::collect(scan, env, nodes, &escaped)?, "explicit":explicit,
        "classes":classes, "owners":owner_rows, "static_containment":pairs, "modes":modes,
        "types":type_refs::sites(scan, env, nodes, &references)?,
        "class_values":constructors::class_values(scan, env)?, "constructors":constructors::candidates(scan, env)?,
        "typed_providers":typed_providers, "quoted":quoted(scan, env, nodes)?,
    }))
}

#[cfg(test)]
mod tests {
    #[test]
    fn protection_admits_a_native_typed_dict() {
        let module = crate::test_module("from typing import TypedDict\nclass C(TypedDict):\n x: int\n", 11);
        let mut scan = super::Scan::new(crate::test_minor(11));
        let (env, nodes, _) = super::super::prepare(&module, &mut scan).expect("inputs");
        let found = super::collect(&mut scan, &env, &nodes).expect("proofs");
        assert_eq!(found["classes"][0][1]["typed_header"], true);
    }
}
