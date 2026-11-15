// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of one analysis of the uses of globals, and the questions on it that the producers of
//! `script_deps.rs`, `script_depend.rs`, `script_global.rs` and `script_proof.rs` all ask.

use std::collections::HashSet;

use crate::kept::Kept;
use crate::script_project::{Project, Publisher, Write, WriteIndex};
use crate::script_records::{Sink, SiteKey};
use crate::script_vendor::Vendors;
use crate::sites::SiteKind;
use crate::source::Span;
use crate::source_input::FRAME_ROOTS;

/// `collect._SCRIPT_ROOTS`: the names of the global object, and `top` and `parent`, which are the
/// window outside a frame. The analysis of a use reads them as roots; the walk of a file does not,
/// so a write through them publishes nothing, and a local variable named `parent` is no root.
pub(crate) fn is_root(name: &str) -> bool {
    crate::source_input::is_script_root(name.as_bytes()) || FRAME_ROOTS.contains(&name)
}

/// `ScriptRoot.unrooted`: how many leading names of a path name the global object, so that
/// `window.self.x` is `x` (#1007).
pub(crate) fn leading_roots(path: &[String]) -> usize {
    path.iter().take_while(|name| is_root(name)).count()
}

/// A site as the analysis reads it: a site of the file, or a name that a destructuring brings.
pub(crate) struct Probe {
    pub kind: SiteKind,
    pub span: Span,
    pub path: Vec<String>,
    pub scope_ambiguous: bool,
}

impl Probe {
    pub(crate) fn key(&self) -> SiteKey {
        SiteKey::new(self.kind, &self.span, &self.path)
    }
}

/// The state of one analysis. The project is read; the sink is written.
pub(crate) struct Run<'a, 'p> {
    pub project: &'p Project<'a>,
    pub partial: bool,
    pub standard: HashSet<String>,
    pub vendors: Vendors,
    pub writes: WriteIndex<'a>,
    pub source_writes: WriteIndex<'a>,
    /// The source writes without repeats, to ask whether one is among them.
    pub source_set: HashSet<Write<'a>>,
    pub sink: Sink,
}

impl<'a, 'p> Run<'a, 'p> {
    /// The publications of a name, in file order.
    pub(crate) fn publishers(&self, name: Option<&String>) -> &'p [Publisher<'a>] {
        let found = name.and_then(|name| self.project.publications.get(name.as_str()));
        found.map_or(&[][..], Vec::as_slice)
    }

    /// The module of a file.
    pub(crate) fn module(&self, rel: &str) -> String {
        let at = self.project.index.get(rel).copied();
        at.and_then(|at| self.project.files.get(at))
            .map_or_else(String::new, |(_, file)| file.module.clone())
    }

    /// The file of a path; the facts of a file that the walk read.
    pub(crate) fn file(&self, rel: &str) -> Option<&'a Kept> {
        let at = self.project.index.get(rel).copied()?;
        self.project.files.get(at).map(|(_, file)| *file)
    }
}
