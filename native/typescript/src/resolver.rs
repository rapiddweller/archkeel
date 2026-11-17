// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of the resolver: the settings in force, the reason that blocks it and the
//! `package.json` files that it read. The rules of `resolve` and of `package` build on it.

use std::collections::HashSet;

use crate::manifest::{self, Json, Lookup, Unknown};
use crate::options::{Options, Resolution};
use crate::source_input::SourceKind;
use archkeel_snapshot::Snapshot;

pub(crate) type Kinds<'a> = &'a [SourceKind];
pub(crate) const TS_AND_DECLARATION: Kinds = &[SourceKind::TypeScript, SourceKind::Declaration];
pub(crate) const DECLARATION: Kinds = &[SourceKind::Declaration];
pub(crate) const NODE_RUNTIME: Kinds = &[SourceKind::JavaScript, SourceKind::Json];

pub(crate) struct Resolver {
    pub options: Options,
    pub(crate) partial: bool,
    /// A reason that nothing can be resolved: the settings in force are not all understood.
    pub blocked: Option<Unknown>,
    pub(crate) reads: HashSet<String>,
    pub(crate) node_runtime: bool,
}

impl Resolver {
    /// Resolve Node runtime files, not TypeScript's substituted or aliased source files.
    pub(crate) fn for_node_preload(&self) -> Self {
        let mut options = self.options.clone();
        options.base_url = None;
        options.paths.clear();
        options.module_resolution = Some(Resolution::NodeNext);
        let mut resolver = Resolver::new(options, self.partial);
        resolver.node_runtime = true;
        resolver
    }

    pub(crate) fn new(options: Options, partial: bool) -> Self {
        let mut resolver = Self {
            options,
            partial,
            blocked: None,
            reads: HashSet::new(),
            node_runtime: false,
        };
        resolver.blocked = resolver.blocked_reason();
        resolver
    }

    fn blocked_reason(&self) -> Option<Unknown> {
        if !self.options.unmodeled.is_empty() {
            let names = self.options.unmodeled.join(", ");
            return Some(Unknown::new(format!(
                "Compiler option is not observed: {names}"
            )));
        }
        if self.partial {
            return Some(Unknown::new("TSConfig settings are not fully observed"));
        }
        (self.options.resolution() == Resolution::Classic)
            .then(|| Unknown::new("moduleResolution classic is not observed"))
    }

    pub(crate) fn exports_aware(&self) -> bool {
        matches!(
            self.options.resolution(),
            Resolution::Node16 | Resolution::NodeNext | Resolution::Bundler
        )
    }

    pub(crate) fn manifest(&mut self, snapshot: &mut Snapshot, directory: &str) -> Lookup<Json> {
        let (path, found) = manifest::read(snapshot, directory);
        self.reads.extend(path);
        found
    }
}
