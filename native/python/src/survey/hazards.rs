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
//! The walk finds names, not bindings: a local value with one of these names is a site too,
//! which is the stricter reading.

use std::collections::HashMap;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

/// The named gaps of the sites.
pub(super) const DYNAMIC: &str = "dynamic_import";
pub(super) const IMPORT_SYSTEM: &str = "import_system_change";

/// The doors: a reference to one of these names, or to a name below it, is a dynamic import.
const DOORS: [&str; 38] = [
    "builtins.__import__",
    "builtins.exec",
    "builtins.eval",
    "builtins.compile",
    "builtins.__dict__",
    "importlib.import_module",
    "importlib.__import__",
    "importlib.reload",
    "importlib.util",
    "importlib.machinery",
    "importlib._bootstrap",
    "importlib._bootstrap_external",
    "importlib.metadata.entry_points",
    "importlib.metadata.EntryPoint",
    "importlib.metadata.EntryPoints",
    "pkgutil",
    "pydoc",
    "runpy",
    "imp",
    "zipimport",
    "code",
    "codeop",
    "timeit",
    "doctest",
    "marshal",
    "pickle",
    "_pickle",
    "shelve",
    "dill",
    "cloudpickle",
    "ctypes.pythonapi",
    "types.FunctionType",
    "types.CodeType",
    "unittest.mock.patch",
    "mock.patch",
    "pytest.importorskip",
    "__builtins__",
    "sys.__dict__",
];

/// The state of the import system: a reference is an import-system change.
const STATE: [&str; 6] = [
    "site",
    "sys.path",
    "sys.meta_path",
    "sys.path_hooks",
    "sys.path_importer_cache",
    "sys.modules",
];

/// The builtins that are doors as a plain name.
const BUILTIN_DOORS: [&str; 5] = ["__import__", "exec", "eval", "compile", "__builtins__"];

/// The names of import functions: a door as a plain name or as an attribute of any value.
const IMPORT_FUNCTIONS: [&str; 9] = [
    "__import__",
    "import_module",
    "load_module",
    "exec_module",
    "module_from_spec",
    "spec_from_file_location",
    "run_module",
    "run_path",
    "resolve_name",
];

/// The attributes that are hazards on any value: state of the import system and modules that
/// another module can re-export (`os.sys`).
const ANY_ATTRIBUTE: [&str; 7] = [
    "meta_path",
    "path_hooks",
    "path_importer_cache",
    "sys",
    "builtins",
    "importlib",
    "__builtins__",
];

/// One site: its gap, a short text and its range.
pub(super) struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
}

/// The sites of a module, in source order.
pub(super) fn sites(tree: &ModModule) -> Vec<Site> {
    let mut walk = Walk {
        found: Vec::new(),
        bound: bindings(tree),
    };
    walk.visit_body(&tree.body);
    walk.found
}

/// The gap of a qualified name: a door, the import state, or a name below one of them.
fn hazard(name: &str) -> Option<&'static str> {
    let under = |entry: &&str| {
        name == *entry
            || name
                .strip_prefix(*entry)
                .is_some_and(|rest| rest.starts_with('.'))
    };
    if STATE.iter().any(under) {
        Some(IMPORT_SYSTEM)
    } else if DOORS.iter().any(under) {
        Some(DYNAMIC)
    } else {
        None
    }
}

/// True for a module above a hazard name, such as `sys` or `importlib.metadata`.
fn above(name: &str) -> bool {
    let prefix = format!("{name}.");
    DOORS
        .iter()
        .chain(&STATE)
        .any(|entry| entry.starts_with(&prefix))
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
        Stmt::Import(node) => node.names.iter().map(|a| a.name.to_string()).collect(),
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

struct Walk {
    found: Vec<Site>,
    bound: HashMap<String, Vec<String>>,
}

impl Walk {
    fn push(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        self.found.push(Site {
            kind,
            detail: detail.to_owned(),
            range: node.range(),
        });
    }

    /// The qualified origins of a plain name: its import bindings, else the name itself.
    fn origins(&self, name: &str) -> Vec<String> {
        self.bound
            .get(name)
            .cloned()
            .unwrap_or_else(|| vec![name.to_owned()])
    }

    /// A plain name that is not the base of an attribute.
    fn name(&mut self, id: &str, expr: &Expr) {
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
        let mut base = expr;
        while let Expr::Attribute(node) = base {
            attributes.push(node.attr.as_str());
            base = &node.value;
        }
        attributes.reverse();
        if let Some(name) = attributes.iter().find(|a| {
            ANY_ATTRIBUTE.contains(a) || IMPORT_FUNCTIONS.contains(a) || **a == "__path__"
        }) {
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
        let Expr::Name(root) = base else {
            return self.visit_expr(base);
        };
        for origin in self.origins(root.id.as_str()) {
            if let Some((kind, name)) = first_hazard(origin, &attributes) {
                return self.push(kind, &name, expr);
            }
        }
    }
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

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        for name in imported(stmt) {
            if let Some(kind) = hazard(&name) {
                self.push(kind, &name, stmt);
            }
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Attribute(_) => self.chain(expr),
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
