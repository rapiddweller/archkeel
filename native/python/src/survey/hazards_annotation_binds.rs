// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bindings that the walk of `hazards_annotation_scopes.rs` makes (AD-1175): where a name goes
//! (`global`, `nonlocal`), what a target binds, imports.

use ruff_python_ast::{Expr, Identifier, StmtClassDef, StmtImport, StmtImportFrom};

use super::facts::{Binding, Build, Kind, Scope, ScopeId, Write, EVALUATORS};
use crate::survey::package_body::anchor;

impl<'a> Build<'a, '_> {
    pub(super) fn open(&mut self, kind: Kind, class: Option<&'a StmtClassDef>) -> ScopeId {
        let scope = Scope::new(kind, Some(self.current), class);
        self.facts.scopes.push(scope);
        self.facts.scopes.len() - 1
    }

    /// The scope that a binding of `name` goes to: `global` and `nonlocal` redirect it.
    pub(super) fn home(&self, name: &str) -> ScopeId {
        let scope = &self.facts.scopes[self.current];
        if scope.globals.contains(name) {
            return 0;
        }
        self.current
    }

    pub(super) fn bind(&mut self, name: &str, binding: Binding<'a>) {
        if self.facts.scopes[self.current].nonlocals.contains(name) {
            let at = self.current;
            self.facts.pending.push((at, name.to_owned(), binding));
            return;
        }
        let home = self.home(name);
        if self.branch == 0 && !matches!(binding, Binding::Absent) {
            self.facts.scopes[home].sure.insert(name.to_owned());
        }
        let names = &mut self.facts.scopes[home].names;
        names.entry(name.to_owned()).or_default().push(binding);
    }

    /// `target = value`; `None` is a binding of a value that the survey does not read.
    pub(super) fn target(&mut self, target: &'a Expr, value: Option<&'a Expr>) {
        let at = self.current;
        let binding = || value.map_or(Binding::Unknown, |v| Binding::Value(v, at));
        match target {
            Expr::Name(node) => self.bind(node.id.as_str(), binding()),
            Expr::Attribute(node) => {
                let stores = self.facts.stores.entry(node.attr.to_string());
                stores.or_default().push(binding());
                self.facts.writes.push(Write {
                    receiver: &node.value,
                    scope: self.current,
                    attr: Some(node.attr.to_string()),
                });
            }
            // `d[k] = v` changes the value of `d`; a write into `vars(C)` or `x.__dict__` is opaque.
            Expr::Subscript(node) => self.target(&node.value, None),
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.target(e, None)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.target(e, None)),
            Expr::Starred(node) => self.target(&node.value, None),
            _ => {}
        }
    }

    pub(super) fn import_from(&mut self, node: &'a StmtImportFrom) {
        let module = anchor(node, self.package);
        for alias in &node.names {
            let name = alias.name.as_str();
            self.facts.evaluates |= EVALUATORS.contains(&name);
            let future = node
                .module
                .as_ref()
                .is_some_and(|m| m.as_str() == "__future__");
            self.facts.postponed |= future && name == "annotations";
            let local = alias.asname.as_ref().map_or(name, Identifier::as_str);
            match (&module, name) {
                (Some(module), "*") => {
                    let scope = &mut self.facts.scopes[self.current];
                    scope.stars.push(module.clone());
                }
                (Some(module), _) => {
                    let binding = Binding::Import(module.clone(), Some(name.to_owned()));
                    self.bind(local, binding);
                }
                (None, _) => self.bind(local, Binding::Unknown),
            }
        }
    }

    /// `import a`, `import a.b as c`: the name binds the module.
    pub(super) fn import(&mut self, node: &'a StmtImport) {
        for alias in &node.names {
            let name = alias.name.as_str();
            self.facts.evaluates |=
                EVALUATORS.contains(&name.rsplit('.').next().unwrap_or_default());
            let first = name.split('.').next().unwrap_or(name);
            let (local, module) = alias
                .asname
                .as_ref()
                .map_or((first, first), |l| (l.as_str(), name));
            self.bind(local, Binding::Import(module.to_owned(), None));
        }
    }

    pub(super) fn target_inert(&mut self, target: &'a Expr) {
        if let Expr::Name(node) = target {
            self.bind(node.id.as_str(), Binding::Inert);
        }
    }
}
