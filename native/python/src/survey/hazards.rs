// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites that can import a module that no `import` statement names (AD-450).
//! A door or state reference is a hazard. A proven inert read keeps its import gap (AD-574).
//! - A dynamic import is a reference to a door, builtin or import function.
//! - An import-system change is a reference to the state of the import system (`STATE`) or a
//!   write to a package `__path__`.
//! - A module above a hazard name used as a value is a dynamic import too.
//!
//! Unproved names remain gaps (AD-539).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

use super::binders::Binders;
use super::bound::Bound;
use super::globals_read;
use super::lazy_cover::Lazy;
use super::literal::{self, Proof};
use super::syspath;
use crate::module::Module;

use bind::{bindings, imported};
use names::{
    above, first_hazard, store, ANY_ATTRIBUTE, BUILTIN_DOORS, DOOR_STRINGS, IMPORT_FUNCTIONS,
};
pub(super) use names::{hazard, DYNAMIC, IMPORT_SYSTEM};

#[path = "hazards_bind.rs"]
mod bind;
#[path = "hazards_comprehension.rs"]
mod comprehension;
#[path = "hazards_door.rs"]
mod door;
#[path = "hazards_inert.rs"]
mod inert;
#[path = "hazards_names.rs"]
pub(super) mod names;
#[path = "hazards_reflect.rs"]
mod reflect;

/// A proven literal import call: a static edge, not a gap (AD-472, `literal.rs`).
pub(super) const LITERAL: &str = "literal_import";

/// One site: its gap, a short text and its range. A door site has its form, the dotted names of
/// the classes and functions that hold it, and the name that an import statement binds (AD-664).
pub(super) struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
    pub door: Option<archkeel_facts::data::DoorForm>,
    pub scope: String,
    pub binding: Option<String>,
}

/// The sites of a module, in source order.
pub(super) fn sites(
    tree: &ModModule,
    proof: Proof,
    binders: &Binders,
    reads: &HashSet<TextRange>,
) -> Vec<Site> {
    let bound = bindings(tree);
    let inert_modules = inert::modules(&bound, &binders.unique(), tree);
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
        scope: Vec::new(),
    };
    for stmt in &tree.body {
        // AD-538: an expression statement of the module body that appends a directory of the
        // snapshot to `sys.path` is a candidate; the survey settles it with the whole scan.
        match syspath::levels(stmt, tree, binders) {
            Some(count) => walk.found.push(Site {
                kind: syspath::PATH_WRITE,
                detail: count.to_string(),
                range: stmt.range(),
                door: None,
                scope: String::new(),
                binding: None,
            }),
            None => walk.visit_stmt(stmt),
        }
    }
    walk.found
}

struct Walk<'r> {
    found: Vec<Site>,
    bound: HashMap<String, Vec<String>>,
    inert_modules: HashMap<String, String>,
    uncertain_code: bool,
    class_body: bool,
    proof: Proof,
    reads: &'r HashSet<TextRange>,
    // Class namespaces are skipped by nested function and comprehension lookups.
    locals: Vec<(HashSet<String>, HashSet<String>, bool)>,
    getattr_bound: bool,
    /// The names of the classes and functions that hold the walk, outermost first.
    scope: Vec<String>,
}

impl Walk<'_> {
    fn lambda(&mut self, node: &ruff_python_ast::ExprLambda) {
        if let Some(parameters) = &node.parameters {
            self.visit_parameters(parameters);
        }
        self.locals.push((
            super::globals_locals::lambda_names(node),
            HashSet::new(),
            false,
        ));
        self.visit_expr(&node.body);
        self.locals.pop();
    }

    /// A site of a name, an attribute or an import: a door when its name is one (AD-664).
    fn push(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        let door = door::form(kind, detail);
        self.add(kind, detail, node, door);
    }

    /// A site that is never a door site: a string that names a door.
    fn push_text(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        self.add(kind, detail, node, None);
    }

    fn add(
        &mut self,
        kind: &'static str,
        detail: &str,
        node: &impl Ranged,
        door: Option<archkeel_facts::data::DoorForm>,
    ) {
        self.found.push(Site {
            kind,
            detail: detail.to_owned(),
            range: node.range(),
            door,
            scope: door.map(|_| self.scope.join(".")).unwrap_or_default(),
            binding: None,
        });
    }

    /// AD-664: the name that an import statement binds for the door site just pushed.
    fn bind_door(&mut self, stmt: &Stmt, name: &str) {
        if let Some(site) = self.found.last_mut().filter(|site| site.door.is_some()) {
            site.binding = bind::local_of(stmt, name);
        }
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
        if self.bound.contains_key(id) {
            return false;
        }
        for (depth, (names, globals, class)) in self.locals.iter().rev().enumerate() {
            if *class && depth > 0 {
                continue;
            }
            if globals.contains(id) {
                return false;
            }
            if names.contains(id) {
                return true;
            }
        }
        false
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
        if matches!(expr, Expr::Name(node) if node.ctx == ExprContext::Load)
            && inert::read(&self.inert_modules, id, &[])
        {
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
        let reads = |at: usize, a: &str| {
            matches!(a, "__globals__" | "f_globals") && self.reads.contains(&ranges[at])
        };
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
                self.bind_door(stmt, &name);
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
            let (locals, globals) = super::globals_locals::local_scope(node);
            self.locals.push((locals, globals, false));
            self.scope.push(node.name.to_string());
            self.visit_body(&node.body);
            self.scope.pop();
            self.locals.pop();
            self.class_body = previous;
            return;
        }
        if let Stmt::ClassDef(node) = stmt {
            self.class_body = true;
            node.decorator_list
                .iter()
                .for_each(|item| self.visit_decorator(item));
            if let Some(params) = &node.type_params {
                self.visit_type_params(params);
            }
            node.arguments
                .iter()
                .for_each(|item| self.visit_arguments(item));
            self.locals.push((
                HashSet::new(),
                super::globals_locals::class_blockers(&node.body),
                true,
            ));
            self.scope.push(node.name.to_string());
            self.visit_body(&node.body);
            self.scope.pop();
            self.locals.pop();
            self.class_body = previous;
            return;
        }
        visitor::walk_stmt(self, stmt);
        self.class_body = previous;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Some((first, rest, targets, values)) = comprehension::parts(expr) {
            self.visit_expr(&first.iter);
            self.locals.push((targets, HashSet::new(), false));
            self.visit_expr(&first.target);
            first.ifs.iter().for_each(|test| self.visit_expr(test));
            rest.iter().for_each(|item| self.visit_comprehension(item));
            values.into_iter().for_each(|value| self.visit_expr(value));
            self.locals.pop();
            return;
        }
        match expr {
            Expr::Lambda(node) => self.lambda(node),
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
                self.push_text(DYNAMIC, node.value.to_str(), expr);
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

#[cfg(test)]
#[path = "hazards_inert_tests.rs"]
mod inert_tests;

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
