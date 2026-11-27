// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites that can import a module that no `import` statement names (AD-450). A proven inert
//! read keeps its import gap (AD-574). Unproved names remain gaps (AD-539).
//! - A dynamic import is a reference to a trojan horse, builtin or import function, or a computed
//!   attribute name on an unproved receiver (#1967).
//! - An import-system change is a reference to `STATE` or a write to a package `__path__`.
//! - A module above a hazard name used as a value is a dynamic import too.

use std::collections::{HashMap, HashSet};
use std::mem::take;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::parse::Unread;

use super::binders::Binders;
use super::bound::Bound;
use super::literal::Proof;
use super::syspath;

use super::hazards_names::{
    self as names, above, attribute_trojan_horse, first_hazard, module_hazard,
    BUILTIN_TROJAN_HORSES, IMPORT_FUNCTIONS, TROJAN_HORSE_STRINGS,
};
pub(super) use super::hazards_names::{hazard, DYNAMIC, IMPORT_SYSTEM, LITERAL};
use bind::imported;
pub(super) use bind::{bindings, exposed};
pub(super) use comprehension::trojans as comprehension_trojans;
pub(super) use inert::{cleared, BUILTINS};
pub(super) use reexport::{table, Reexports};
pub(super) use reflect::proved;
pub(super) use trojan_horse::Site;

#[path = "hazards_annotation.rs"]
mod annotation;
#[path = "hazards_bind.rs"]
mod bind;
#[path = "hazards_comprehension.rs"]
mod comprehension;
#[path = "hazards_inert.rs"]
mod inert;
#[path = "hazards_reexport.rs"]
mod reexport;
#[path = "hazards_reflect.rs"]
pub(super) mod reflect;
#[path = "hazards_trojan_horse.rs"]
mod trojan_horse;

/// The sites of a module, in source order.
pub(super) fn sites(
    tree: &ModModule,
    proof: Proof,
    binders: &Binders,
    reads: &HashSet<TextRange>,
    reexports: &Reexports,
) -> Vec<Site> {
    let bound = bindings(tree);
    let inert_modules = inert::modules(&bound, &binders.unique(), tree);
    let code_types = inert::code_types(&bound, &binders.unique());
    let mut walk = Walk {
        found: Vec::new(),
        bound,
        inert_modules,
        code_types,
        isinstance_visible: binders.builtin_visible("isinstance"),
        uncertain_code: Bound::of(&tree.body).opaque || reflect::deleted_code(tree),
        class_body: false,
        proof,
        reads: reads.clone(),
        locals: Vec::new(),
        getattr_bound: !Bound::of(&tree.body).unbound("getattr"),
        scope: Vec::new(),
        code_aliases: reflect::code_aliases(tree),
        reexports,
        annotation: false,
        strings: annotation::Strings::of(tree),
    };
    for stmt in &tree.body {
        // AD-538: an expression statement of the module body that appends a directory of the
        // snapshot to `sys.path` is a candidate; the survey settles it with the whole scan.
        match syspath::levels(stmt, tree, binders) {
            Some(count) => {
                let site = Site::plain(syspath::PATH_WRITE, &count.to_string(), stmt.range());
                walk.found.push(site);
            }
            None => walk.visit_stmt(stmt),
        }
    }
    annotation::class::with(walk.found, tree)
}

