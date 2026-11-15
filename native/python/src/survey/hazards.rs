// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites that can import a module that no `import` statement names (AD-450).
//!
//! A reference to a hazard name is the hazard: a call, an alias import, an attribute read, a
//! value or a write. A name resolves through the import statements of the module, in any scope:
//! `import sys as s` makes `s.path` the name `sys.path`. A name that no import binds resolves to
//! itself, so `sys.path` is `sys.path` also without `import sys`.
//!
//! - A dynamic import is a reference to a door: a standard-library name that imports a module
//!   from a value or runs text (`DOORS`), a builtin such as `exec`, or an attribute with the name
//!   of an import function on any value.
//! - An import-system change is a reference to the state of the import system (`STATE`) or a
//!   write to a package `__path__`.
//! - A module above a hazard name (`sys`, `importlib`, `builtins`) that is used as a value, not as
//!   the base of an attribute, is a dynamic import too: `getattr(sys, "path")` and `x = importlib`
//!   reach any name of it. An attribute `sys`, `builtins` or `importlib` of any value is the same.
//!
//! Except for `code` (AD-539), the walk finds names, not scoped bindings. A name that a function
//! binds as a parameter or a local, and that no import binds, is a local value and no door
//! (AD-530). `getattr(module, "name")` with a literal name reads the one attribute `module.name`.
//! A read of `__globals__` that only a lookup of a literal key reads is no site
//! (`globals_read.rs`).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::binders::Binders;
use super::bound::Bound;
use super::globals_read;
use super::literal::{self, Proof};
use super::syspath;
use crate::module::Module;

use names::{
    above, first_hazard, hazard, ANY_ATTRIBUTE, BUILTIN_DOORS, DOOR_STRINGS, IMPORT_FUNCTIONS,
};
pub(super) use names::{namespace_hazard, DYNAMIC, IMPORT_SYSTEM};

#[path = "hazards_binds.rs"]
mod binds;
#[path = "hazards_names.rs"]
mod names;
#[path = "hazards_reflect.rs"]
mod reflect;

/// A proven literal import call: a static edge, not a gap (AD-472, `literal.rs`).
pub(super) const LITERAL: &str = "literal_import";

/// One site: its gap, a short text and its range.
pub(super) struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
}

/// The sites of a module, in source order.
pub(super) fn sites(
    tree: &ModModule,
    proof: Proof,
    binders: &Binders,
    inert: &HashSet<TextRange>,
) -> Vec<Site> {
    let mut walk = Walk {
        found: Vec::new(),
        bound: binds::bindings(tree),
        uncertain_code: Bound::of(&tree.body).opaque || reflect::deleted_code(tree),
        class_body: false,
        proof,
        inert,
        locals: Vec::new(),
        getattr_bound: !Bound::of(&tree.body).unbound("getattr"),
    };
    for stmt in &tree.body {
        // AD-538: an expression statement of the module body that appends a directory of the
        // snapshot to `sys.path` is a candidate; the survey settles it with the whole scan.
        match syspath::levels(stmt, tree, binders) {
            Some(count) => walk.found.push(Site {
                kind: syspath::PATH_WRITE,
                detail: count.to_string(),
                range: stmt.range(),
            }),
            None => walk.visit_stmt(stmt),
        }
    }
    walk.found
}

struct Walk<'i> {
    found: Vec<Site>,
    bound: HashMap<String, Vec<String>>,
    uncertain_code: bool,
    class_body: bool,
    proof: Proof,
    /// The sources of `__globals__` that are inert (`globals_read.rs`).
    inert: &'i HashSet<TextRange>,
    /// The names that each enclosing function binds, the innermost last.
    locals: Vec<HashSet<String>>,
    /// The module binds `getattr` itself: a call of it is no read of an attribute.
    getattr_bound: bool,
}

