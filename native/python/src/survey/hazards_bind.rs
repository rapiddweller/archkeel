// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that the import statements of a module bind, for the door check (AD-450, AD-472).

use std::collections::HashMap;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{ModModule, Stmt};

use super::reflect;

/// The qualified names that the import statements of a module bind, in any scope.
pub(super) fn bindings(tree: &ModModule) -> HashMap<String, Vec<String>> {
    struct Imports(HashMap<String, Vec<String>>);
    impl<'a> Visitor<'a> for Imports {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            for (name, origin) in bound(stmt) {
                self.0.entry(name).or_default().push(origin);
            }
            visitor::walk_stmt(self, stmt);
        }
    }
    let mut walk = Imports(HashMap::new());
    walk.visit_body(&tree.body);
    reflect::aliases(tree, &mut walk.0);
    walk.0
}

/// The names that one import statement binds and their qualified origins. A relative import
/// names a module of the project and binds nothing here.
fn bound(stmt: &Stmt) -> Vec<(String, String)> {
    match stmt {
        Stmt::Import(node) => node
            .names
            .iter()
            .map(|alias| {
                let name = alias.name.as_str();
                match &alias.asname {
                    Some(asname) => (asname.to_string(), name.to_owned()),
                    None => {
                        let first = name.split('.').next().unwrap_or(name);
                        (first.to_owned(), first.to_owned())
                    }
                }
            })
            .collect(),
        Stmt::ImportFrom(node) if node.level == 0 => {
            let module = node.module.as_ref().map_or("", |module| module.as_str());
            node.names
                .iter()
                .map(|alias| {
                    let name = alias.name.as_str();
                    let local = alias.asname.as_ref().map_or(name, |asname| asname.as_str());
                    (local.to_owned(), format!("{module}.{name}"))
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// The names that an import statement imports, as qualified names, for the door check: each
/// module of `import a.b`, and each name of `from m import n`. A star import names its module.
pub(super) fn imported(stmt: &Stmt) -> Vec<String> {
    match stmt {
        // A plain `import importlib` binds the module of the accepted literal call (AD-472);
        // each use of the name is still read. Each other import of `importlib` is a reference.
        Stmt::Import(node) => node
            .names
            .iter()
            .filter(|a| a.asname.is_some() || a.name.as_str() != "importlib")
            .map(|a| a.name.to_string())
            .collect(),
        Stmt::ImportFrom(node) if node.level == 0 => {
            let module = node.module.as_ref().map_or("", |module| module.as_str());
            node.names
                .iter()
                .map(|alias| match alias.name.as_str() {
                    "*" => module.to_owned(),
                    name => format!("{module}.{name}"),
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// The local name that `from m import n [as a]` binds for the qualified name `m.n`, if the
/// statement binds it (AD-664).
pub(super) fn local_of(stmt: &Stmt, qualified: &str) -> Option<String> {
    let Stmt::ImportFrom(node) = stmt else {
        return None;
    };
    let module = node.module.as_ref().map_or("", |module| module.as_str());
    node.names.iter().find_map(|alias| {
        let name = alias.name.as_str();
        (format!("{module}.{name}") == qualified).then(|| {
            alias
                .asname
                .as_ref()
                .map_or(name, |asname| asname.as_str())
                .to_owned()
        })
    })
}