struct Walk<'r> {
    reexports: &'r Reexports,
    annotation: bool,
    strings: annotation::Strings,
    found: Vec<Site>,
    bound: HashMap<String, Vec<String>>,
    inert_modules: HashMap<String, String>,
    code_types: HashSet<String>,
    isinstance_visible: bool,
    uncertain_code: bool,
    class_body: bool,
    proof: Proof,
    reads: HashSet<TextRange>,
    // Class namespaces are skipped by nested function and comprehension lookups.
    locals: Vec<(HashSet<String>, HashSet<String>, bool)>,
    getattr_bound: bool,
    /// The names of the classes and functions that hold the walk, outermost first.
    scope: Vec<String>,
    /// The names that the file assigns from `code` or from an attribute `code` (#1520).
    code_aliases: HashSet<String>,
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

    /// A site of a name, an attribute or an import: a trojan horse when its name is one (AD-664).
    fn push(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        let trojan_horse = trojan_horse::form(kind, detail);
        self.add(kind, detail, node, trojan_horse);
    }

    /// A site that is never a trojan horse site: a string that names a trojan horse.
    fn push_text(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        self.add(kind, detail, node, None);
    }

    fn add(
        &mut self,
        kind: &'static str,
        detail: &str,
        node: &impl Ranged,
        trojan_horse: Option<archkeel_facts::data::TrojanHorseForm>,
    ) {
        self.found.push(Site {
            kind,
            detail: detail.to_owned(),
            range: node.range(),
            trojan_horse,
            scope: self.scope.join("."),
            binding: None,
        });
    }

    /// AD-664: the name that an import statement binds for the trojan horse site just pushed.
    fn bind_trojan_horse(&mut self, stmt: &Stmt, name: &str) {
        if let Some(site) = self.found.last_mut() {
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

    /// True when a function binds `id` and no import binds it: a local value, no trojan horse (AD-530).
    fn local(&self, id: &str) -> bool {
        names::local(&self.bound, &self.locals, id)
    }

    /// `getattr(name, "attr")` and `getattr(name, "attr", default)` with a literal attribute that
    /// is no trojan horse string read the one attribute `name.attr` (AD-530). Other forms: as before.
    fn literal_getattr(&mut self, call: &ruff_python_ast::ExprCall) -> bool {
        let args = &call.arguments.args;
        let named = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "getattr");
        let (Some(Expr::Name(root)), Some(Expr::StringLiteral(attr))) = (args.first(), args.get(1))
        else {
            return false;
        };
        let literal = !TROJAN_HORSE_STRINGS.contains(&attr.value.to_str())
            && !comprehension::reflective(attr.value.to_str());
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
        let load = matches!(expr, Expr::Name(node) if node.ctx == ExprContext::Load);
        if self.local(id) || (load && inert::read(&self.inert_modules, id, &[])) {
            return;
        }
        if BUILTIN_TROJAN_HORSES.contains(&id) || IMPORT_FUNCTIONS.contains(&id) {
            return self.push(DYNAMIC, id, expr);
        }
        for origin in self.origins(id) {
            if let Some(kind) = hazard(&origin) {
                return self.push(kind, &origin, expr);
            }
            let value = self.bound.contains_key(id) && reexport::value(self.reexports, &origin);
            if above(&origin) || value {
                return self.push(DYNAMIC, &origin, expr);
            }
        }
    }

    fn call<'a>(&mut self, expr: &'a Expr, call: &'a ruff_python_ast::ExprCall) {
        match self.proof.target(call) {
            Some(target) => {
                self.push(LITERAL, &target, expr);
                if let Some(kind) = module_hazard(&target) {
                    self.push(kind, &target, expr);
                }
            }
            None if inert::code_type_check(call, &self.code_types, self.isinstance_visible) => {
                self.visit_expr(&call.arguments.args[0]);
            }
            None if !reflect::code(expr, &self.bound) && self.literal_getattr(call) => {}
            None if inert::names_no_module(call, &|id| self.origins(id)) => {
                visitor::walk_arguments(self, &call.arguments);
            }
            None => {
                if reflect::code(expr, &self.bound) {
                    self.push(DYNAMIC, "code", expr);
                }
                let bare = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "vars");
                if bare && call.arguments.is_empty() {
                    self.push(DYNAMIC, "vars", expr);
                }
                visitor::walk_expr(self, expr);
            }
        }
    }

    fn evaluated(&mut self, string: &ruff_python_ast::ExprStringLiteral) {
        let first = self.found.len();
        // The text runs in the global names of its module: no fact of the real tree applies to it.
        let outer = (
            take(&mut self.proof),
            take(&mut self.reads),
            take(&mut self.locals),
        );
        match annotation::parsed(string) {
            Ok(code) => self.visit_expr(&code),
            // CPython can evaluate a text that the parser bound refuses: a gap, never nothing.
            Err(Unread::Bound) => self.push_text(DYNAMIC, "annotation", string),
            Err(Unread::Syntax) => {}
        }
        (self.proof, self.reads, self.locals) = outer;
        for site in &mut self.found[first..] {
            site.range = string.range();
        }
    }

    /// A hazard behind a name that a module of the scan binds to a standard library module.
    fn reexported(&mut self, attributes: &[&str], expr: &Expr) {
        if let Some((kind, name)) = reexport::find(self.reexports, attributes) {
            self.push(kind, &name, expr);
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
        let store = matches!(expr, Expr::Attribute(node) if node.ctx != ExprContext::Load);
        if !store
            && matches!(base, Expr::Name(name) if inert::read(&self.inert_modules, name.id.as_str(), &attributes))
        {
            return;
        }
        let reads = |at: usize, a: &str| {
            matches!(a, "__globals__" | "f_globals") && self.reads.contains(&ranges[at])
        };
        let trojan_horse_at = attributes
            .iter()
            .enumerate()
            .find(|(at, a)| attribute_trojan_horse(&attributes, *at) && !reads(*at, a));
        if let Some((_, name)) = trojan_horse_at {
            let state = ["meta_path", "path_hooks", "path_importer_cache", "__path__"];
            let kind = if state.contains(name) {
                IMPORT_SYSTEM
            } else {
                DYNAMIC
            };
            if *name != "__path__" || store {
                return self.push(kind, name, expr);
            }
        }
        if attributes.contains(&"code") && reflect::module(base, &self.bound) {
            return self.push(DYNAMIC, "code", expr);
        }
        if reflect::runner(base, &attributes, &self.code_aliases) {
            return self.push(DYNAMIC, "code", expr);
        }
        let Expr::Name(root) = base else {
            self.reexported(&attributes, expr);
            return self.visit_expr(base);
        };
        let id = root.id.as_str();
        if self.local(id) {
            self.reexported(&attributes, expr);
            return;
        }
        if BUILTIN_TROJAN_HORSES.contains(&id) || IMPORT_FUNCTIONS.contains(&id) {
            return self.push(DYNAMIC, id, expr);
        }
        let dunder = attributes
            .iter()
            .any(|a| a.starts_with("__") && a.ends_with("__"));
        for origin in self.origins(id) {
            let hit = reexport::find_from(self.reexports, self.bound.get(id), &origin, &attributes);
            if let Some((kind, name)) = hit {
                return self.push(kind, &name, expr);
            }
            let trojan_horse = dunder && (hazard(&origin).is_some() || above(&origin));
            if let Some((kind, name)) = first_hazard(origin.clone(), &attributes) {
                return self.push(kind, &name, expr);
            }
            if trojan_horse {
                // A dunder attribute of a trojan horse module, such as `sys.__getattribute__`.
                return self.push(DYNAMIC, &origin, expr);
            }
        }
        self.reexported(&attributes, expr);
    }
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if annotation::writes_annotations(stmt) {
            self.push_text(DYNAMIC, "__annotations__", stmt);
        }
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
                self.bind_trojan_horse(stmt, &name);
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
            node.returns.iter().for_each(|r| self.visit_annotation(r));
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

    fn visit_annotation(&mut self, expr: &'a Expr) {
        let outer = std::mem::replace(&mut self.annotation, true);
        self.visit_expr(expr);
        self.annotation = outer;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match annotation::evaluated(expr, self.annotation, &self.strings) {
            annotation::Text::None => {}
            annotation::Text::Literal(text) => self.evaluated(text),
            annotation::Text::Held(texts) => texts.iter().for_each(|text| self.evaluated(text)),
            annotation::Text::Opaque => self.push_text(DYNAMIC, "annotation", expr),
        }
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
            // The proved call converts the loader use to an import edge.
            Expr::Call(call) => self.call(expr, call),
            Expr::Subscript(_) if reflect::code(expr, &self.bound) => {
                self.push(DYNAMIC, "code", expr);
                visitor::walk_expr(self, expr);
            }
            Expr::Attribute(_) => self.chain(expr),
            Expr::Subscript(node) if self.annotation && annotation::literal(&node.value) => {
                self.visit_expr(&node.value);
                self.annotation = false;
                self.visit_expr(&node.slice);
                self.annotation = true;
            }
            Expr::StringLiteral(node)
                if TROJAN_HORSE_STRINGS.contains(&node.value.to_str())
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

/// Proven imports and hazards, each keyed by its module index.
pub(super) type Split = (Vec<(usize, TextRange, String)>, Vec<(usize, Site)>);