impl Walk<'_> {
    fn push(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        self.found.push(Site {
            kind,
            detail: detail.to_owned(),
            range: node.range(),
        });
    }

    /// The qualified origins of a plain name: its import bindings, else the name itself.
    fn origins(&self, name: &str) -> Vec<String> {
        if name == "code"
            && !self.uncertain_code
            && !self.class_body
            && !self.bound.contains_key(name)
        {
            return Vec::new();
        }
        self.bound
            .get(name)
            .cloned()
            .unwrap_or_else(|| vec![name.to_owned()])
    }

    /// True when a function binds `id` and no import binds it: a local value, no door (AD-530).
    fn local(&self, id: &str) -> bool {
        !self.bound.contains_key(id) && self.locals.iter().any(|names| names.contains(id))
    }

    /// A plain name that is not the base of an attribute.
    fn name(&mut self, id: &str, expr: &Expr) {
        if self.local(id) {
            return;
        }
        if BUILTIN_DOORS.contains(&id) || IMPORT_FUNCTIONS.contains(&id) {
            return self.push(DYNAMIC, id, expr);
        }
        for origin in self.origins(id) {
            if let Some(kind) = hazard(&origin) {
                return self.push(kind, &origin, expr);
            }
            if above(&origin) {
                return self.push(DYNAMIC, &origin, expr);
            }
        }
    }

    /// An attribute chain `base.a.b`: the first hazard on it, or a module above a hazard as
    /// the value of the whole chain.
    fn chain(&mut self, expr: &Expr) {
        let mut attributes = Vec::new();
        let mut ranges = Vec::new();
        let mut base = expr;
        while let Expr::Attribute(node) = base {
            attributes.push(node.attr.as_str());
            ranges.push(node.range());
            base = &node.value;
        }
        attributes.reverse();
        ranges.reverse();
        let reads = |at: usize, a: &str| a == "__globals__" && self.inert.contains(&ranges[at]);
        let hazard_at = attributes.iter().enumerate().find(|(at, a)| {
            let named =
                ANY_ATTRIBUTE.contains(a) || IMPORT_FUNCTIONS.contains(a) || **a == "__path__";
            named && !reads(*at, a)
        });
        if let Some((_, name)) = hazard_at {
            let state = ["meta_path", "path_hooks", "path_importer_cache", "__path__"];
            let kind = if state.contains(name) {
                IMPORT_SYSTEM
            } else {
                DYNAMIC
            };
            if *name != "__path__" || store(expr) {
                return self.push(kind, name, expr);
            }
        }
        if attributes.contains(&"code") && reflect::module(base, &self.bound) {
            return self.push(DYNAMIC, "code", expr);
        }
        let Expr::Name(root) = base else {
            return self.visit_expr(base);
        };
        let id = root.id.as_str();
        if self.local(id) {
            return;
        }
        if BUILTIN_DOORS.contains(&id) || IMPORT_FUNCTIONS.contains(&id) {
            return self.push(DYNAMIC, id, expr);
        }
        let dunder = attributes
            .iter()
            .any(|a| a.starts_with("__") && a.ends_with("__"));
        for origin in self.origins(id) {
            let door = dunder && (hazard(&origin).is_some() || above(&origin));
            if let Some((kind, name)) = first_hazard(origin.clone(), &attributes) {
                return self.push(kind, &name, expr);
            }
            if door {
                // A dunder attribute of a door module, such as `sys.__getattribute__`.
                return self.push(DYNAMIC, &origin, expr);
            }
        }
    }
}

impl Walk<'_> {
    /// `getattr(name, "attr")` and `getattr(name, "attr", default)` with a literal attribute that
    /// is no door string read the one attribute `name.attr` (AD-530). The site is that attribute's
    /// hazard, if it has one; the module `name` is not read as a value. Any other form is read as
    /// before.
    fn literal_getattr(&mut self, call: &ruff_python_ast::ExprCall) -> bool {
        let args = &call.arguments.args;
        let named = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "getattr");
        let (Some(Expr::Name(root)), Some(Expr::StringLiteral(attr))) = (args.first(), args.get(1))
        else {
            return false;
        };
        let literal = !DOOR_STRINGS.contains(&attr.value.to_str());
        if !(named
            && literal
            && (2..=3).contains(&args.len())
            && call.arguments.keywords.is_empty())
            || self.local("getattr")
            || self.getattr_bound
            || self.bound.contains_key("getattr")
        {
            return false;
        }
        let id = root.id.as_str();
        if !self.local(id) {
            let first = |origin: String| first_hazard(origin, &[attr.value.to_str()]);
            let found = self.origins(id).into_iter().find_map(first);
            if let Some((kind, name)) = found {
                self.push(kind, &name, call);
            }
        }
        args.iter().skip(2).for_each(|item| self.visit_expr(item));
        true
    }
}

