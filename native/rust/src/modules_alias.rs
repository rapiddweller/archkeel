// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that `extern crate self as name;` binds to the root of the own crate.
//!
//! An alias in the crate root joins the extern prelude: any module of the crate, and a path that
//! starts with `::`, names the root with it. An alias in another module (or inline module) is a
//! name of that module only, reached as `crate::m::name`. A local name that the file declares
//! wins over the prelude, so a file that declares the alias name itself is resolved by the
//! binding it sees, or is UNKNOWN. An alias in a function body binds in that file only. The
//! resolver (`modules.rs`) reads this table; the table knows nothing of the resolver.

use std::collections::{BTreeMap, BTreeSet};

use crate::tree::Module;

#[derive(Debug, Default)]
pub(crate) struct Aliases {
    /// The aliases of each crate root, by the module id of the root: the extern prelude.
    prelude: BTreeMap<String, BTreeSet<String>>,
    /// The aliases that a lexical module binds, to the crate root that each names.
    members: BTreeMap<(String, String), String>,
}

impl Aliases {
    /// Read the `extern crate self as name;` items of `module`, whose target root is `root`.
    pub(crate) fn record(&mut self, module: &Module, root: &str) {
        for (scope, name) in &module.scan.self_aliases {
            let lexical = scope
                .iter()
                .fold(module.module.clone(), |id, part| format!("{id}.{part}"));
            let key = (lexical, name.clone());
            self.members.insert(key, root.to_owned());
            if scope.is_empty() && module.module == root {
                self.prelude
                    .entry(root.to_owned())
                    .or_default()
                    .insert(name.clone());
            }
        }
    }

    /// The crate root that the lexical module `at` names with `name`, when it is an alias.
    pub(crate) fn member(&self, at: &str, name: &str) -> Option<&str> {
        let key = (at.to_owned(), name.to_owned());
        self.members.get(&key).map(String::as_str)
    }

    /// Whether the extern prelude of the target with the root `root` holds `name`.
    pub(crate) fn in_prelude(&self, root: &str, name: &str) -> bool {
        self.prelude
            .get(root)
            .is_some_and(|names| names.contains(name))
    }
}
