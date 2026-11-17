// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of one collection and the small helpers on it that every step shares: the evidence
//! that a step files, the gaps that it records and the test sources that a request removes.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use archkeel_facts::envelope::{Evidence, FileFact, Target};
use archkeel_facts::request::TypeScriptRequest;
use archkeel_facts::{GapFact, Record};

use crate::kept::Kept;
use crate::pytext::is_space;
use crate::resolver::Resolver;
use crate::syntax::Parsers;
use crate::test_sources::is_test_source;
use archkeel_snapshot::Snapshot;

pub(crate) enum GapKind {
    Collection,
    Resolution,
}

pub(crate) struct Collection<'a> {
    pub(crate) request: &'a TypeScriptRequest,
    pub(crate) namespace: &'a str,
    pub(crate) roots: Vec<String>,
    pub(crate) snapshot: Snapshot,
    pub(crate) resolver: Resolver,
    pub(crate) parsers: Parsers,
    /// A bundler is assumed to decide module loading, and the settings allow it.
    pub(crate) bundler: bool,
    /// Every file to read, in discovery order; a file added while walking is walked too.
    pub(crate) queue: Vec<String>,
    pub(crate) queued: HashSet<String>,
    pub(crate) gaps: BTreeMap<String, Record<GapFact>>,
    /// What reaches an installed-package directory other than a `node_modules` search (AD-488).
    pub(crate) reach: BTreeSet<String>,
    pub(crate) evidence: BTreeMap<String, Evidence>,
    pub(crate) files: Vec<FileFact>,
    pub(crate) imports: Vec<crate::collected::ImportRecord>,
    pub(crate) targets: Vec<Target>,
    pub(crate) read: usize,
    pub(crate) kept: BTreeMap<String, Kept>,
    pub(crate) order: Vec<String>,
    pub(crate) sites: HashMap<String, crate::source::FileSite>,
    /// The script host and the vendored libraries of the project.
    pub(crate) script: crate::script_environment::ScriptEnvironment,
    /// `script_pending_effects` of the files: writes that no publication bounds.
    pub(crate) pending_effects: Vec<(String, crate::source::Span)>,
    /// Each installed file that an import of the scan reaches, with the module and the evidence
    /// of that import (#1529).
    pub(crate) installed: Vec<(String, String, String)>,
}

impl Collection<'_> {
    /// A 9.0.0 request removes test sources, by their path or by their real path.
    pub(crate) fn excluded_test(&mut self, rel: &str) -> bool {
        self.request.excludes_test_sources()
            && (is_test_source(rel)
                || self
                    .snapshot
                    .real(rel)
                    .is_some_and(|real| is_test_source(&real)))
    }

    /// `source_records.file_evidence`: line 1 shows the file; an empty first line cites line 0.
    pub(crate) fn file_evidence(&mut self, rel: &str, text: &str) -> String {
        let first = text
            .split('\n')
            .next()
            .unwrap_or("")
            .trim_end_matches(is_space);
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        self.keep(Evidence::at(rel, line, line, column, first))
    }

    /// `collect._cite`: file one source location as evidence.
    pub(crate) fn cite(&mut self, rel: &str, span: &crate::source::Span) -> String {
        self.keep(Evidence::at(
            rel,
            span.line,
            span.end_line,
            span.column,
            &span.excerpt,
        ))
    }

    /// `collect._gap`: one UNKNOWN record; the same reason, evidence and module give one record.
    pub(crate) fn gap(
        &mut self,
        reason: &str,
        evidence: Option<&str>,
        module: &str,
        kind: GapKind,
    ) {
        let fact = match kind {
            GapKind::Collection => GapFact::collection(reason, module),
            GapKind::Resolution => GapFact::resolution(reason, module),
        };
        let (id, record) = Record::unknown_gap(reason, evidence, module, fact);
        self.gaps.entry(id).or_insert(record);
    }

    /// File one piece of evidence and give its id.
    fn keep(&mut self, evidence: Evidence) -> String {
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }
}
