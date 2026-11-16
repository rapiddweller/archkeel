// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binders of a lazy module that agree with the proven value of a key (AD-654).
//!
//! `__getattr__` runs only for a name that the module namespace does not hold. A key that a
//! statement of the module binds keeps its proof only when each such binder gives the same value:
//! an import of the same attribute or module (also under `TYPE_CHECKING`, which may run or not),
//! or a star import of a module whose literal `__all__` lists the key. `from . import name` of
//! the package itself reads the key through `__getattr__`, so it agrees with `import_module`.

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Stmt, StmtImport, StmtImportFrom};

use super::binders::first_part;
use super::lazy_cover::Source;
use super::package_body::anchor;

/// The name and the value of each import binder of the module, at any depth.
pub(super) fn import_values(body: &[Stmt], package: &str) -> Vec<(String, Source)> {
    let mut walk = Walk {
        package,
        found: Vec::new(),
    };
    walk.visit_body(body);
    walk.found
}

struct Walk<'a> {
    package: &'a str,
    found: Vec<(String, Source)>,
}

impl Walk<'_> {
    /// `import a.b` binds `a` to the module `a`; `import a.b as c` binds `c` to `a.b`.
    fn import(&mut self, node: &StmtImport) {
        for alias in &node.names {
            let name = alias.name.as_str();
            let (bound, module) = match &alias.asname {
                Some(asname) => (asname.as_str(), name),
                None => (first_part(name), first_part(name)),
            };
            let value = Source::Module(module.to_owned());
            self.found.push((bound.to_owned(), value));
        }
    }

    /// `from m import a as b` binds `b` to the attribute `a` of `m`. A failed relative name binds
    /// nothing: the import raises.
    fn import_from(&mut self, node: &StmtImportFrom) {
        let Some(module) = anchor(node, self.package) else {
            return;
        };
        for alias in node.names.iter().filter(|alias| alias.name.as_str() != "*") {
            let bound = alias.asname.as_ref().unwrap_or(&alias.name).to_string();
            let value = Source::Attr(module.clone(), alias.name.to_string());
            self.found.push((bound, value));
        }
    }
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => self.import(node),
            Stmt::ImportFrom(node) => self.import_from(node),
            _ => visitor::walk_stmt(self, stmt),
        }
    }
}

/// True when an import binder of `module` gives the same value as the proven source.
pub(super) fn agrees(value: &Source, source: &Source, module: &str) -> bool {
    match (value, source) {
        (Source::Attr(anchor, name), Source::Module(target)) if anchor == module => {
            format!("{anchor}.{name}") == *target
        }
        _ => value == source,
    }
}
