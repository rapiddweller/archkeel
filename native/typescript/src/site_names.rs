// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a scope hides from a site (`_scope_names`, `_active_scope_names`).
//!
//! `_scope_names` walks the parameters and the whole body of a scope, and a site unites the names
//! of every function between itself and its definition. Held as sets, n nested functions that each
//! declare one name cost n squared entries. Here the walk writes every candidate name once, in
//! document order, to two lists. A scope keeps two ranges of bytes, so its names are the entries of
//! its ranges, and a site keeps one link in a chain of scopes. A reader unites the ranges of the
//! chain when it needs the names of one site.

use std::collections::BTreeSet;

use crate::site_paths::Text;

/// A scope that adds its names to the sites below it.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
struct Scope {
    parent: Option<u32>,
    /// The bytes of the `parameters` field and of the `body` field.
    parameters: Option<(usize, usize)>,
    body: Option<(usize, usize)>,
}

/// A candidate name, with the byte where its node starts.
type Entry = (usize, Text);

#[derive(Default)]
pub struct Names {
    scopes: Vec<Scope>,
    /// The identifiers that are the name of their parent (`_declaration_name`), in document order.
    declared: Vec<Entry>,
    /// The names of variable declarators and the left sides of assignments, in document order.
    written: Vec<Entry>,
}

impl Names {
    /// Open a scope below `parent`: the chain of its sites ends here.
    pub fn open(
        &mut self,
        parent: Option<u32>,
        parameters: Option<(usize, usize)>,
        body: Option<(usize, usize)>,
    ) -> u32 {
        self.scopes.push(Scope {
            parent,
            parameters,
            body,
        });
        u32::try_from(self.scopes.len() - 1).unwrap_or(u32::MAX)
    }

    /// An identifier that names its parent.
    pub fn declared(&mut self, start: usize, name: Text) {
        self.declared.push((start, name));
    }

    /// A declarator or an assignment that names an identifier.
    pub fn written(&mut self, start: usize, name: Text) {
        self.written.push((start, name));
    }

    /// The names of the entries that start in `range`.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    fn within(list: &[Entry], range: (usize, usize)) -> &[Entry] {
        let from = list.partition_point(|entry| entry.0 < range.0);
        let to = list.partition_point(|entry| entry.0 < range.1);
        list.get(from..to.max(from)).unwrap_or(&[])
    }

    /// The names that the scopes of a chain hide, sorted and without repeats.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub fn shadowed(&self, chain: Option<u32>, data: &[u8]) -> Vec<String> {
        let mut names = BTreeSet::new();
        let mut next = chain;
        while let Some(scope) = next.and_then(|at| self.scopes.get(at as usize)) {
            let parameters = scope
                .parameters
                .map(|range| Self::within(&self.declared, range));
            let body = scope.body.map(|range| Self::within(&self.written, range));
            for (_, name) in parameters.into_iter().chain(body).flatten() {
                names.insert(name.decode(data));
            }
            next = scope.parent;
        }
        names.into_iter().collect()
    }
}

#[cfg(test)]
#[path = "site_names_tests.rs"]
mod tests;
