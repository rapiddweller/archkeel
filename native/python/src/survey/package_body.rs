// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the top-level statements of a package body bind (`imports.rs`): the names that it binds
//! ahead of a submodule, whether it can give any name, the submodules that it imports, and the
//! module that a relative name of the package names.

use std::collections::HashSet;

use ruff_python_ast::{Expr, Stmt, StmtImportFrom};

use super::binders::import_bindings;
use crate::module::Module;

/// `_shadowed_names`: the names that the top-level statements of a package body bind ahead of a
/// submodule of the same name (AD-53). `__getattr__` or a star import empties the set.
pub(super) fn shadowing_names(module: &Module) -> HashSet<String> {
    let mut names = HashSet::new();
    for statement in &module.tree.body {
        match statement {
            Stmt::FunctionDef(node) if node.name.as_str() == "__getattr__" => {
                return HashSet::new()
            }
            Stmt::ClassDef(node) if node.name.as_str() == "__getattr__" => return HashSet::new(),
            Stmt::FunctionDef(node) => drop(names.insert(node.name.id.to_string())),
            Stmt::ClassDef(node) => drop(names.insert(node.name.id.to_string())),
            Stmt::Assign(node) => names.extend(node.targets.iter().filter_map(name_of)),
            Stmt::AnnAssign(node) => names.extend(name_of(&node.target)),
            Stmt::Import(_) => names.extend(import_bindings(statement)),
            Stmt::ImportFrom(node) => {
                if node.names.iter().any(|alias| alias.name.as_str() == "*") {
                    return HashSet::new();
                }
                names.extend(from_bindings(node, &module.name));
            }
            _ => {}
        }
    }
    names
}

/// The names of `from ... import` in the package body of `package`, without the plain
/// `from . import name` that binds the submodule itself (`_binds_identical_submodule`).
fn from_bindings<'n>(node: &'n StmtImportFrom, package: &str) -> impl Iterator<Item = String> + 'n {
    let own = anchor(node, package).as_deref() == Some(package);
    node.names
        .iter()
        .filter(move |alias| !(own && alias.asname.is_none()))
        .map(|alias| alias.asname.as_ref().unwrap_or(&alias.name).id.to_string())
}

fn name_of(target: &Expr) -> Option<String> {
    match target {
        Expr::Name(node) => Some(node.id.to_string()),
        _ => None,
    }
}

/// The submodules that a package body imports at its top level. The import system binds each
/// one as an attribute of the package, so `__getattr__` is not called for its name.
pub(super) fn own_submodules(module: &Module) -> HashSet<String> {
    let package = module.name.as_str();
    let mut found = HashSet::new();
    for statement in &module.tree.body {
        match statement {
            Stmt::ImportFrom(node) => {
                let Some(anchor) = anchor(node, package) else {
                    continue;
                };
                found.insert(anchor.clone());
                let names = node.names.iter().map(|alias| alias.name.as_str());
                found.extend(names.map(|name| format!("{anchor}.{name}")));
            }
            Stmt::Import(node) => {
                found.extend(node.names.iter().map(|alias| alias.name.to_string()));
            }
            _ => {}
        }
    }
    found
}

/// A package body that can give any name: a top-level `__getattr__` or a star import.
pub(super) fn open_body(module: &Module) -> bool {
    module.tree.body.iter().any(|statement| match statement {
        Stmt::FunctionDef(node) => node.name.as_str() == "__getattr__",
        Stmt::ImportFrom(node) => node.names.iter().any(|alias| alias.name.as_str() == "*"),
        _ => false,
    })
}

/// `importlib.util.resolve_name` for a name of `level` dots and then `name`. Each failure of it
/// on CPython 3.11 to 3.14 is an `ImportError`.
pub(super) fn resolve(level: u32, name: &str, package: &str) -> Option<String> {
    if package.is_empty() {
        return None;
    }
    let mut base = package;
    for _ in 1..level {
        base = &base[..base.rfind('.')?];
    }
    Some(if name.is_empty() {
        base.to_owned()
    } else {
        format!("{base}.{name}")
    })
}

/// The module that `from ... import` names, or `None` when `resolve_name` fails.
pub(super) fn anchor(node: &StmtImportFrom, package: &str) -> Option<String> {
    let name = node.module.as_ref().map_or("", |module| module.as_str());
    if node.level == 0 {
        return Some(name.to_owned());
    }
    resolve(node.level, name, package)
}
