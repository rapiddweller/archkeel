// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Ordered decorator and property proofs. The lookup uses the resolved import aliases.

use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};
use serde_json::{json, Value};
use std::collections::HashMap;

use super::super::scan::{Result, Scan};
use super::super::{class, statements};
use super::{resolve, Env};
use crate::pyast::Node;

const TARGETS: &[&str] = &[
    "staticmethod",
    "builtins.staticmethod",
    "classmethod",
    "builtins.classmethod",
    "property",
    "builtins.property",
    "typing.overload",
    "typing_extensions.overload",
    "abc.abstractmethod",
];

pub(super) fn line(env: &Env<'_>, method: &StmtFunctionDef) -> i64 {
    env.module
        .location(&crate::module::definition::Def::Function(method).range(env.module.text()))
        .line
}

pub(super) fn proven(
    scan: &mut Scan,
    env: &Env<'_>,
    decorator: &Expr,
    method: &Stmt,
    parent: Option<&Stmt>,
    targets: &[&str],
) -> Result<bool> {
    let target = match decorator {
        Expr::Call(n) => &*n.func,
        n => n,
    };
    let resolved = resolve(scan, env.module, target)?;
    scan.tick(targets.len())?;
    if !targets.contains(&resolved.as_str()) {
        return Ok(false);
    }
    let root = match target {
        Expr::Name(n) => Some(n.id.as_str()),
        Expr::Attribute(n) => match &*n.value {
            Expr::Name(n) => Some(n.id.as_str()),
            _ => None,
        },
        _ => None,
    };
    let Some(root) = root else {
        return Ok(false);
    };
    let class_body = match parent {
        Some(Stmt::ClassDef(n)) => Some(n.body.as_slice()),
        _ => None,
    };
    if !scan.aliases.contains_key(root) {
        return Ok(matches!(decorator, Expr::Name(_))
            && matches!(
                resolved.as_str(),
                "staticmethod" | "classmethod" | "property"
            )
            && !env.may_exist(scan, &env.module.tree.body, None, root)?
            && match class_body {
                Some(body) => !env.may_exist(scan, body, Some(method), root)?,
                None => true,
            });
    }
    if !env.stable.contains(root)
        || !env.may_exist(
            scan,
            &env.module.tree.body,
            Some(parent.unwrap_or(method)),
            root,
        )?
    {
        return Ok(false);
    }
    Ok(match class_body {
        Some(body) => !env.may_exist(scan, body, Some(method), root)?,
        None => true,
    })
}

pub(super) fn signature(
    scan: &mut Scan,
    env: &Env<'_>,
    method: &Stmt,
    parent: Option<&Stmt>,
) -> Result<(&'static str, bool)> {
    let Stmt::FunctionDef(n) = method else {
        return Err("method proof needs a function".into());
    };
    let mut kind = "instance";
    let mut valid = true;
    let mut descriptors = 0;
    for decorator in &n.decorator_list {
        scan.tick(1)?;
        let expr = &decorator.expression;
        let proven =
            !matches!(expr, Expr::Call(_)) && proven(scan, env, expr, method, parent, TARGETS)?;
        valid &= proven;
        if proven {
            match resolve(scan, env.module, expr)?.as_str() {
                "staticmethod" | "builtins.staticmethod" => {
                    kind = "static";
                    descriptors += 1;
                }
                "classmethod" | "builtins.classmethod" => {
                    kind = "class";
                    descriptors += 1;
                }
                "property" | "builtins.property" => descriptors += 1,
                _ => {}
            }
        }
    }
    Ok((kind, valid && descriptors <= 1))
}

pub(super) fn direct(env: &Env<'_>, stmt: &Stmt) -> bool {
    use ruff_text_size::Ranged;
    env.module
        .tree
        .body
        .binary_search_by_key(&stmt.start(), Ranged::start)
        .is_ok()
}

pub(super) fn properties(
    scan: &mut Scan,
    env: &Env<'_>,
    parent: &Stmt,
) -> Result<HashMap<*const StmtFunctionDef, Value>> {
    let Stmt::ClassDef(class) = parent else {
        return Ok(HashMap::new());
    };
    let mut bindings = HashMap::new();
    if !direct(env, parent) {
        return Ok(bindings);
    }
    let mut previous = HashMap::new();
    for child in &class.body {
        scan.tick(1)?;
        let names = statements::binding(scan, &Node::Stmt(child), env.module.text())?;
        let Stmt::FunctionDef(n) = child else {
            erase(scan, &names, &mut previous)?;
            continue;
        };
        if let Some(binding) = operation(scan, env, child, parent, &previous, &bindings)? {
            bindings.insert(std::ptr::from_ref(n), binding);
        }
        previous.insert(n.name.as_str(), n);
    }
    Ok(bindings)
}

fn erase(
    scan: &mut Scan,
    names: &Value,
    previous: &mut HashMap<&str, &StmtFunctionDef>,
) -> Result<()> {
    if names.is_null() {
        scan.tick(previous.len())?;
        previous.clear();
        return Ok(());
    }
    let names = names
        .get(0)
        .and_then(Value::as_array)
        .ok_or("property binding names unseen")?;
    for name in names {
        scan.tick(1)?;
        let name = name.as_str().ok_or("property binding name unseen")?;
        previous.remove(name);
    }
    Ok(())
}

