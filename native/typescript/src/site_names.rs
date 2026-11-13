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

use std::collections::{BTreeSet, HashMap};

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
pub(crate) struct Names {
    scopes: Vec<Scope>,
    /// The identifiers that are the name of their parent (`_declaration_name`), in document order.
    declared: Vec<Entry>,
    /// The names of variable declarators and the left sides of assignments, in document order.
    written: Vec<Entry>,
}

impl Names {
    /// Open a scope below `parent`: the chain of its sites ends here.
    pub(crate) fn open(
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
    pub(crate) fn declared(&mut self, start: usize, name: Text) {
        self.declared.push((start, name));
    }

    /// A declarator or an assignment that names an identifier.
    pub(crate) fn written(&mut self, start: usize, name: Text) {
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
    pub(crate) fn shadowed(&self, chain: Option<u32>, data: &[u8]) -> Vec<String> {
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

/// The names of a file by name, for the question "does a scope of this chain hide this name"
/// (`name in site.shadowed_names`) without a union of the sets. A chain item hides a name when the
/// name is declared in its `parameters` or written in its `body`. The ranges of the items of a chain
/// nest, so each item keeps the list of the ranges that its ancestors do not already cover, and a
/// question reads that short list and does one binary search in the positions of the name.
#[derive(Default)]
pub(crate) struct NameIndex {
    declared: HashMap<String, Vec<usize>>,
    written: HashMap<String, Vec<usize>>,
    /// For each scope, the head of its list of body ranges and of parameter ranges.
    body: Vec<Option<u32>>,
    parameters: Vec<Option<u32>>,
    /// `(from, to, next)`: a range and the rest of the list.
    ranges: Vec<(usize, usize, Option<u32>)>,
}

impl Names {
    /// Index the names of the file. `data` is the text that the positions point into.
    pub(crate) fn index(&self, data: &[u8]) -> NameIndex {
        let mut index = NameIndex::default();
        for (list, target) in [
            (&self.declared, &mut index.declared),
            (&self.written, &mut index.written),
        ] {
            for (start, name) in list {
                target.entry(name.decode(data)).or_default().push(*start);
            }
        }
        for scope in &self.scopes {
            let above = scope.parent.map(|at| at as usize);
            let body = index.extend(
                above.and_then(|at| index.body.get(at).copied().flatten()),
                scope.body,
            );
            let parameters = index.extend(
                above.and_then(|at| index.parameters.get(at).copied().flatten()),
                scope.parameters,
            );
            index.body.push(body);
            index.parameters.push(parameters);
        }
        index
    }
}

impl NameIndex {
    /// The list of `above` with `range` in front, unless an earlier range covers it.
    fn extend(&mut self, above: Option<u32>, range: Option<(usize, usize)>) -> Option<u32> {
        let Some((from, to)) = range else {
            return above;
        };
        let mut next = above;
        while let Some(at) = next {
            let (lo, hi, rest) = self.ranges.get(at as usize).copied()?;
            if lo <= from && to <= hi {
                return above;
            }
            next = rest;
        }
        self.ranges.push((from, to, above));
        u32::try_from(self.ranges.len() - 1).ok()
    }

    fn within(&self, list: Option<u32>, starts: &[usize]) -> bool {
        let mut next = list;
        while let Some((lo, hi, rest)) = next.and_then(|at| self.ranges.get(at as usize).copied()) {
            let first = starts.partition_point(|start| *start < lo);
            if starts.get(first).is_some_and(|start| *start < hi) {
                return true;
            }
            next = rest;
        }
        false
    }

    /// `name in site.shadowed_names` for the site whose chain ends at `chain`.
    pub(crate) fn shadows(&self, chain: Option<u32>, name: &str) -> bool {
        let Some(at) = chain.map(|at| at as usize) else {
            return false;
        };
        let body = self.body.get(at).copied().flatten();
        let parameters = self.parameters.get(at).copied().flatten();
        self.written
            .get(name)
            .is_some_and(|starts| self.within(body, starts))
            || self
                .declared
                .get(name)
                .is_some_and(|starts| self.within(parameters, starts))
    }
}

#[cfg(test)]
#[path = "site_names_tests.rs"]
mod tests;
