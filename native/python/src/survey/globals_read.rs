// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A read of the globals of a function that cannot import a module (AD-530).
//!
//! `f.__globals__` and `getattr(f, "__globals__")` give the namespace of a function. The dict
//! reaches `__builtins__` and so any import, so the survey treats a read as a dynamic import
//! (`hazards.rs`). A read is inert when the dict is used only in forms that name no trojan horse:
//!
//! - `d.get("key")`, `d["key"]` and `"key" in d` with a literal key that is no trojan horse string;
//! - an argument of a call whose callee is outside the scan, or a function of the scan whose
//!   parameter is used in these forms only (bounded, a cycle is not inert). A callee outside the
//!   scan is a function of an import that leaves the scan, a member of such a module, or a pure
//!   builtin (`PURE_BUILTINS`). The survey does not read library code (AD-450); a library
//!   function that gives the dict back, and project code that then reads `__builtins__` from it
//!   by a computed key, is a known limit (AD-530).
//!
//! The dict may be the value of one local name that the function writes once. Any other use is
//! not inert: a return, a store, a copy, `.items()`, `**d`, an iteration, a computed key, a
//! callee that the survey cannot name, or a name that the function writes again.
//!
//! Release 4.0.1 counts no edge for a read of `__globals__`. Evaluating a string annotation in the
//! dict is what `typing.get_type_hints(f)` does in library code, and the survey does not read
//! library code (AD-450).

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::globals_locals::Locals;
use super::globals_project::Project;
use super::globals_uses::Target;
use crate::module::Module;

/// The ranges of the inert sources of each module: the string `"__globals__"` of a `getattr`, or
/// the attribute `__globals__` (AD-530).
pub(super) fn inert_reads(modules: &[Module]) -> Vec<HashSet<TextRange>> {
    let project = Project::new(modules);
    modules
        .iter()
        .map(|module| {
            let mut found = HashSet::new();
            let mut walk = Functions {
                project: &project,
                module: module.name.as_str(),
                found: &mut found,
            };
            walk.visit_body(&module.tree.body);
            found
        })
        .collect()
}

/// The functions of a module: a source inside one is inert or not by its own uses.
struct Functions<'p, 'm> {
    project: &'p Project<'m>,
    module: &'p str,
    found: &'p mut HashSet<TextRange>,
}

/// The marker range of a source of globals: the string of `getattr(f, "__globals__")`, or the
/// attribute `__globals__` of a function or `f_globals` of a frame.
fn source(expr: &Expr) -> Option<TextRange> {
    match expr {
        Expr::Call(call) => {
            let named = matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "getattr");
            let args = &call.arguments.args;
            match args.get(1) {
                Some(Expr::StringLiteral(text))
                    if named
                        && (2..=3).contains(&args.len())
                        && call.arguments.keywords.is_empty()
                        && text.value.to_str() == "__globals__" =>
                {
                    Some(text.range())
                }
                _ => None,
            }
        }
        Expr::Attribute(node)
            if matches!(node.attr.as_str(), "__globals__" | "f_globals")
                && node.ctx == ExprContext::Load =>
        {
            Some(node.range())
        }
        _ => None,
    }
}

impl<'a> Visitor<'a> for Functions<'_, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::FunctionDef(def) = stmt {
            self.function(def);
        }
        visitor::walk_stmt(self, stmt);
    }
}

impl Functions<'_, '_> {
    /// Each source of the function, with the expression that holds it.
    fn function(&mut self, def: &StmtFunctionDef) {
        let local = Locals::of(def);
        let mut sources = Sources::default();
        sources.visit_body(&def.body);
        for (holder, marker) in sources.found {
            let target = Target::Source(holder.range());
            let mut path = Vec::new();
            let direct = self
                .project
                .uses_inert(self.module, &def.body, target, &local, &mut path);
            if direct {
                self.found.insert(marker);
            }
        }
        // A source that one local name holds: the name has no other write, and each load is inert.
        let mut assigns = Assigned::default();
        assigns.visit_body(&def.body);
        for (name, holder, marker) in assigns.found {
            let single = local.stored.get(name.as_str()).copied() == Some(1);
            if !single || local.declared.contains(&name) {
                continue;
            }
            let mut path = Vec::new();
            let target = Target::Name(&name);
            if self
                .project
                .uses_inert(self.module, &def.body, target, &local, &mut path)
            {
                let _ = holder;
                self.found.insert(marker);
            }
        }
    }
}

/// The sources in a function body, with the expression that holds each.
#[derive(Default)]
struct Sources<'a> {
    found: Vec<(&'a Expr, TextRange)>,
}

impl<'a> Visitor<'a> for Sources<'a> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Some(marker) = source(expr) {
            self.found.push((expr, marker));
        }
        visitor::walk_expr(self, expr);
    }
}

/// The statements `name = <source>` of a function body.
#[derive(Default)]
struct Assigned<'a> {
    found: Vec<(String, &'a Expr, TextRange)>,
}

impl<'a> Visitor<'a> for Assigned<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::Assign(node) = stmt {
            if let ([Expr::Name(name)], Some(marker)) =
                (node.targets.as_slice(), source(&node.value))
            {
                self.found.push((name.id.to_string(), &node.value, marker));
            }
        }
        visitor::walk_stmt(self, stmt);
    }
}

#[cfg(test)]
#[path = "globals_read_tests.rs"]
mod tests;
