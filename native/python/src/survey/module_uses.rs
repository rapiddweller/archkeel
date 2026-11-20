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
use ruff_python_ast::{Comprehension, Expr, ExprCall, ExprContext, Stmt};
use ruff_text_size::{Ranged, TextRange};

use super::binders::{first_part, Binders};
use super::guard::Guard;
use super::module_scopes::{definition, may_read_import, resolve, Kind, Resolved, Scope};
use crate::module::Module;

/// AD-708: a whole-module import whose module object escapes gives names that the scan does not
/// read, so it is no proof of its names.
pub(super) fn unread_names(
    records: &mut [Record<ImportFact>],
    escaped: &HashSet<(String, String)>,
) {
    for record in records {
        let ImportFact::Import(data) = &mut record.data else {
            continue;
        };
        let key = (data.source_module.as_str().to_owned(), data.binding.clone());
        let (source, Some(binding)) = key else {
            continue;
        };
        if data.symbol.is_none() && escaped.contains(&(source, binding)) {
            data.symbols_known = false;
        }
    }
}

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
    let (names, directories) = module_names(modules);
    let mut bindings: HashMap<&str, HashMap<&str, HashSet<String>>> = HashMap::new();
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
            source.entry(binding).or_default().insert(module.to_owned());
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
            scopes: vec![Scope::of(Kind::Module, &module.tree.body, None)],
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

/// The modules of the scan, and each dotted prefix of one: a package directory, also without
/// `__init__.py` (AD-450).
pub(super) fn module_names(modules: &[Module]) -> (HashSet<&str>, HashSet<&str>) {
    let names: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    let directories = (names.iter())
        .flat_map(|name| name.match_indices('.').map(move |(at, _)| &name[..at]))
        .collect();
    (names, directories)
}

struct Walk<'s, 'm> {
    names: &'s HashSet<&'m str>,
    directories: &'s HashSet<&'m str>,
    bindings: Option<&'s HashMap<&'m str, HashSet<String>>>,
    guard: Guard,
    guarded: bool,
    /// The scopes that enclose the walk, the module first (#1506).
    scopes: Vec<Scope>,
    uses: Vec<Use>,
    escaped: HashSet<&'m str>,
}

impl<'m> Walk<'_, 'm> {
    fn module(&self, name: &str) -> bool {
        self.names.contains(name) || self.directories.contains(name)
    }

    /// What a name of a module binding reads at its place (#1506): the module, when only imports
    /// of one module bind it in its scope; maybe the module, when other bindings or other imports
    /// bind it too; nothing, when only other bindings bind it there.
    fn bound(&self, expr: &Expr) -> Option<Bound<'m>> {
        let Expr::Name(node) = expr else {
            return None;
        };
        let (binding, modules) = self.bindings?.get_key_value(node.id.as_str())?;
        match resolve(&self.scopes, node.id.as_str()) {
            Resolved::Imported if modules.len() == 1 => {
                Some(Bound::Module(binding, modules.iter().next()?.clone()))
            }
            Resolved::Imported | Resolved::Either => Some(Bound::Either(binding)),
            Resolved::Value | Resolved::Unbound => None,
        }
    }

    fn scoped(&mut self, scope: Scope, walk: impl FnOnce(&mut Self)) {
        self.scopes.push(scope);
        walk(self);
        self.scopes.pop();
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
        let (binding, mut module) = match self.bound(at) {
            None => return false,
            Some(Bound::Module(binding, module)) => (binding, module),
            // The name may be the module: its uses are not read.
            Some(Bound::Either(binding)) => {
                self.escaped.insert(binding);
                return true;
            }
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

/// What a name of a module binding reads.
enum Bound<'m> {
    Module(&'m str, String),
    Either(&'m str),
}

impl<'a> Visitor<'a> for Walk<'_, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Some((scope, body)) = definition(self, stmt) {
            return self.scoped(scope, |walk| walk.visit_body(body));
        }
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
        if matches!(expr, Expr::Name(node) if node.ctx == ExprContext::Load) {
            if let Some(Bound::Module(binding, _) | Bound::Either(binding)) = self.bound(expr) {
                self.escaped.insert(binding);
            }
        }
        let scope = match expr {
            Expr::Lambda(node) => {
                if let Some(parameters) = &node.parameters {
                    self.visit_parameters(parameters);
                }
                let scope = Scope::lambda(node.parameters.as_deref(), &node.body);
                return self.scoped(scope, |walk| walk.visit_expr(&node.body));
            }
            Expr::ListComp(node) => Scope::comprehension(&node.generators),
            Expr::SetComp(node) => Scope::comprehension(&node.generators),
            Expr::DictComp(node) => Scope::comprehension(&node.generators),
            Expr::Generator(node) => Scope::comprehension(&node.generators),
            _ => return visitor::walk_expr(self, expr),
        };
        self.scoped(scope, |walk| visitor::walk_expr(walk, expr));
    }
}

