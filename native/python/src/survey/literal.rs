// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a call imports one literal module (AD-472).
//!
//! Exactly two forms are a static edge and no hazard:
//!
//! - `importlib.import_module("a.b")`, when each binding of `importlib` in the module is a plain
//!   `import importlib` (no alias, no submodule import, no other binding);
//! - `__import__("a.b")`, when the module binds `__import__` nowhere.
//!
//! The call has exactly one argument and no keyword: a plain string literal with an absolute dotted
//! name. A module that calls `globals`, `vars` or `locals` proves nothing. `from importlib import
//! import_module` stays a door: its import statement is a reference to the door. Any other call,
//! alias, value or attribute use stays a `dynamic_import` gap (`hazards.rs`).

use archkeel_facts::identity::is_identifier;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt};

use super::binders::Binders;

/// What one module proves about the names of the two import functions.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(super) struct Proof {
    importlib: bool,
    dunder: bool,
}

impl Proof {
    /// The proof of a module from its binding counts (`binders.rs`).
    pub(super) fn of(tree: &ModModule, binders: &Binders) -> Self {
        let mut walk = Walk::default();
        walk.visit_body(&tree.body);
        if walk.namespace {
            return Proof::default();
        }
        Proof {
            importlib: walk.plain > 0 && binders.count("importlib") == Some(walk.plain),
            dunder: binders.count("__import__") == Some(0),
        }
    }

    /// The module that a call imports, when the proof covers its function and its argument.
    pub(super) fn target(&self, call: &ExprCall) -> Option<String> {
        let trusted = match &*call.func {
            Expr::Name(node) => node.id.as_str() == "__import__" && self.dunder,
            Expr::Attribute(node) => {
                node.attr.as_str() == "import_module"
                    && matches!(&*node.value, Expr::Name(base) if base.id.as_str() == "importlib")
                    && self.importlib
            }
            _ => false,
        };
        if !trusted || !call.arguments.keywords.is_empty() {
            return None;
        }
        let [Expr::StringLiteral(text)] = &*call.arguments.args else {
            return None;
        };
        let name = text.value.to_str();
        let dotted = !text.value.is_implicit_concatenated() && name.split('.').all(is_identifier);
        dotted.then(|| name.to_owned())
    }
}

/// The plain `import importlib` statements and the calls that read or write a namespace.
#[derive(Default)]
struct Walk {
    plain: usize,
    namespace: bool,
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::Import(node) = stmt {
            let plain = node
                .names
                .iter()
                .filter(|alias| alias.asname.is_none() && alias.name.as_str() == "importlib");
            self.plain += plain.count();
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        self.namespace |= matches!(expr, Expr::Name(node)
            if matches!(node.id.as_str(), "globals" | "vars" | "locals"));
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "literal_tests.rs"]
mod tests;
