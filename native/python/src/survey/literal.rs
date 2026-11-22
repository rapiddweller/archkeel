// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a call imports one literal module (AD-472).
//!
//! Two loader forms can give a static edge:
//!
//! - `importlib.import_module("a.b")`, when each binding of `importlib` in the module is a plain
//!   `import importlib` (no alias, no submodule import, no other binding), and there is no
//!   visible write to that loader in the scan;
//! - `__import__("a.b")`, when the module binds `__import__` nowhere.
//!
//! The call has exactly one argument and no keyword: a plain string literal with an absolute dotted
//! name, or the adjacent local assignment of AD-1026. A module that calls `globals`, `vars` or
//! `locals` proves nothing. `from importlib import
//! import_module` stays a trojan horse: its import statement is a reference to the trojan horse. Any other call,
//! alias, value or attribute use stays a `dynamic_import` gap (`hazards.rs`). A target that is
//! itself a hazard keeps its named gap as well as the edge.

use std::collections::{BTreeMap, HashMap};

use archkeel_facts::identity::{evidence_id, is_identifier};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt, StmtFunctionDef};

use super::binders::Binders;
use crate::module::Module;

/// What one module proves about the names of the two import functions.
#[derive(Default)]
pub(super) struct Proof {
    importlib: bool,
    dunder: bool,
    local: HashMap<*const ExprCall, String>,
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
            local: HashMap::new(),
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
        match &*call.arguments.args {
            [arg @ Expr::StringLiteral(_)] => member(arg),
            [Expr::Name(_)] => HashMap::get(&self.local, &std::ptr::from_ref(call)).cloned(),
            _ => None,
        }
    }

    pub(super) fn prove_local(&mut self, tree: &ModModule, loader_unchanged: bool) {
        if !self.importlib || !loader_unchanged {
            return;
        }
        let after_import = tree.body.iter().skip_while(
            |stmt| !matches!(stmt, Stmt::Import(node) if node.names.iter().any(plain_alias)),
        );
        self.local = after_import
            .filter_map(|stmt| match stmt {
                Stmt::FunctionDef(def) if !def.is_async => self.local_target(def),
                _ => None,
            })
            .collect();
    }

    fn local_target(&self, def: &StmtFunctionDef) -> Option<(*const ExprCall, String)> {
        // No statement can run between the local store and the load of the argument.
        let [Stmt::Assign(assign), Stmt::Return(ret)] = def.body.as_slice() else {
            return None;
        };
        let [Expr::Name(binding)] = assign.targets.as_slice() else {
            return None;
        };
        let Expr::Call(call) = ret.value.as_deref()? else {
            return None;
        };
        let [Expr::Name(arg)] = &*call.arguments.args else {
            return None;
        };
        if binding.id != arg.id || !self.loader(&call.func) || !call.arguments.keywords.is_empty() {
            return None;
        }
        Some((std::ptr::from_ref(call), member(&assign.value)?))
    }
}

fn plain_alias(alias: &ruff_python_ast::Alias) -> bool {
    alias.asname.is_none() && alias.name.as_str() == "importlib"
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
            let plain = node.names.iter().filter(|alias| plain_alias(alias));
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
