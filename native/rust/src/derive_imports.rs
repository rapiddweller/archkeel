// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The imports of one module that the proof of a derive identity looks up, read once. The proof runs
//! for every concern of the module; a scan of all references per concern would grow with the square
//! of the module size.

use std::collections::BTreeMap;

use crate::scan::{Reference, Via};
use crate::tree::Module;

pub(crate) struct Local<'a> {
    pub module: &'a Module,
    /// The glob imports, in the order of the file.
    pub globs: Vec<&'a Reference>,
    /// The first `use` that binds a name outside of a block, by scope and name.
    bindings: BTreeMap<(&'a [String], &'a str), &'a Reference>,
}

impl<'a> Local<'a> {
    pub(crate) fn of(module: &'a Module) -> Self {
        let mut globs = Vec::new();
        let mut bindings = BTreeMap::new();
        for reference in &module.scan.references {
            match &reference.via {
                Via::Glob { .. } => globs.push(reference),
                Via::Use {
                    binding: Some(name),
                    block: false,
                    ..
                } => {
                    bindings
                        .entry((reference.scope.as_slice(), name.as_str()))
                        .or_insert(reference);
                }
                _ => {}
            }
        }
        Self {
            module,
            globs,
            bindings,
        }
    }

    pub(crate) fn binding(&self, scope: &[String], name: &str) -> Option<&'a Reference> {
        self.bindings.get(&(scope, name)).copied()
    }
}
