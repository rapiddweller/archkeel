// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The selected sources of one survey with their parse, their kind and the owner of each part.

use std::collections::{BTreeMap, HashMap};

use archkeel_snapshot::Snapshot;

use crate::discover::Source;
use crate::syntax::Syntax;

/// What the survey knows of one selected source.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Kind {
    /// A library with a unique module: it gets a file fact.
    Library,
    /// A source with `part of`.
    Part,
    /// A source without a proven module: a syntax error, the parse budget or a module collision.
    Unknown,
}

/// The selected sources of one survey with their parse and their kind.
pub(crate) struct Index<'a> {
    pub(crate) package: &'a str,
    pub(crate) sources: &'a [Source],
    pub(crate) syntax: Vec<Option<Syntax>>,
    pub(crate) kinds: Vec<Kind>,
    pub(crate) by_rel: HashMap<&'a str, usize>,
}

/// Where a local path is.
pub(crate) enum Located {
    Source(usize),
    NotSelected,
    Missing,
}

impl Index<'_> {
    /// The selected source at `rel`, or whether a file that is not selected exists there.
    pub(crate) fn locate(&self, snapshot: &mut Snapshot, rel: &str) -> Located {
        match self.by_rel.get(rel) {
            Some(index) => Located::Source(*index),
            None if snapshot.is_file(rel) || snapshot.is_link(rel) => Located::NotSelected,
            None => Located::Missing,
        }
    }
}

/// The owner of each owned part, keyed by the index of the part.
pub(crate) type Owners = BTreeMap<usize, usize>;
