// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites that can import a module that no `import` statement names (AD-450).
//!
//! A door or state reference is a hazard. A proven inert read keeps its import gap (AD-562).
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
//! Unproved names remain gaps (AD-539).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::binders::Binders;
use super::bound::Bound;
use super::globals_read;
use super::lazy_cover::Lazy;
use super::literal::{self, Proof};
use super::syspath;
use crate::module::Module;

use names::{doors, ANY_ATTRIBUTE, BUILTIN_DOORS, DOOR_STRINGS, IMPORT_FUNCTIONS, STATE};
pub(super) use names::{DYNAMIC, IMPORT_SYSTEM};

#[path = "hazards_inert.rs"]
mod inert;
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
    reads: &HashSet<TextRange>,
) -> Vec<Site> {
    let bound = bindings(tree);
    let inert_modules = inert::modules(&bound, &binders.unique());
    let mut walk = Walk {
        found: Vec::new(),
        bound,
        inert_modules,
        uncertain_code: Bound::of(&tree.body).opaque || reflect::deleted_code(tree),
        class_body: false,
        proof,
        reads,
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

/// The names of a door module that cannot import a module by a name given at run time (AD-472).
/// `importlib.metadata.version` reads the version from the metadata files of an installed
/// distribution, and `PackageNotFoundError` is an exception class. A reference to one of these
/// exact names is no gap; any name below it, and each other name of the module, still is.
const INERT: [&str; 2] = [
    "importlib.metadata.version",
    "importlib.metadata.PackageNotFoundError",
];

/// The gap of a qualified name: a door, the import state, or a name below one of them.
pub(super) fn hazard(name: &str) -> Option<&'static str> {
    if INERT.contains(&name) {
        return None;
    }
    let under = |entry: &&str| {
        name == *entry
            || name
                .strip_prefix(*entry)
                .is_some_and(|rest| rest.starts_with('.'))
    };
    if STATE.iter().any(under) {
        Some(IMPORT_SYSTEM)
    } else if doors().any(|door| under(&door)) {
        Some(DYNAMIC)
    } else {
        None
    }
}

/// True for a module above a hazard name, such as `sys` or `importlib.metadata`.
fn above(name: &str) -> bool {
    let prefix = format!("{name}.");
    doors().chain(STATE).any(|entry| entry.starts_with(&prefix))
}

/// The qualified names that the import statements of a module bind, in any scope.
fn bindings(tree: &ModModule) -> HashMap<String, Vec<String>> {
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
fn imported(stmt: &Stmt) -> Vec<String> {
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

struct Walk<'r> {
    found: Vec<Site>,
    bound: HashMap<String, Vec<String>>,
    inert_modules: HashMap<String, String>,
    uncertain_code: bool,
    class_body: bool,
    proof: Proof,
    /// The sources of `__globals__` that only a literal lookup reads (`globals_read.rs`).
    reads: &'r HashSet<TextRange>,
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

    /// `getattr(name, "attr")` and `getattr(name, "attr", default)` with a literal attribute that
    /// is no door string read the one attribute `name.attr` (AD-530). Any other form is read as
    /// before.
    fn literal_getattr(&mut self, call: &ruff_python_ast::ExprCall) -> bool {
        let args = &call.arguments.args;
        let named = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "getattr");
        let (Some(Expr::Name(root)), Some(Expr::StringLiteral(attr))) = (args.first(), args.get(1))
        else {
            return false;
        };
        let literal = !DOOR_STRINGS.contains(&attr.value.to_str());
        let plain = named && literal && (2..=3).contains(&args.len());
        if !plain
            || !call.arguments.keywords.is_empty()
            || self.local("getattr")
            || self.getattr_bound
            || self.bound.contains_key("getattr")
        {
            return false;
        }
        let id = root.id.as_str();
        if !self.local(id) {
            let first = |origin: String| first_hazard(origin, &[attr.value.to_str()]);
            if let Some((kind, name)) = self.origins(id).into_iter().find_map(first) {
                self.push(kind, &name, call);
            }
        }
        args.iter().skip(2).for_each(|item| self.visit_expr(item));
        true
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
        if !store(expr)
            && matches!(base, Expr::Name(name) if inert::read(&self.inert_modules, name.id.as_str(), &attributes))
        {
            return;
        }
        let reads = |at: usize, a: &str| a == "__globals__" && self.reads.contains(&ranges[at]);
        let door_at = attributes.iter().enumerate().find(|(at, a)| {
            let named =
                ANY_ATTRIBUTE.contains(a) || IMPORT_FUNCTIONS.contains(a) || **a == "__path__";
            named && !reads(*at, a)
        });
        if let Some((_, name)) = door_at {
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

/// The names that a function binds (AD-530): see `globals_locals.rs`.
fn bound_in(def: &StmtFunctionDef) -> HashSet<String> {
    super::globals_locals::local_names(def)
}

/// The first hazard on the names `origin`, `origin.a`, `origin.a.b`, ..., or a module above a
/// hazard as the value of the whole chain.
fn first_hazard(origin: String, attributes: &[&str]) -> Option<(&'static str, String)> {
    let mut name = origin;
    for attribute in attributes {
        name = format!("{name}.{attribute}");
        if let Some(kind) = hazard(&name) {
            return Some((kind, name));
        }
    }
    above(&name).then_some((DYNAMIC, name))
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
        for name in imported(stmt) {
            if name.ends_with(".code") {
                self.push(DYNAMIC, &name, stmt);
            } else if let Some(kind) = hazard(&name) {
                self.push(kind, &name, stmt);
            }
        }
        let previous = self.class_body;
        if let Stmt::FunctionDef(node) = stmt {
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
                    && !self.reads.contains(&node.range()) =>
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

/// The sites that the lazy import proof covers (`lazy.rs`) are no hazard when `lazy` is given.
pub(super) fn split(modules: &[Module], binders: &[Binders], lazy: Option<&[Lazy]>) -> Split {
    let (mut literals, mut found) = (Vec::new(), Vec::new());
    let reads = globals_read::inert_reads(modules);
    for (index, (module, binders)) in modules.iter().zip(binders).enumerate() {
        let proof = literal::Proof::of(&module.tree, binders);
        let covered = lazy.map(|all| &all[index]);
        for (range, target) in covered.iter().flat_map(|item| &item.targets) {
            literals.push((index, *range, target.clone()));
        }
        for site in sites(&module.tree, proof, binders, &reads[index]) {
            let exempt = covered.iter().flat_map(|item| &item.exempt);
            if exempt
                .into_iter()
                .any(|range| range.contains_range(site.range))
            {
                continue;
            }
            match site.kind {
                LITERAL => literals.push((index, site.range, site.detail)),
                _ => found.push((index, site)),
            }
        }
    }
    (literals, found)
}
