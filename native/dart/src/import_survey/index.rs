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
    /// The package directory below the snapshot root, empty for the root (#1539).
    pub(crate) package_dir: &'a str,
    pub(crate) sources: &'a [Source],
    pub(crate) syntax: Vec<Option<Syntax>>,
    pub(crate) kinds: Vec<Kind>,
    pub(crate) by_rel: HashMap<&'a str, usize>,
    /// The module of each selected source.
    pub(crate) modules: std::collections::HashSet<&'a str>,
    pub(crate) isolate_loader: bool,
    /// The package map of the root package (AD-800).
    pub(crate) packages: super::package_map::PackageMap,
}

/// Where a local path is.
pub(crate) enum Located {
    Source(usize),
    NotSelected,
    Missing,
}

impl Index<'_> {
    /// True when a selected source has the module `name`.
    pub(crate) fn is_module(&self, name: &str) -> bool {
        self.modules.contains(name)
    }

    /// Classify `uri` of a directive in the source `importer` of this package.
    pub(crate) fn classify(&self, importer: &str, uri: &str) -> super::uri::Uri {
        super::uri::classify_in(importer, uri, self.package, self.package_dir)
    }

    /// The selected source at `rel`, or whether a file that is not selected exists there.
    pub(crate) fn locate(&self, snapshot: &mut Snapshot, rel: &str) -> Located {
        match self.by_rel.get(rel) {
            Some(index) => Located::Source(*index),
            None if snapshot.is_file(rel) || Snapshot::is_link(snapshot, rel) => {
                Located::NotSelected
            }
            None => Located::Missing,
        }
    }
}

/// The owner of each owned part, keyed by the index of the part.
pub(crate) type Owners = BTreeMap<usize, usize>;
