// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class-body proofs at the empty-provider boundary of import convergence.

use super::super::scan::{Result, Scan};
use super::super::{class, names, namespace, scopes, statements};
use super::{methods, values, Env};
use crate::pyast::Node;
use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

fn exposed(scan: &mut Scan, class: &StmtClassDef) -> Result<bool> {
    for node in scopes::module_scope(scan, &class.body)? {
        scan.tick(1)?;
        if namespace::exposes(scan, &node, true, false, true)? {
            return Ok(true);
        }
    }
    Ok(false)
}

fn unproven(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt, inert: bool) -> Result<bool> {
    let Stmt::ClassDef(n) = stmt else {
        return Err("class proof needs a class".into());
    };
    for expression in class::expressions(scan, n)? {
        scan.tick(1)?;
        for node in scan.walk(expression)? {
            scan.tick(1)?;
            if matches!(node, Node::Expr(Expr::Named(_)))
                && !(inert
                    && values::inert(scan, node.expr().ok_or("named expression unseen")?, 0)?)
                || namespace::exposes(scan, &node, true, false, true)?
            {
                return Ok(true);
            }
        }
    }
    for child in &n.body {
        scan.tick(1)?;
        if matches!(
            child,
            Stmt::If(_)
                | Stmt::For(_)
                | Stmt::While(_)
                | Stmt::With(_)
                | Stmt::Try(_)
                | Stmt::Match(_)
        ) {
            return Ok(true);
        }
    }
    let properties = methods::properties(scan, env, stmt)?;
    let mut bindings: HashMap<String, (usize, usize, usize, bool, bool)> = HashMap::new();
    let mut property_counts: HashMap<&str, usize> = HashMap::new();
    for child in &n.body {
        scan.tick(1)?;
        if let Stmt::FunctionDef(f) = child {
            if properties.contains_key(&std::ptr::from_ref(f)) {
                *property_counts.entry(f.name.as_str()).or_default() += 1;
            }
            if matches!(f.name.as_str(), "__init_subclass__" | "__class_getitem__")
                || !properties.contains_key(&std::ptr::from_ref(f))
                    && !methods::signature(scan, env, child, Some(stmt))?.1
            {
                return Ok(true);
            }
        }
        if named_effect(scan, child, inert)? {
            return Ok(true);
        }
        let admitted =
            statements::binding_with(scan, &Node::Stmt(child), env.module.text(), inert, true)?;
        if admitted.is_null() {
            return Ok(true);
        }
        let bound = admitted
            .get(0)
            .and_then(Value::as_array)
            .ok_or("class binding names unseen")?;
        let function = admitted
            .get(1)
            .and_then(Value::as_bool)
            .ok_or("class binding kind unseen")?;
        let overload = admitted
            .get(2)
            .and_then(Value::as_bool)
            .ok_or("class overload flag unseen")?;
        for name in bound {
            scan.tick(1)?;
            let name = name.as_str().ok_or("class binding name unseen")?;
            if name == "__slots__" {
                return Ok(true);
            }
            let value = bindings
                .entry(name.to_owned())
                .or_insert((0, 0, 0, false, true));
            value.0 += 1;
            value.1 += usize::from(overload);
            value.2 += usize::from(!overload);
            value.3 = overload;
            value.4 &= function;
        }
    }
    for (name, (count, overloads, implementations, last_overload, functions)) in bindings {
        scan.tick(1)?;
        if count > 1
            && property_counts.get(name.as_str()) != Some(&count)
            && !(functions && overloads == count - 1 && implementations == 1 && !last_overload)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn named_effect(scan: &mut Scan, child: &Stmt, inert: bool) -> Result<bool> {
    let value = match child {
        Stmt::Assign(n) => Some(&*n.value),
        Stmt::AnnAssign(n) => n.value.as_deref(),
        _ => None,
    };
    let Some(value) = value else {
        return Ok(false);
    };
    for item in scan.walk(Node::Expr(value))? {
        scan.tick(1)?;
        if let Node::Expr(item @ Expr::Named(_)) = item {
            if !(inert && values::inert(scan, item, 0)?) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn assignment_receives(scan: &mut Scan, env: &Env<'_>, node: &Node<'_>) -> Result<bool> {
    let (targets, value) = match node {
        Node::Stmt(Stmt::Assign(n)) => (n.targets.iter().collect::<Vec<_>>(), Some(&*n.value)),
        Node::Stmt(Stmt::AnnAssign(n)) => (vec![&*n.target], n.value.as_deref()),
        Node::Expr(Expr::Named(n)) => (vec![&*n.target], Some(&*n.value)),
        _ => (Vec::new(), None),
    };
    let Some(value) = value else {
        return Ok(matches!(node, Node::Stmt(_))
            && statements::binding(scan, node, env.module.text())?.is_null());
    };
    scan.tick(targets.len())?;
    if !targets.iter().all(|n| matches!(n, Expr::Name(_))) {
        return Ok(!values::inert(scan, value, 0)?);
    }
    Ok(statements::binding_with(scan, node, env.module.text(), true, false)?.is_null())
}

fn receives(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt) -> Result<bool> {
    let Stmt::ClassDef(class) = stmt else {
        return Err("class owner proof needs a class".into());
    };
    if exposed(scan, class)? {
        return Ok(true);
    }
    let properties = methods::properties(scan, env, stmt)?;
    for node in scopes::module_scope(scan, &class.body)? {
        scan.tick(1)?;
        match &node {
            Node::Stmt(child @ Stmt::FunctionDef(n)) => {
                if !methods::signature(scan, env, child, Some(stmt))?.1
                    && !properties.contains_key(&std::ptr::from_ref(n))
                {
                    return Ok(true);
                }
            }
            Node::Stmt(Stmt::ClassDef(n)) => {
                if !n.decorator_list.is_empty()
                    || n.arguments
                        .as_ref()
                        .is_some_and(|a| !a.keywords.is_empty() || !a.args.is_empty())
                {
                    return Ok(true);
                }
            }
            Node::Stmt(Stmt::Import(_) | Stmt::ImportFrom(_)) => return Ok(true),
            _ => {
                if assignment_receives(scan, env, &node)? {
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}

fn namespace_static(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt) -> Result<bool> {
    if receives(scan, env, stmt)? {
        return Ok(false);
    }
    let Stmt::ClassDef(class) = stmt else {
        return Err("class namespace proof needs a class".into());
    };
    let nodes = scopes::module_scope(scan, &class.body)?;
    let mut annotations = HashSet::new();
    for node in &nodes {
        scan.tick(1)?;
        if let Node::Stmt(Stmt::AnnAssign(n)) = node {
            if n.value.is_none() && matches!(&*n.target, Expr::Name(_)) {
                annotations.insert(std::ptr::from_ref(&*n.target));
            }
        }
    }
    scan.tick(nodes.len())?;
    let nodes: Vec<_> = nodes
        .into_iter()
        .filter(|n| {
            !n.expr()
                .is_some_and(|n| annotations.contains(&std::ptr::from_ref(n)))
        })
        .collect();
    let bound = names::bound(scan, &nodes)?;
    scan.tick(bound.len())?;
    Ok(!bound.iter().any(|n| n == "__module__"))
}

fn native_method(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt) -> Result<bool> {
    let Stmt::FunctionDef(n) = stmt else {
        return Err("native method proof needs a function".into());
    };
    if !methods::signature(scan, env, stmt, None)?.1 {
        return Ok(false);
    }
    for parameter in n
        .parameters
        .posonlyargs
        .iter()
        .chain(&n.parameters.args)
        .chain(&n.parameters.kwonlyargs)
    {
        scan.tick(1)?;
        if let Some(default) = parameter.default.as_deref() {
            if !values::inert(scan, default, 0)? {
                return Ok(false);
            }
        }
    }
    let mut annotations = Vec::new();
    for arg in n.parameters.iter() {
        scan.tick(1)?;
        if let Some(annotation) = arg.annotation() {
            annotations.push(annotation);
        }
    }
    annotations.extend(n.returns.as_deref());
    for annotation in annotations {
        scan.tick(1)?;
        if !values::deferred(scan, env, annotation)? && !values::inert(scan, annotation, 0)? {
            return Ok(false);
        }
    }
    Ok(true)
}

fn native_body(scan: &mut Scan, env: &Env<'_>, stmt: &Stmt) -> Result<bool> {
    if unproven(scan, env, stmt, true)? {
        return Ok(false);
    }
    let Stmt::ClassDef(n) = stmt else {
        return Err("native class proof needs a class".into());
    };
    for child in &n.body {
        scan.tick(1)?;
        match child {
            Stmt::Pass(_) => {}
            Stmt::Expr(n) if matches!(&*n.value, Expr::StringLiteral(_)) => {}
            Stmt::FunctionDef(_) => {
                if !native_method(scan, env, child)? {
                    return Ok(false);
                }
            }
            Stmt::Assign(n) => {
                scan.tick(n.targets.len())?;
                if !n.targets.iter().all(|n| matches!(n, Expr::Name(_)))
                    || !values::inert(scan, &n.value, 0)?
                {
                    return Ok(false);
                }
            }
            Stmt::AnnAssign(n) => {
                if !matches!(&*n.target, Expr::Name(_))
                    || !values::deferred(scan, env, &n.annotation)?
                        && !values::inert(scan, &n.annotation, 0)?
                {
                    return Ok(false);
                }
                let Some(value) = n.value.as_deref() else {
                    continue;
                };
                if !values::inert(scan, value, 0)? {
                    return Ok(false);
                }
            }
            _ => return Ok(false),
        }
    }
    Ok(true)
}

pub(super) fn table(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(stmt @ Stmt::ClassDef(n)) = node else {
            continue;
        };
        let at = env
            .module
            .location(&crate::module::definition::Def::Class(n).range(env.module.text()));
        let row = json!([at.line, {
            "header": n.decorator_list.is_empty() && n.arguments.as_ref().is_none_or(|a| a.keywords.is_empty()),
            "exposed": exposed(scan, n)?, "unproven": [unproven(scan, env, stmt, false)?, unproven(scan, env, stmt, true)?],
            "receives": receives(scan, env, stmt)?, "namespace": namespace_static(scan, env, stmt)?,
            "native_body": native_body(scan, env, stmt)?,
        }]);
        scan.output.value(&row)?;
        out.push(row);
    }
    Ok(out)
}
