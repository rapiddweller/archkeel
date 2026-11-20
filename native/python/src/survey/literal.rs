// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a call imports one literal module (AD-472).
//!
//! Exactly two forms are a static edge:
//!
//! - `importlib.import_module("a.b")`, when each binding of `importlib` in the module is a plain
//!   `import importlib` (no alias, no submodule import, no other binding), and there is no
//!   visible write to that loader in the scan;
//! - `__import__("a.b")`, when the module binds `__import__` nowhere.
//!
//! The call has exactly one argument and no keyword: a plain string literal with an absolute dotted
//! name. A module that calls `globals`, `vars` or `locals` proves nothing. `from importlib import
//! import_module` stays a door: its import statement is a reference to the door. Any other call,
//! alias, value or attribute use stays a `dynamic_import` gap (`hazards.rs`). A target that is
//! itself a hazard keeps its named gap as well as the edge.

use std::collections::BTreeMap;

use archkeel_facts::identity::{evidence_id, is_identifier};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt};

use super::binders::Binders;
use crate::module::Module;

/// What one module proves about the names of the two import functions.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(super) struct Proof {
    importlib: bool,
    dunder: bool,
}

impl Proof {
    pub(super) fn without_replaced_loader(mut self, replaced: bool) -> Self {
        self.importlib &= !replaced;
        self
    }

    /// A direct `importlib.import_module` reference with the loader binding proved.
    pub(super) fn loader(&self, function: &Expr) -> bool {
        self.importlib
            && matches!(function, Expr::Attribute(node)
                if node.attr.as_str() == "import_module"
                && matches!(&*node.value, Expr::Name(base) if base.id.as_str() == "importlib"))
    }

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
            Expr::Attribute(_) => self.loader(&call.func),
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

/// The number of plain `import importlib` statements of a module.
pub(super) fn plain_importlib(tree: &ModModule) -> usize {
    let mut walk = Walk::default();
    walk.visit_body(&tree.body);
    walk.plain
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

/// A stable direct assignment supplies its written immutable tuple, not its callers.
pub(super) fn literal_tuples(
    module: &Module,
    stable: &[String],
) -> BTreeMap<String, (u32, Vec<String>)> {
    module
        .tree
        .body
        .iter()
        .filter_map(|stmt| tuple_binding(module, stable, stmt))
        .collect()
}

fn tuple_binding(
    module: &Module,
    stable: &[String],
    stmt: &Stmt,
) -> Option<(String, (u32, Vec<String>))> {
    let Stmt::Assign(node) = stmt else {
        return None;
    };
    let ([Expr::Name(name)], Expr::Tuple(tuple)) = (node.targets.as_slice(), node.value.as_ref())
    else {
        return None;
    };
    let name = name.id.as_str();
    stable
        .binary_search_by(|item| String::as_str(item).cmp(name))
        .ok()?;
    let members = tuple.elts.iter().map(member).collect::<Option<Vec<_>>>()?;
    let line = u32::try_from(module.location(stmt).line).ok()?;
    (!Vec::is_empty(&members)).then(|| (name.to_owned(), (line, members)))
}

fn member(expr: &Expr) -> Option<String> {
    let Expr::StringLiteral(literal) = expr else {
        return None;
    };
    let text = literal.value.to_str();
    (!literal.value.is_implicit_concatenated() && text.split('.').all(is_identifier))
        .then(|| text.to_owned())
}

/// Cite the same callee position as the unresolved loader gap.
pub(super) fn loader_calls(module: &Module, binders: &Binders) -> BTreeMap<String, String> {
    if binders.count("importlib").unwrap_or(0) == 0 {
        return BTreeMap::new();
    }
    let mut walk = Calls {
        module,
        proof: Proof::of(&module.tree, binders),
        found: BTreeMap::new(),
    };
    walk.visit_body(&module.tree.body);
    walk.found
}

struct Calls<'m> {
    module: &'m Module,
    proof: Proof,
    found: BTreeMap<String, String>,
}

impl<'a> Visitor<'a> for Calls<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            self.record(expr, call);
        }
        visitor::walk_expr(self, expr);
    }
}

impl Calls<'_> {
    fn record(&mut self, expr: &Expr, call: &ExprCall) {
        if !self.proof.loader(&call.func)
            || !call.arguments.keywords.is_empty()
            || !matches!(&*call.arguments.args, [Expr::Name(_) | Expr::FString(_)])
        {
            return;
        }
        let Some(text) = self.module.source_of(expr) else {
            return;
        };
        let at = self.module.location(&*call.func);
        let id = evidence_id(&self.module.rel, at.line, at.end_line, at.column);
        BTreeMap::insert(&mut self.found, id, text.to_owned());
    }
}

#[cfg(test)]
#[path = "literal_tests.rs"]
mod tests;
