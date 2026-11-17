// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The uses of a whole-module binding (#1415, AD-708).
//!
//! `import app.lib` binds a module object; `app.lib._priv.secret()` then uses the name `_priv` of
//! `app.lib` as `from app.lib import _priv` does, without an import statement. Each attribute load
//! on a module of the scan, through a module binding and each child module of a chain, is a use of
//! that name: `imports.rs` writes it as an import record of its own, resolved as the `from`
//! import of the name. A chain stops at the first name that is no module of the scan.
//!
//! Each other use of the binding hands the module object on: a bare load, a chain that ends at a
//! module, a namespace attribute (`__dict__`, `__all__`, `__setattr__`, `__delattr__`), a store or a
//! delete. Then the names that the module object gives are not read, and the import of that
//! binding is no proof of its names (`symbols_known` is false). A name is a binding of the whole
//! module for the scan; a local name of the same spelling counts as the binding, which can only add
//! a record or withhold a proof.

use std::collections::{HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, Stmt};
use ruff_text_size::{Ranged, TextRange};

use super::binders::{first_part, Binders};
use super::guard::Guard;
use crate::module::Module;

/// The attributes of a module that are its namespace.
const NAMESPACE: [&str; 4] = ["__dict__", "__all__", "__setattr__", "__delattr__"];

/// One attribute load on a module of the scan.
pub(super) struct Use {
    /// The range of the attribute expression that ends at the name.
    pub range: TextRange,
    /// The module and the name of it that the load reads.
    pub module: String,
    pub name: String,
    /// The load sits in the body of `if TYPE_CHECKING:`.
    pub guarded: bool,
}

/// The uses of the module bindings of each module, in the order of `modules`.
#[derive(Default)]
pub(super) struct ModuleUses {
    pub uses: Vec<Vec<Use>>,
    /// Each (source module, binding) whose module object escapes.
    pub escaped: HashSet<(String, String)>,
}

/// The uses of each whole-module binding that `imports` states.
pub(super) fn find(
    modules: &[Module],
    binders: &[Binders],
    imports: &[Record<ImportFact>],
) -> ModuleUses {
    let (names, directories) = super::imports::module_names(modules);
    let mut bindings: HashMap<&str, HashMap<&str, String>> = HashMap::new();
    let mut unread = HashSet::new();
    for record in imports {
        let ImportFact::Import(data) = &record.data else {
            continue;
        };
        let (Some(binding), None) = (data.binding.as_deref(), data.symbol.as_deref()) else {
            continue;
        };
        let (source, target) = (data.source_module.as_str(), data.target_module.as_str());
        // `import a.b` binds the package `a`; `import a.b as c` and `from a import b` bind `a.b`.
        // `import a.a` and `from a import a` give the same record: which module the name binds is
        // not read, so its uses are not either.
        let top = binding == first_part(target);
        if top && target != binding && target.rsplit('.').next() == Some(binding) {
            unread.insert((source.to_owned(), binding.to_owned()));
            continue;
        }
        let module = if top { binding } else { target };
        // Only a module of the scan can be a component; another one crosses none.
        if names.contains(module) || directories.contains(module) {
            let source = bindings.entry(source).or_default();
            source.insert(binding, module.to_owned());
        }
    }
    let mut found = ModuleUses {
        escaped: unread,
        ..ModuleUses::default()
    };
    for (module, binders) in modules.iter().zip(binders) {
        let mut walk = Walk {
            names: &names,
            directories: &directories,
            bindings: bindings.get(module.name.as_str()),
            guard: Guard::of(&module.tree, binders),
            guarded: false,
            uses: Vec::new(),
            escaped: HashSet::new(),
        };
        walk.visit_body(&module.tree.body);
        for binding in walk.escaped {
            found
                .escaped
                .insert((module.name.clone(), binding.to_owned()));
        }
        found.uses.push(walk.uses);
    }
    found
}

struct Walk<'s, 'm> {
    names: &'s HashSet<&'m str>,
    directories: &'s HashSet<&'m str>,
    bindings: Option<&'s HashMap<&'m str, String>>,
    guard: Guard,
    guarded: bool,
    uses: Vec<Use>,
    escaped: HashSet<&'m str>,
}

impl<'m> Walk<'_, 'm> {
    fn module(&self, name: &str) -> bool {
        self.names.contains(name) || self.directories.contains(name)
    }

    /// The binding and its module when `expr` is a name that binds a whole module.
    fn bound(&self, expr: &Expr) -> Option<(&'m str, String)> {
        let Expr::Name(node) = expr else {
            return None;
        };
        let (binding, module) = self.bindings?.get_key_value(node.id.as_str())?;
        Some((*binding, module.clone()))
    }

    /// A chain `binding.a.b...`: a use of each name up to the first one that is no module. True
    /// when the chain starts at a module binding.
    fn chain(&mut self, expr: &Expr) -> bool {
        let mut links = Vec::new();
        let mut at = expr;
        while let Expr::Attribute(node) = at {
            links.push(node);
            at = &node.value;
        }
        let Some((binding, mut module)) = self.bound(at) else {
            return false;
        };
        links.reverse();
        let last = links.len() - 1;
        for (index, node) in links.iter().enumerate() {
            let name = node.attr.as_str();
            let written = index == last && node.ctx != ExprContext::Load;
            if NAMESPACE.contains(&name) || written {
                self.escaped.insert(binding);
                return true;
            }
            self.uses.push(Use {
                range: node.range(),
                module: module.clone(),
                name: name.to_owned(),
                guarded: self.guarded,
            });
            let child = format!("{module}.{name}");
            if !self.module(&child) {
                return true;
            }
            module = child;
        }
        // The chain ends at a module: the module object is used as a value.
        self.escaped.insert(binding);
        true
    }
}

impl<'a> Visitor<'a> for Walk<'_, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let Stmt::If(node) = stmt else {
            return visitor::walk_stmt(self, stmt);
        };
        self.visit_expr(&node.test);
        let before = self.guarded;
        self.guarded = before || self.guard.holds(&node.test);
        self.visit_body(&node.body);
        self.guarded = before;
        for clause in &node.elif_else_clauses {
            if let Some(test) = &clause.test {
                self.visit_expr(test);
            }
            let holds = clause.test.as_ref().is_some_and(|t| self.guard.holds(t));
            self.guarded = before || holds;
            self.visit_body(&clause.body);
            self.guarded = before;
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::Attribute(_)) && self.chain(expr) {
            return;
        }
        if let Expr::Name(node) = expr {
            if node.ctx == ExprContext::Load {
                if let Some((binding, _)) = self.bound(expr) {
                    self.escaped.insert(binding);
                }
            }
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "module_uses_tests.rs"]
mod tests;