/// The names that a function binds: its parameters and its writes, not the names of a nested
/// scope and not a comprehension variable (AD-530). A name that a `global` or `nonlocal` line
/// names is not local.
fn bound_in(def: &StmtFunctionDef) -> HashSet<String> {
    super::globals_locals::local_names(def)
}

/// True for an attribute in a write or a delete.
fn store(expr: &Expr) -> bool {
    matches!(expr, Expr::Attribute(node) if node.ctx != ExprContext::Load)
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::ImportFrom(node)
            if node.level > 0 && node.names.iter().any(|alias| alias.name.as_str() == "code"))
        {
            self.push(DYNAMIC, "code", stmt);
        }
        for name in binds::imported(stmt) {
            if name.ends_with(".code") {
                self.push(DYNAMIC, &name, stmt);
            } else if let Some(kind) = hazard(&name) {
                self.push(kind, &name, stmt);
            }
        }
        let previous = self.class_body;
        if let Stmt::FunctionDef(node) = stmt {
            // The decorators, the defaults and the annotations run in the enclosing scope.
            node.decorator_list
                .iter()
                .for_each(|item| self.visit_decorator(item));
            if let Some(params) = &node.type_params {
                self.visit_type_params(params);
            }
            self.visit_parameters(&node.parameters);
            node.returns.iter().for_each(|item| self.visit_expr(item));
            self.class_body = false;
            self.locals.push(bound_in(node));
            self.visit_body(&node.body);
            self.locals.pop();
            self.class_body = previous;
            return;
        }
        if matches!(stmt, Stmt::ClassDef(_)) {
            self.class_body = true;
        }
        visitor::walk_stmt(self, stmt);
        self.class_body = previous;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            // AD-472: only the callee of a proven literal call is exempt; its one argument is a
            // string literal, so nothing below the call is left to read.
            Expr::Call(call) => match self.proof.target(call) {
                Some(target) => {
                    self.push(LITERAL, &target, expr);
                    if let Some(kind) = hazard(&target) {
                        self.push(kind, &target, expr);
                    }
                }
                None if !reflect::code(expr, &self.bound) && self.literal_getattr(call) => {}
                None => {
                    if reflect::code(expr, &self.bound) {
                        self.push(DYNAMIC, "code", expr);
                    }
                    // `vars()` without an argument is the namespace of the caller.
                    let bare = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "vars");
                    if bare && call.arguments.is_empty() {
                        self.push(DYNAMIC, "vars", expr);
                    }
                    visitor::walk_expr(self, expr);
                }
            },
            Expr::Subscript(_) if reflect::code(expr, &self.bound) => {
                self.push(DYNAMIC, "code", expr);
                visitor::walk_expr(self, expr);
            }
            Expr::Attribute(_) => self.chain(expr),
            Expr::StringLiteral(node)
                if DOOR_STRINGS.contains(&node.value.to_str())
                    && !self.inert.contains(&node.range()) =>
            {
                self.push(DYNAMIC, node.value.to_str(), expr);
            }
            Expr::Name(node) if node.id.as_str() == "__path__" => {
                if node.ctx != ExprContext::Load {
                    self.push(IMPORT_SYSTEM, "__path__", expr);
                }
            }
            Expr::Name(node) if node.ctx == ExprContext::Load => self.name(node.id.as_str(), expr),
            _ => visitor::walk_expr(self, expr),
        }
    }
}

#[cfg(test)]
#[path = "hazards_tests.rs"]
mod tests;

/// The proven literal import calls of the modules, and their hazard sites, each with the index
/// of its module.
pub(super) type Split = (Vec<(usize, TextRange, String)>, Vec<(usize, Site)>);

pub(super) fn split(modules: &[Module], binders: &[Binders]) -> Split {
    let (mut literals, mut found) = (Vec::new(), Vec::new());
    let inert = globals_read::inert_reads(modules);
    for (index, (module, binders)) in modules.iter().zip(binders).enumerate() {
        let proof = literal::Proof::of(&module.tree, binders);
        for site in sites(&module.tree, proof, binders, &inert[index]) {
            match site.kind {
                LITERAL => literals.push((index, site.range, site.detail)),
                _ => found.push((index, site)),
            }
        }
    }
    (literals, found)
}
