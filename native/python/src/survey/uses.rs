// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The modules of the scan whose namespace may change under a route (AD-504): one visitor of the
//! uses of a module binding, with a closed list of harmless uses.
//!
//! A route through a module is proven only for the namespace that the module's own statements
//! build. A name that an import binds to a module of the scan (or to an imported name of unknown
//! kind) *escapes* in each use but one: a direct attribute load `name.attr`, and a call
//! `name.attr(...)`, when `attr` is no namespace (`__dict__`, `__all__`, `__setattr__`,
//! `__delattr__`) and no child module. Each other use is an escape, so the visitor fails closed:
//! an attribute store, `+=`, `del`, a call that passes the name (`setattr`, `getattr`, `vars`,
//! `patch(lib)`), an assignment of the bare name, a container, a conditional, a return, a
//! comprehension target, and an import of `__dict__` or `__all__` from the module. An escaped
//! module and each module below it withhold every route through them.
//!
//! An imported name is harmless when its origin is a `def`, a `class`, a literal or a display.
//! These values are not modules, so their use cannot directly change a module namespace.
//! A write through `sys.modules`, a computed import, `globals()` of another module, a writer
//! outside the scan roots and a C extension are not seen here: the first two are survey gaps
//! (AD-450); the rest is listed in `docs/known-limits.md`.

use std::collections::{HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprAttribute, ExprContext, Stmt};

use super::bound::{Bound, Kind};
use super::uses_scan::{class_patch, Scan};
use crate::module::Module;

/// The attributes of a module that are its namespace.
const NAMESPACE: [&str; 4] = ["__dict__", "__all__", "__setattr__", "__delattr__"];

/// What one imported name is in a module.
enum Binding {
    /// `import a.b` (the name `a`), `import a.b as c`, `from a import b` where `a.b` is a module.
    Module(String),
    /// `from a import x` where `a.x` is no module of the scan: the origin of the name.
    Attribute(String, String),
}

/// The modules that a use of a module binding in `modules` can change.
pub(super) fn escaped(modules: &[Module], imports: &[Record<ImportFact>]) -> HashSet<String> {
    let binders: Vec<_> = modules
        .iter()
        .map(|module| super::binders::Binders::of(&module.tree))
        .collect();
    let (_, sites) = super::hazards::split(modules, &binders, None);
    let mut scan = Scan {
        modules: modules.iter().map(|module| module.name.as_str()).collect(),
        hazardous: sites
            .iter()
            .filter(|(_, site)| namespace_hazard(&site.detail))
            .map(|(index, _)| modules[*index].name.as_str())
            .collect(),
        typing_values: HashSet::new(),
        class_patch: false,
        bounds: modules
            .iter()
            .map(|module| (module.name.as_str(), Bound::of(&module.tree.body)))
            .collect(),
        imports: HashMap::new(),
    };
    let mut bindings: HashMap<&str, HashMap<&str, Vec<Binding>>> = HashMap::new();
    let mut found = HashSet::new();
    for record in imports {
        let data = record.data.data();
        let (source, target) = (data.source_module.as_str(), data.target_module.as_str());
        let Some(binding) = data.binding.as_deref().filter(|name| *name != "*") else {
            continue;
        };
        let symbol = data.symbol.as_deref();
        scan.imports
            .entry((source, binding))
            .or_default()
            .push((target, symbol));
        if symbol.is_some_and(|name| NAMESPACE.contains(&name)) {
            found.extend(scan.below(target));
        }
        let kind = match symbol {
            None if binding == target.split('.').next().unwrap_or(target) => {
                Binding::Module(binding.to_owned())
            }
            None => Binding::Module(target.to_owned()),
            Some(name) => Binding::Attribute(target.to_owned(), name.to_owned()),
        };
        bindings
            .entry(source)
            .or_default()
            .entry(binding)
            .or_default()
            .push(kind);
    }
    scan.class_patch = class_patch(&scan, modules);
    scan.typing_values = typing_values(modules, imports, &scan);
    for module in modules {
        let mut walk = Uses {
            scan: &scan,
            names: bindings.get(module.name.as_str()),
            found: &mut found,
        };
        walk.visit_body(&module.tree.body);
    }
    found
}

fn namespace_hazard(detail: &str) -> bool {
    matches!(
        detail,
        "globals"
            | "locals"
            | "vars"
            | "exec"
            | "eval"
            | "compile"
            | "__globals__"
            | "__builtins__"
            | "sys.__dict__"
    ) || detail == "builtins"
        || detail.starts_with("builtins.")
        || detail == "sys.modules"
        || detail.starts_with("sys.modules.")
}

/// A typing factory that is referenced only as a factory cannot be patched by a scanned use.
type Factory = (String, String);

