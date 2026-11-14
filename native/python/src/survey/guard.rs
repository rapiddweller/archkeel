// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `TYPE_CHECKING` guard of one module (AD-450, lead decision F).
//!
//! The body of `if <guard>:` holds imports that do not run. A test is a guard only when its
//! name is bound by an import from `typing` or `typing_extensions` and the file binds that name
//! nowhere else: `from typing import TYPE_CHECKING [as X]`, or `typing.TYPE_CHECKING` where
//! `import typing [as X]` is each binding of the module name. Any other name or attribute
//! called `TYPE_CHECKING` is a runtime value, so its imports are runtime edges. A module-level
//! star import can bind any name, so a module with one has no guard. `if not <guard>:` and `else` run.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Alias, Expr, ExprContext, ModModule, Parameter, Pattern, Stmt};

/// The modules whose `TYPE_CHECKING` is the guard.
const TYPING: [&str; 2] = ["typing", "typing_extensions"];

/// The guard names and the typing module names of one module.
#[derive(Default)]
pub(super) struct Guard {
    names: HashSet<String>,
    modules: HashSet<String>,
}

impl Guard {
    pub(super) fn of(tree: &ModModule) -> Self {
        let mut walk = Bindings::default();
        walk.visit_body(&tree.body);
        let star = tree.body.iter().any(|stmt| {
            matches!(stmt, Stmt::ImportFrom(node) if node.names.iter().any(|a| a.name.as_str() == "*"))
        });
        if star {
            return Guard::default();
        }
        let only = |found: &HashMap<String, usize>| -> HashSet<String> {
            found
                .keys()
                .filter(|name| !walk.other.contains_key(*name))
                .cloned()
                .collect()
        };
        Guard {
            names: only(&walk.guards),
            modules: only(&walk.typing),
        }
    }

    /// True when `test` is the guard.
    pub(super) fn holds(&self, test: &Expr) -> bool {
        match test {
            Expr::Name(node) => self.names.contains(node.id.as_str()),
            Expr::Attribute(node) => {
                node.attr.as_str() == "TYPE_CHECKING"
                    && matches!(&*node.value, Expr::Name(base) if self.modules.contains(base.id.as_str()))
            }
            _ => false,
        }
    }
}

/// Each binding of each name in a module, in any scope.
#[derive(Default)]
struct Bindings {
    guards: HashMap<String, usize>,
    typing: HashMap<String, usize>,
    other: HashMap<String, usize>,
}

impl Bindings {
    fn other(&mut self, name: &str) {
        *self.other.entry(name.to_owned()).or_default() += 1;
    }

    fn import(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::Import(node) => node.names.iter().for_each(|alias| self.plain(alias)),
            Stmt::ImportFrom(node) => {
                let typing = node.level == 0
                    && node
                        .module
                        .as_ref()
                        .is_some_and(|m| TYPING.contains(&m.as_str()));
                node.names.iter().for_each(|alias| self.from(alias, typing));
            }
            _ => {}
        }
    }

    /// `import m [as x]`: a binding of a typing module or another binding.
    fn plain(&mut self, alias: &Alias) {
        let name = alias.name.as_str();
        let local = alias.asname.as_ref().map_or_else(
            || name.split('.').next().unwrap_or(name),
            |asname| asname.as_str(),
        );
        let table = if TYPING.contains(&name) {
            &mut self.typing
        } else {
            &mut self.other
        };
        *table.entry(local.to_owned()).or_default() += 1;
    }

    /// One name of `from m import ...`; `typing` is true for an import from a typing module.
    fn from(&mut self, alias: &Alias, typing: bool) {
        let name = alias.name.as_str();
        let local = alias.asname.as_ref().map_or(name, |asname| asname.as_str());
        let table = match name {
            "*" => return,
            "TYPE_CHECKING" if typing => &mut self.guards,
            _ => &mut self.other,
        };
        *table.entry(local.to_owned()).or_default() += 1;
    }
}

impl<'a> Visitor<'a> for Bindings {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(_) | Stmt::ImportFrom(_) => self.import(stmt),
            Stmt::FunctionDef(node) => self.other(node.name.as_str()),
            Stmt::ClassDef(node) => self.other(node.name.as_str()),
            Stmt::Global(node) => node.names.iter().for_each(|n| self.other(n.as_str())),
            Stmt::Nonlocal(node) => node.names.iter().for_each(|n| self.other(n.as_str())),
            Stmt::Try(node) => {
                for handler in &node.handlers {
                    let ruff_python_ast::ExceptHandler::ExceptHandler(handler) = handler;
                    handler.name.iter().for_each(|n| self.other(n.as_str()));
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if node.ctx != ExprContext::Load {
                self.other(node.id.as_str());
            }
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.other(parameter.name.as_str());
        visitor::walk_parameter(self, parameter);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        match pattern {
            Pattern::MatchAs(node) => node.name.iter().for_each(|n| self.other(n.as_str())),
            Pattern::MatchStar(node) => node.name.iter().for_each(|n| self.other(n.as_str())),
            Pattern::MatchMapping(node) => node.rest.iter().for_each(|n| self.other(n.as_str())),
            _ => {}
        }
        visitor::walk_pattern(self, pattern);
    }
}

#[cfg(test)]
#[path = "guard_tests.rs"]
mod tests;