/// A visible write to `importlib.import_module`, through an import binding or its alias.
pub(super) fn replaces_literal_loader(modules: &[Module], binders: &[Binders]) -> bool {
    modules.iter().zip(binders).any(|(module, binders)| {
        if !binders.imports_importlib {
            return false;
        }
        let tree = &module.tree;
        let mut walk = LoaderWrites {
            binders,
            scopes: vec![Scope::of(Kind::Module, &tree.body, None)],
            found: false,
        };
        walk.visit_body(&tree.body);
        walk.found
    })
}

struct LoaderWrites<'a> {
    binders: &'a Binders,
    scopes: Vec<Scope>,
    found: bool,
}

impl LoaderWrites<'_> {
    fn imported(&self, expr: &Expr, origin: &str) -> bool {
        matches!(expr, Expr::Name(name) if may_read_import(&self.scopes, name.id.as_str(), origin))
    }

    fn builtin(&self, expr: &Expr, name: &str) -> bool {
        matches!(expr, Expr::Name(node) if node.id.as_str() == name
            && self.binders.count(name).is_some()
            && resolve(&self.scopes, name) == Resolved::Unbound)
    }

    fn call(&self, call: &ExprCall) -> bool {
        let arguments = &call.arguments;
        let [first, rest @ ..] = &*arguments.args else {
            return false;
        };
        let bound_writer = match &*call.func {
            Expr::Attribute(attr)
                if matches!(attr.attr.as_str(), "__setattr__" | "__delattr__") =>
            {
                if self.imported(&attr.value, "importlib") {
                    return loader_key(first);
                }
                self.builtin(&attr.value, "object")
            }
            Expr::Attribute(attr) => {
                matches!(attr.attr.as_str(), "setattr" | "delattr")
                    && self.imported(&attr.value, "builtins")
            }
            func => {
                self.builtin(func, "setattr")
                    || self.builtin(func, "delattr")
                    || self.imported(func, "builtins.setattr")
                    || self.imported(func, "builtins.delattr")
            }
        };
        bound_writer && self.imported(first, "importlib") && rest.first().is_some_and(loader_key)
    }

    fn dictionary(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Attribute(attr) => {
                attr.attr.as_str() == "__dict__" && self.imported(&attr.value, "importlib")
            }
            Expr::Call(call) => {
                self.builtin(&call.func, "vars")
                    && matches!(&*call.arguments.args, [module] if self.imported(module, "importlib"))
            }
            _ => false,
        }
    }

    fn scoped(&mut self, scope: Scope, walk: impl FnOnce(&mut Self)) {
        self.scopes.push(scope);
        walk(self);
        self.scopes.pop();
    }

    fn comprehension<'a>(
        &mut self,
        generators: &'a [Comprehension],
        values: [Option<&'a Expr>; 2],
    ) {
        let Some((first, rest)) = generators.split_first() else {
            return;
        };
        self.visit_expr(&first.iter);
        self.scoped(Scope::comprehension(generators), |walk| {
            walk.visit_expr(&first.target);
            for test in &first.ifs {
                walk.visit_expr(test);
            }
            for generator in rest {
                walk.visit_comprehension(generator);
            }
            for value in values.into_iter().flatten() {
                walk.visit_expr(value);
            }
        });
    }
}

impl<'a> Visitor<'a> for LoaderWrites<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if self.found {
            return;
        }
        if let Some((scope, body)) = definition(self, stmt) {
            self.scoped(scope, |walk| walk.visit_body(body));
        } else {
            visitor::walk_stmt(self, stmt);
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if self.found {
            return;
        }
        self.found |= match expr {
            Expr::Attribute(node) => {
                node.ctx != ExprContext::Load
                    && node.attr.as_str() == "import_module"
                    && self.imported(&node.value, "importlib")
            }
            Expr::Subscript(node) => {
                node.ctx != ExprContext::Load
                    && loader_key(&node.slice)
                    && self.dictionary(&node.value)
            }
            Expr::Call(node) => self.call(node),
            _ => false,
        };
        if self.found {
            return;
        }
        match expr {
            Expr::Lambda(node) => {
                if let Some(parameters) = &node.parameters {
                    self.visit_parameters(parameters);
                }
                let scope = Scope::lambda(node.parameters.as_deref(), &node.body);
                self.scoped(scope, |walk| walk.visit_expr(&node.body));
            }
            Expr::ListComp(node) => self.comprehension(&node.generators, [Some(&node.elt), None]),
            Expr::SetComp(node) => self.comprehension(&node.generators, [Some(&node.elt), None]),
            Expr::Generator(node) => self.comprehension(&node.generators, [Some(&node.elt), None]),
            Expr::DictComp(node) => {
                self.comprehension(&node.generators, [node.key.as_deref(), Some(&node.value)])
            }
            _ => visitor::walk_expr(self, expr),
        }
    }
}

fn loader_key(expr: &Expr) -> bool {
    matches!(expr, Expr::StringLiteral(node) if node.value.to_str() == "import_module")
}

#[cfg(test)]
#[path = "module_uses_tests.rs"]
mod tests;
