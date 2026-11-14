// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The source domain of one mount of an inside-contract tree (AD-385).

use std::collections::HashSet;

use crate::ids::ModuleId;
use crate::ownership::in_scope;

/// The source domain of one mount: the modules that it owns and the packages of its parent
/// (`source_roots`).
#[derive(Clone, Debug)]
pub(crate) struct Domain {
    /// The held modules, sorted: the domain grows with the mount, not with the reply.
    held: Vec<ModuleId>,
    names: HashSet<String>,
    roots: Vec<String>,
    /// The exact modules of the parent of the mount (`source_exact_modules`).
    exact: Vec<String>,
}

impl Domain {
    /// The domain of the held modules, their names, the parent packages and the parent exact
    /// modules.
    pub(crate) fn new(
        mut held: Vec<ModuleId>,
        names: HashSet<String>,
        (roots, exact): (Vec<String>, Vec<String>),
    ) -> Domain {
        held.sort_unstable();
        held.dedup();
        Domain {
            held,
            names,
            roots,
            exact,
        }
    }

    /// The packages and the exact modules of the parent of the mount.
    pub(crate) fn scopes(&self) -> (&[String], &[String]) {
        (&self.roots, &self.exact)
    }

    /// The held modules, sorted.
    pub(crate) fn held(&self) -> &[ModuleId] {
        &self.held
    }

    /// The names of the held modules.
    pub(crate) fn names(&self) -> impl Iterator<Item = &String> {
        self.names.iter()
    }

    pub(crate) fn holds(&self, module: ModuleId) -> bool {
        self.held.binary_search(&module).is_ok()
    }

    pub(crate) fn selects(&self, module: &str) -> bool {
        self.names.contains(module)
    }

    pub(crate) fn below_roots(&self, package: &str) -> bool {
        self.roots.iter().any(|root| in_scope(package, root))
    }
}

#[cfg(test)]
#[path = "domain_tests.rs"]
mod tests;