fn operation(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    parent: &Stmt,
    previous: &HashMap<&str, &StmtFunctionDef>,
    bindings: &HashMap<*const StmtFunctionDef, Value>,
) -> Result<Option<Value>> {
    let (Stmt::FunctionDef(n), Stmt::ClassDef(owner)) = (stmt, parent) else {
        return Ok(None);
    };
    if n.decorator_list.len() != 1 || n.is_async {
        return Ok(None);
    }
    let Some(decorator) = n.decorator_list.first().map(|d| &d.expression) else {
        return Ok(None);
    };
    let line = line(env, n);
    if !matches!(decorator, Expr::Call(_))
        && proven(
            scan,
            env,
            decorator,
            stmt,
            Some(parent),
            &["property", "builtins.property"],
        )?
    {
        return Ok(Some(
            json!({"operation":"create", "source":"new", "line":line, "source_line":0}),
        ));
    }
    let Expr::Attribute(decorator) = decorator else {
        return Ok(None);
    };
    let operation = decorator.attr.as_str();
    if !matches!(operation, "getter" | "setter") {
        return Ok(None);
    }
    let descriptor = &*decorator.value;
    if matches!(descriptor, Expr::Name(name) if name.id.as_str() == n.name.as_str()) {
        if let Some(origin) = previous.get(n.name.as_str()) {
            if bindings.contains_key(&std::ptr::from_ref(*origin)) {
                return Ok(Some(
                    json!({"operation":operation, "source":"local", "line":line, "source_line":self::line(env, origin)}),
                ));
            }
        }
    }
    let Expr::Attribute(attribute) = descriptor else {
        return Ok(None);
    };
    if attribute.attr.as_str() != n.name.as_str() || owner.bases().len() != 1 {
        return Ok(None);
    }
    let Some(base) = owner.bases().first() else {
        return Ok(None);
    };
    let mut root = &*attribute.value;
    while let Expr::Attribute(n) = root {
        scan.tick(1)?;
        root = &n.value;
    }
    let Expr::Name(root) = root else {
        return Ok(None);
    };
    if class::text(scan, &attribute.value, env.module.text())?
        == class::text(scan, base, env.module.text())?
        && !env.may_exist(scan, &owner.body, Some(stmt), root.id.as_str())?
    {
        return Ok(Some(
            json!({"operation":operation, "source":"base", "line":line, "source_line":0}),
        ));
    }
    Ok(None)
}

fn final_method(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    parent: &Stmt,
    n: &StmtFunctionDef,
) -> Result<bool> {
    let Stmt::ClassDef(class) = parent else {
        return Ok(false);
    };
    if !n.decorator_list.is_empty() || !direct(env, parent) {
        return Ok(false);
    }
    scan.tick(class.body.len())?;
    for later in class.body.iter().rev() {
        scan.tick(1)?;
        if std::ptr::eq(later, stmt) {
            return Ok(true);
        }
        if env.may_exist(scan, std::slice::from_ref(later), None, n.name.as_str())? {
            return Ok(false);
        }
    }
    Ok(true)
}

pub(super) fn descriptor(
    scan: &mut Scan,
    env: &Env<'_>,
    stmt: &Stmt,
    parent: Option<&Stmt>,
    properties: &HashMap<*const StmtFunctionDef, Value>,
) -> Result<Value> {
    let Stmt::FunctionDef(n) = stmt else {
        return Err("method descriptor needs a function".into());
    };
    let (kind, proven) = signature(scan, env, stmt, parent)?;
    let mut final_binding = false;
    let mut binding = None;
    if let Some(parent @ Stmt::ClassDef(class)) = parent {
        if env.stable.contains(class.name.as_str()) {
            binding = properties.get(&std::ptr::from_ref(n));
            final_binding = final_method(scan, env, stmt, parent, n)?;
        }
    }
    let mut data = json!({"method_kind":kind, "signature_decorators_proven":proven, "source_final_method_binding":final_binding});
    if let Some(binding) = binding {
        data["property_binding"] = binding.to_owned();
    }
    Ok(data)
}

pub(super) fn table(scan: &mut Scan, env: &Env<'_>, nodes: &[Node<'_>]) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for node in nodes {
        scan.tick(1)?;
        let Node::Stmt(stmt) = node else {
            continue;
        };
        if let Stmt::FunctionDef(n) = stmt {
            let data = descriptor(scan, env, stmt, None, &HashMap::new())?;
            let row = json!([line(env, n), data]);
            scan.output.value(&row)?;
            out.push(row);
        }
        let Stmt::ClassDef(n) = stmt else {
            continue;
        };
        let properties = properties(scan, env, stmt)?;
        for child in &n.body {
            scan.tick(1)?;
            let Stmt::FunctionDef(method) = child else {
                continue;
            };
            let data = descriptor(scan, env, child, Some(stmt), &properties)?;
            let row = json!([line(env, method), data]);
            scan.output.value(&row)?;
            out.push(row);
        }
    }
    Ok(out)
}
