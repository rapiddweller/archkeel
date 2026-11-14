// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `TYPE_CHECKING` guard of one module (AD-450, lead decision F).
//!
//! The body of `if <guard>:` holds imports that do not run. A test is a guard only when its
//! name is bound by an import from `typing` or `typing_extensions` and the file binds that name
//! nowhere else: `from typing import TYPE_CHECKING [as X]`, or `typing.TYPE_CHECKING` where
//! `import typing [as X]` is each binding of the module name. Any other name or attribute
//! called `TYPE_CHECKING` is a runtime value, so its imports are runtime edges. A star import or
//! a type parameter list makes the binding count unknown (`binders.rs`), so such a module has no
//! guard. `if not <guard>:` and `else` run.

use std::collections::HashMap;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ModModule, Stmt};

use super::binders::Binders;

/// The modules whose `TYPE_CHECKING` is the guard.
const TYPING: [&str; 2] = ["typing", "typing_extensions"];

/// The guard names and the typing module names of one module.
#[derive(Default)]
pub(super) struct Guard {
    names: Vec<String>,
    modules: Vec<String>,
}

impl Guard {
    /// The guard of a module. `binders` counts each binding of each name in the module; a name
    /// is a guard name when each of its bindings is an import of the guard from a typing module.
    pub(super) fn of(tree: &ModModule, binders: &Binders) -> Self {
        let mut walk = Imports::default();
        walk.visit_body(&tree.body);
        let only = |found: HashMap<String, usize>| -> Vec<String> {
            found
                .into_iter()
                .filter(|(name, count)| binders.count(name) == Some(*count))
                .map(|(name, _)| name)
                .collect()
        };
        Guard {
            names: only(walk.guards),
            modules: only(walk.typing),
        }
    }

    /// True when `test` is the guard.
    pub(super) fn holds(&self, test: &Expr) -> bool {
        let known = |list: &[String], name: &str| list.iter().any(|item| item == name);
        match test {
            Expr::Name(node) => known(&self.names, node.id.as_str()),
            Expr::Attribute(node) => {
                node.attr.as_str() == "TYPE_CHECKING"
                    && matches!(&*node.value, Expr::Name(base) if known(&self.modules, base.id.as_str()))
            }
            _ => false,
        }
    }
}

/// The bindings of the guard and of the typing modules by import statements, in any scope.
#[derive(Default)]
struct Imports {
    guards: HashMap<String, usize>,
    typing: HashMap<String, usize>,
}

impl<'a> Visitor<'a> for Imports {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => {
                let typing = node
                    .names
                    .iter()
                    .filter(|a| TYPING.contains(&a.name.as_str()));
                for alias in typing {
                    let local = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
                    *self.typing.entry(local.to_owned()).or_default() += 1;
                }
            }
            Stmt::ImportFrom(node)
                if node.level == 0
                    && node
                        .module
                        .as_ref()
                        .is_some_and(|m| TYPING.contains(&m.as_str())) =>
            {
                let guard = node
                    .names
                    .iter()
                    .filter(|a| a.name.as_str() == "TYPE_CHECKING");
                for alias in guard {
                    let local = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
                    *self.guards.entry(local.to_owned()).or_default() += 1;
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }
}

#[cfg(test)]
#[path = "guard_tests.rs"]
mod tests;
