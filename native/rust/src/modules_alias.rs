// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that `extern crate self as name;` binds to the root of the own crate.
//!
//! An alias in the crate root joins the extern prelude: any module of the crate, and a path that
//! starts with `::`, names the root with it. An alias in another module (or inline module) is a
//! name of that module only, reached as `crate::m::name`. A local name that the file declares
//! wins over the prelude, so a file that declares the alias name itself is resolved by the
//! binding it sees, or is UNKNOWN. An alias in a function body binds in that file only.

use std::collections::{BTreeMap, BTreeSet};

use super::{Frame, Index, Outcome};
use crate::tree::Module;

#[derive(Debug, Default)]
pub(super) struct Aliases {
    /// The aliases of each crate root, by the module id of the root: the extern prelude.
    prelude: BTreeMap<String, BTreeSet<String>>,
    /// The aliases that a lexical module binds, to the crate root that each names.
    members: BTreeMap<(String, String), String>,
}

impl Aliases {
    /// Read the `extern crate self as name;` items of `module`, whose target root is `root`.
    pub(super) fn record(&mut self, module: &Module, root: &str) {
        for (scope, name) in &module.scan.self_aliases {
            let lexical = scope
                .iter()
                .fold(module.module.clone(), |id, part| format!("{id}.{part}"));
            self.members
                .insert((lexical, name.clone()), root.to_owned());
            if scope.is_empty() && module.module == root {
                self.prelude
                    .entry(root.to_owned())
                    .or_default()
                    .insert(name.clone());
            }
        }
    }

    /// The crate root that the lexical module `at` names with `name`, when it is an alias.
    pub(super) fn member(&self, at: &str, name: &str) -> Option<&str> {
        let key = (at.to_owned(), name.to_owned());
        self.members.get(&key).map(String::as_str)
    }

    /// Whether the extern prelude of the target of `frame` holds `name`.
    pub(super) fn in_prelude(&self, frame: &Frame<'_>, name: &str) -> bool {
        self.prelude
            .get(frame.root)
            .is_some_and(|names| names.contains(name))
    }
}

impl Index<'_> {
    /// A path that starts with `::name`: the crate root when `name` is in the extern prelude.
    pub(super) fn absolute(&self, frame: &Frame<'_>, names: &[String]) -> Outcome {
        self.prelude_edge(frame, names).unwrap_or(Outcome::None)
    }

    /// What `names` names when its first name is an alias of the extern prelude, or `None`.
    pub(super) fn prelude_edge(&self, frame: &Frame<'_>, names: &[String]) -> Option<Outcome> {
        let first = names.first()?;
        let alias = self.aliases.in_prelude(frame, first);
        alias.then(|| self.follow(frame.root, 0, &names[1..]))
    }

    /// A name that the file declares without a module or a binding of it: an alias of the prelude
    /// makes the path UNKNOWN, since the declaration may take the place of the alias.
    pub(super) fn declared_over_alias(&self, frame: &Frame<'_>, name: &str) -> Outcome {
        if !self.aliases.in_prelude(frame, name) {
            return Outcome::None;
        }
        let reason =
            format!("A name that the file declares may hide the alias of the own crate: {name}");
        Outcome::Unknown(reason)
    }
}