fn typing_factory(scan: &Scan<'_>, module: &str, name: &str, depth: usize) -> Option<Factory> {
    let bound = scan.bounds.get(module)?;
    if depth >= 8
        || bound.getattr
        || bound.attribute_write
        || scan.hazardous.contains(module)
        || scan.modules.contains(format!("{module}.{name}").as_str())
        || bound.kind(name) != Some(Kind::Import)
    {
        return None;
    }
    let [(target, Some(symbol))] = scan.imports.get(&(module, name))?.as_slice() else {
        return None;
    };
    if matches!(*target, "typing" | "typing_extensions") && factory_form(symbol).is_some() {
        return Some(((*target).to_owned(), (*symbol).to_owned()));
    }
    typing_factory(scan, target, symbol, depth + 1)
}

/// The factories whose subscript gives an alias object whatever its arguments are: `Annotated`
/// always, `Optional[X]` is `Union[X, None]` and `Literal[...]` keeps its values. `Union[X]` is
/// `X` and `Union[X, X]` is `X`, so `Union` needs literal arguments.
fn any_argument(name: &str) -> bool {
    matches!(name, "Annotated" | "Optional" | "Literal")
}

fn factory_form(name: &str) -> Option<bool> {
    match name {
        "Annotated" | "Union" | "Optional" | "Literal" => Some(true),
        "TypeVar" | "NewType" => Some(false),
        _ => None,
    }
}

fn typing_values(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    scan: &Scan<'_>,
) -> HashSet<(String, String)> {
    let mut aliases = HashMap::new();
    let mut blocked = HashSet::new();
    let mut blocked_modules = HashSet::new();
    let class_write = scan.bounds.values().any(|bound| bound.attribute_write)
        || super::uses_typing_guard::withheld(modules);
    for record in imports {
        let data = record.data.data();
        let target = data.target_module.as_str();
        if !matches!(target, "typing" | "typing_extensions") {
            continue;
        }
        if data.symbol.as_deref().is_none_or(|symbol| symbol == "*") {
            blocked_modules.insert(target.to_owned());
            continue;
        }
        let (Some(symbol), Some(binding)) = (data.symbol.as_deref(), data.binding.as_deref())
        else {
            continue;
        };
        if factory_form(symbol).is_some()
            && scan
                .bounds
                .get(data.source_module.as_str())
                .and_then(|b| b.kind(binding))
                != Some(Kind::Import)
        {
            blocked.insert((target.to_owned(), symbol.to_owned()));
        }
    }
    for (module, name) in scan.imports.keys() {
        if let Some(factory) = typing_factory(scan, module, name, 0) {
            aliases.insert(((*module).to_owned(), (*name).to_owned()), factory);
        }
    }
    for module in modules {
        let names = aliases
            .iter()
            .filter_map(|((owner, name), factory)| {
                (owner == &module.name).then_some((name.as_str(), factory))
            })
            .collect();
        let mut watch = TypingWatch {
            names,
            blocked: &mut blocked,
        };
        watch.visit_body(&module.tree.body);
    }
    let mut values = HashSet::new();
    for module in modules {
        let Some(bound) = scan.bounds.get(module.name.as_str()) else {
            continue;
        };
        for (name, head, form, inert) in module
            .tree
            .body
            .iter()
            .flat_map(|stmt| typing_candidates(stmt, bound))
        {
            let key = (module.name.clone(), head.to_owned());
            let Some(factory) = aliases.get(&key) else {
                continue;
            };
            if factory_form(&factory.1) == Some(form)
                && (inert || any_argument(&factory.1))
                && !blocked.iter().any(|(_, name)| name == &factory.1)
                && blocked_modules.is_empty()
                && !class_write
            {
                values.insert((module.name.clone(), name.to_owned()));
            }
        }
    }
    values
}

/// A typing alias candidate: its name, the head name, the form (subscript or call) and whether
/// each argument is a literal or an unbound builtin type.
type Candidate<'a> = (&'a str, &'a str, bool, bool);

fn typing_candidates<'a>(stmt: &'a Stmt, bound: &Bound) -> Vec<Candidate<'a>> {
    let (targets, value): (Vec<&Expr>, &Expr) = match stmt {
        Stmt::Assign(node) => (node.targets.iter().collect(), &node.value),
        Stmt::AnnAssign(node) => match &node.value {
            Some(value) => (vec![&node.target], value),
            None => return Vec::new(),
        },
        _ => return Vec::new(),
    };
    let (head, form, inert) = match value {
        Expr::Subscript(node) => (&*node.value, true, bound.inert_typing_arg(&node.slice)),
        Expr::Call(node) => {
            let inert = node.arguments.keywords.is_empty()
                && node
                    .arguments
                    .args
                    .iter()
                    .all(|arg| bound.inert_typing_arg(arg));
            if !inert {
                return Vec::new();
            }
            (&*node.func, false, true)
        }
        _ => return Vec::new(),
    };
    let Expr::Name(head) = head else {
        return Vec::new();
    };
    targets
        .into_iter()
        .filter_map(|target| match target {
            Expr::Name(name) => Some((name.id.as_str(), head.id.as_str(), form, inert)),
            _ => None,
        })
        .collect()
}

