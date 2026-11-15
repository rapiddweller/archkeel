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
use ruff_python_ast::{Expr, ExprAttribute, ExprContext};

use super::bound::{Bound, Kind};
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

/// The module and the symbol that an import names.
type Origin<'m> = (&'m str, Option<&'m str>);

/// The facts that the visitor reads about the scan.
struct Scan<'m> {
    modules: HashSet<&'m str>,
    bounds: HashMap<&'m str, Bound>,
    hazardous: HashSet<&'m str>,
    /// The imports of each module by bound name: (target module, symbol).
    imports: HashMap<(&'m str, &'m str), Vec<Origin<'m>>>,
}

impl Scan<'_> {
    /// True when `name` is not a module, following plain re-exports.
    fn callable(&self, module: &str, name: &str, depth: usize) -> bool {
        let Some(bound) = self.bounds.get(module).filter(|bound| {
            depth < 8
                && !bound.getattr
                && !bound.attribute_write
                && !self.hazardous.contains(module)
                && !self.modules.contains(format!("{module}.{name}").as_str())
        }) else {
            return false;
        };
        match bound.kind(name) {
            Some(Kind::Callable | Kind::Value) => true,
            Some(Kind::BuiltinGeneric(builtin)) => bound.unbound(builtin),
            Some(Kind::Import) => match self.imports.get(&(module, name)).map(Vec::as_slice) {
                Some([(target, Some(symbol))]) => self.callable(target, symbol, depth + 1),
                _ => false,
            },
            _ => false,
        }
    }

    /// The module and each module below it.
    fn below(&self, module: &str) -> Vec<String> {
        let child = format!("{module}.");
        let names = self.modules.iter().copied();
        names
            .filter(|name| *name == module || name.starts_with(&child))
            .map(str::to_owned)
            .collect()
    }
}

/// The modules that a use of a module binding in `modules` can change.
pub(super) fn escaped(modules: &[Module], imports: &[Record<ImportFact>]) -> HashSet<String> {
    let binders: Vec<_> = modules
        .iter()
        .map(|module| super::binders::Binders::of(&module.tree))
        .collect();
    let (_, sites) = super::hazards::split(modules, &binders);
    let mut scan = Scan {
        modules: modules.iter().map(|module| module.name.as_str()).collect(),
        hazardous: sites
            .iter()
            .filter(|(_, site)| namespace_hazard(&site.detail))
            .map(|(index, _)| modules[*index].name.as_str())
            .collect(),
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
