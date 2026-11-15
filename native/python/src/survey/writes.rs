// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The modules of the scan that another module writes to (AD-504).
//!
//! A route through a module is proven only for the namespace that the module's own statements
//! build. An attribute write (`lib.f = x`, `lib.run += 1`, `del lib.f`), `setattr(lib, ...)`, a
//! mutating call on `lib.__all__` or on `lib.__dict__`, or a store into either, from any module of
//! the scan, can change what `from lib import f` reads. The survey names the written module when
//! the base is a name bound by an import (flow-insensitive: an import in any scope counts) or a
//! literal import call. An imported name of unknown kind (`from lib import x; x.y = 1`) may be a
//! module, so it names the module that it was imported from. A write through `sys.modules`, a
//! computed import, `globals()` of another module or a C extension is not seen here: the first two
//! are survey gaps (AD-450); the rest is listed in `docs/known-limits.md`.

use std::collections::{HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt};

use crate::module::Module;

/// Calls on `__all__` or `__dict__` that change them.
const MUTATORS: [&str; 12] = [
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "popitem",
    "clear",
    "sort",
    "reverse",
    "update",
    "setdefault",
    "__setitem__",
];

/// What one imported name is in a module: the module object or an attribute of a module.
enum Kind {
    /// `import a.b` (the name `a`), `import a.b as c`, `from a import b` where `a.b` is a module.
    Module(String),
    /// `from a import x` where `a.x` is no module of the scan: the object may still be one.
    Attribute(String),
}

/// The modules that a module of `modules` writes to.
pub(super) fn written(modules: &[Module], imports: &[Record<ImportFact>]) -> HashSet<String> {
    let scan: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    let mut kinds: HashMap<&str, HashMap<&str, Vec<Kind>>> = HashMap::new();
    for record in imports {
        let data = record.data.data();
        let Some(binding) = data.binding.as_deref().filter(|name| *name != "*") else {
            continue;
        };
        let target = data.target_module.as_str();
        let kind = match data.symbol.as_deref() {
            None if binding == target.split('.').next().unwrap_or(target) => {
                // `import a.b` binds `a`: the object is the package, the path follows.
                Kind::Module(binding.to_owned())
            }
            None => Kind::Module(target.to_owned()),
            Some(_) => Kind::Attribute(target.to_owned()),
        };
        kinds
            .entry(data.source_module.as_str())
            .or_default()
            .entry(binding)
            .or_default()
            .push(kind);
    }
    let mut found = HashSet::new();
    for module in modules {
        let names = kinds.get(module.name.as_str());
        let mut walk = Writes::default();
        walk.visit_body(&module.tree.body);
        for base in walk.bases {
            for name in reached(base, names, &scan) {
                found.insert(name);
            }
        }
    }
    found
}

/// The module names that a write to `base` can change.
fn reached(
    base: &Expr,
    names: Option<&HashMap<&str, Vec<Kind>>>,
    scan: &HashSet<&str>,
) -> Vec<String> {
    if let Some(literal) = literal_import(base) {
        return prefix(&literal, scan).into_iter().collect();
    }
    let Some(path) = dotted(base) else {
        return Vec::new();
    };
    let (head, rest) = path
        .split_once('.')
        .map_or((path.as_str(), ""), |(h, r)| (h, r));
    let Some(kinds) = names.and_then(|names| names.get(head)) else {
        return Vec::new();
    };
    let join = |root: &str| {
        if rest.is_empty() {
            root.to_owned()
        } else {
            format!("{root}.{rest}")
        }
    };
    kinds
        .iter()
        .filter_map(|kind| match kind {
            Kind::Module(root) => prefix(&join(root), scan),
            Kind::Attribute(anchor) => prefix(anchor, scan),
        })
        .collect()
}

/// The longest module of the scan that is a dotted prefix of `name`.
fn prefix(name: &str, scan: &HashSet<&str>) -> Option<String> {
    let mut end = name.len();
    loop {
        let head = &name[..end];
        if scan.contains(head) {
            return Some(head.to_owned());
        }
        end = head.rfind('.')?;
    }
}

/// `a.b.c` for a chain of names and attributes.
fn dotted(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(node) => Some(node.id.to_string()),
        Expr::Attribute(node) => Some(format!("{}.{}", dotted(&node.value)?, node.attr.as_str())),
        _ => None,
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

/// The base of each store, `del`, `setattr` and mutation in a body, at any depth: the one reader
/// of the objects that a statement writes to (AD-504, AD-518).
pub(crate) fn bases(body: &[Stmt]) -> Vec<&Expr> {
    let mut walk = Writes::default();
    walk.visit_body(body);
    walk.bases
}

/// The objects that a module writes to: the base of each store, `del`, `setattr` and mutation.
#[derive(Default)]
struct Writes<'a> {
    bases: Vec<&'a Expr>,
}

impl<'a> Writes<'a> {
    fn target(&mut self, target: &'a Expr) {
        match target {
            Expr::Attribute(node) => self.bases.push(&node.value),
            Expr::Tuple(node) => node.elts.iter().for_each(|item| self.target(item)),
            Expr::List(node) => node.elts.iter().for_each(|item| self.target(item)),
            Expr::Starred(node) => self.target(&node.value),
            Expr::Subscript(node) => self.namespace(&node.value),
            _ => {}
        }
    }

    /// `x.__all__` or `x.__dict__` or `vars(x)`: a namespace of the object `x`.
    fn namespace(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Attribute(node) if matches!(node.attr.as_str(), "__all__" | "__dict__") => {
                self.bases.push(&node.value);
            }
            Expr::Call(call) if matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "vars") =>
            {
                self.bases.extend(call.arguments.args.first());
            }
            _ => {}
        }
    }
}

impl<'a> Visitor<'a> for Writes<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Assign(node) => node.targets.iter().for_each(|target| self.target(target)),
            Stmt::AugAssign(node) => self.target(&node.target),
            Stmt::AnnAssign(node) => self.target(&node.target),
            Stmt::For(node) => self.target(&node.target),
            Stmt::With(node) => {
                for item in &node.items {
                    item.optional_vars
                        .iter()
                        .for_each(|target| self.target(target));
                }
            }
            Stmt::Delete(node) => node.targets.iter().for_each(|target| self.target(target)),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            match &*call.func {
                Expr::Name(name) if matches!(name.id.as_str(), "setattr" | "delattr") => {
                    self.bases.extend(call.arguments.args.first());
                }
                Expr::Attribute(node) if MUTATORS.contains(&node.attr.as_str()) => {
                    self.namespace(&node.value);
                }
                _ => {}
            }
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "writes_tests.rs"]
mod tests;