struct TypingWatch<'a> {
    names: HashMap<&'a str, &'a Factory>,
    blocked: &'a mut HashSet<Factory>,
}

impl<'a> Visitor<'a> for TypingWatch<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Subscript(node) if self.factory(&node.value, true) => {
                self.visit_expr(&node.slice);
                return;
            }
            Expr::Call(node) if self.factory(&node.func, false) => {
                self.visit_arguments(&node.arguments);
                return;
            }
            Expr::Name(name) => {
                if let Some(factory) = self.names.get(name.id.as_str()) {
                    self.blocked.insert((*factory).clone());
                }
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

impl TypingWatch<'_> {
    fn factory(&self, expr: &Expr, form: bool) -> bool {
        let Expr::Name(name) = expr else { return false };
        self.names
            .get(name.id.as_str())
            .is_some_and(|factory| factory_form(&factory.1) == Some(form))
    }
}

struct Uses<'s, 'm> {
    scan: &'s Scan<'m>,
    names: Option<&'s HashMap<&'m str, Vec<Binding>>>,
    found: &'s mut HashSet<String>,
}

impl Uses<'_, '_> {
    /// The modules that the expression denotes (the module itself, not a name inside it), and
    /// whether each of them is certain (a module binding) or unknown (an imported name).
    fn denotes(&self, expr: &Expr) -> Vec<String> {
        match expr {
            Expr::Name(node) => {
                let kinds = self.names.and_then(|names| names.get(node.id.as_str()));
                kinds
                    .into_iter()
                    .flatten()
                    .filter_map(|kind| self.name(kind))
                    .collect()
            }
            Expr::Attribute(node) => self
                .exact(&node.value)
                .into_iter()
                .map(|module| format!("{module}.{}", node.attr.as_str()))
                .filter(|child| self.scan.modules.contains(child.as_str()))
                .collect(),
            Expr::Call(_) => literal_import(expr)
                .filter(|name| self.scan.modules.contains(name.as_str()))
                .into_iter()
                .collect(),
            _ => Vec::new(),
        }
    }

    /// The modules that a binding may denote; a proven non-module denotes none.
    fn name(&self, kind: &Binding) -> Option<String> {
        match kind {
            Binding::Module(module) => Some(module.clone()),
            Binding::Attribute(anchor, symbol) => {
                (!self.scan.callable(anchor, symbol, 0)).then(|| anchor.clone())
            }
        }
    }

    /// The modules that a chain certainly denotes: bindings of a module, not of an unknown name.
    fn exact(&self, expr: &Expr) -> Vec<String> {
        match expr {
            Expr::Name(node) => {
                let kinds = self.names.and_then(|names| names.get(node.id.as_str()));
                let modules = kinds.into_iter().flatten();
                modules
                    .filter_map(|kind| match kind {
                        Binding::Module(module) => Some(module.clone()),
                        Binding::Attribute(..) => None,
                    })
                    .collect()
            }
            _ => self.denotes(expr),
        }
    }

    fn escape(&mut self, modules: Vec<String>) {
        for module in modules {
            self.found.extend(self.scan.below(&module));
        }
    }
}

impl Uses<'_, '_> {
    /// An attribute of a module binding: true when the use is decided (harmless or escaped).
    fn attribute(&mut self, node: &ExprAttribute, expr: &Expr) -> bool {
        let base = self.denotes(&node.value);
        if base.is_empty() {
            return false;
        }
        let load = node.ctx == ExprContext::Load && !NAMESPACE.contains(&node.attr.as_str());
        let child = self.denotes(expr);
        // The one harmless use: a direct load of a name that is no module. A load of a child
        // module is a bare use of that module; each other use escapes the base.
        if !load {
            self.escape(base);
        } else if !child.is_empty() {
            self.escape(child);
        }
        true
    }
}

impl<'a> Visitor<'a> for Uses<'_, '_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Attribute(node) = expr {
            if self.attribute(node, expr) {
                return;
            }
        }
        let bare = self.denotes(expr);
        if !bare.is_empty() {
            self.escape(bare);
        }
        visitor::walk_expr(self, expr);
    }
}

/// The module that `importlib.import_module("m")` or `__import__("m")` names.
fn literal_import(expr: &Expr) -> Option<String> {
    let Expr::Call(call) = expr else {
        return None;
    };
    let name = match &*call.func {
        Expr::Name(node) => node.id.to_string(),
        Expr::Attribute(node) => node.attr.to_string(),
        _ => return None,
    };
    if name != "import_module" && name != "__import__" {
        return None;
    }
    match call.arguments.args.first()? {
        Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
        _ => None,
    }
}

#[cfg(test)]
#[path = "uses_tests.rs"]
mod tests;
