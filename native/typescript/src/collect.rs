// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import facts of one request, as `analyzer/typescript/collect.py` collects them.
//!
//! The files, inputs, coverage, file evidence, import records and import targets follow the
//! Python collector. The records are one for each statement. The expansion of a statement into one
//! record for each named binding (`_named_imports`), the script globals and the symbols belong to
//! later phases. Without them this collector declares the legacy capability: sections `imports`
//! and `unknowns`, and no `script-globals-v1` feature. It invents no evidence.

use std::collections::{BTreeMap, HashMap, HashSet};

use archkeel_wire::identity::{evidence_id, module_identity, package_of, stable_id, Part};
use archkeel_wire::reply::{Evidence, Facts, FileFact, Provenance, Record, Target};
use archkeel_wire::request::Request;
use serde_json::{Map, Value};

use crate::config::load_config;
use crate::kept::{Kept, Pending};
use crate::options::Resolution;
use crate::paths::join;
use crate::pytext::is_space;
use crate::records::{build, Records};
use crate::resolve::Resolver;
use crate::snapshot::Snapshot;
use crate::syntax::Parsers;
use crate::test_sources::{is_test_source, NO_PRODUCTION_SOURCE};

/// The profile and adapter name of the Python TypeScript collector, so that this is a drop-in.
pub const PROFILE: &str = "archkeel-typescript-imports";
const SECTIONS: [&str; 2] = ["imports", "unknowns"];
const FEATURES: [&str; 4] = [
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
];
// What the compiler's `trim()` removes (`collect._WHITESPACE`).
const COMPILER_SPACE: &str = " \t\n\u{b}\u{c}\r\u{a0}\u{1680}\u{2000}\u{2001}\u{2002}\u{2003}\u{2004}\u{2005}\u{2006}\u{2007}\u{2008}\u{2009}\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}\u{feff}";

enum GapKind {
    Collection,
    Resolution,
}

struct Collection<'a> {
    request: &'a Request,
    namespace: &'a str,
    roots: Vec<String>,
    snapshot: Snapshot,
    resolver: Resolver,
    parsers: Parsers,
    /// A bundler is assumed to decide module loading, and the settings allow it.
    bundler: bool,
    /// Every file to read, in discovery order; a file added while walking is walked too.
    queue: Vec<String>,
    queued: HashSet<String>,
    gaps: BTreeMap<String, Record>,
    evidence: BTreeMap<String, Evidence>,
    files: Vec<FileFact>,
    imports: Vec<Record>,
    targets: Vec<Target>,
    read: usize,
    /// Keep what the records of PR 4.3a-3a need (`records.rs`); a plain collection does not.
    keep: bool,
    kept: BTreeMap<String, Kept>,
    order: Vec<String>,
    sites: HashMap<String, (String, i64, i64)>,
}

/// Collect the facts of one request.
pub fn collect(request: &Request, provenance: Provenance) -> Facts {
    gather(request, provenance, false).0
}

/// The facts of one request and the records that the reply does not carry yet. Only the `dump`
/// feature calls it (AD-323).
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub fn records(request: &Request, provenance: Provenance) -> (Facts, Records) {
    let (facts, pending) = gather(request, provenance, true);
    let records = build(&facts, &pending);
    (facts, records)
}

fn gather(request: &Request, provenance: Provenance, keep: bool) -> (Facts, Pending) {
    let roots: Vec<String> = request.roots.iter().map(|root| join(".", root)).collect();
    let mut snapshot = Snapshot::new(&request.root);
    let config = load_config(&mut snapshot, &request.tsconfig, &roots);
    let resolver = Resolver::new(config.options, config.partial);
    let bundler = request.bundler
        && resolver.blocked.is_none()
        && resolver.options.resolution() == Resolution::Bundler;
    let partial = config.partial;
    let listed = config.files;
    let mut collection = Collection {
        request,
        namespace: &request.namespace,
        roots: roots.clone(),
        snapshot,
        resolver,
        parsers: Parsers::new(),
        bundler,
        queue: Vec::new(),
        queued: HashSet::new(),
        gaps: BTreeMap::new(),
        evidence: BTreeMap::new(),
        files: Vec::new(),
        imports: Vec::new(),
        targets: Vec::new(),
        read: 0,
        keep,
        kept: BTreeMap::new(),
        order: Vec::new(),
        sites: HashMap::new(),
    };
    collection.queue = listed
        .iter()
        .filter(|rel| !collection.excluded_test(rel))
        .cloned()
        .collect();
    collection.queued = collection.queue.iter().cloned().collect();
    if request.exclude_test_sources && !listed.is_empty() && collection.queue.is_empty() {
        collection
            .snapshot
            .problems
            .insert(NO_PRODUCTION_SOURCE.to_owned());
    }
    if request.bundler && !collection.bundler && collection.resolver.blocked.is_none() {
        collection.gap(
            "Bundler mode requires moduleResolution bundler",
            None,
            "",
            GapKind::Resolution,
        );
    }
    let mut index = 0;
    while index < collection.queue.len() {
        let rel = collection.queue[index].clone();
        collection.file(&rel);
        index += 1;
    }
    let problems: Vec<String> = collection.snapshot.problems.iter().cloned().collect();
    for problem in problems {
        collection.gap(&problem, None, "", GapKind::Collection);
    }
    let scope = roots
        .iter()
        .map(|root| {
            if collection.snapshot.is_dir(root) {
                format!("{root}/**")
            } else {
                root.clone()
            }
        })
        .collect();
    let mut files = collection.files;
    files.sort_by(|left, right| left.rel_path.cmp(&right.rel_path));
    let mut selected_files = collection.queue;
    selected_files.sort();
    let gaps: Vec<Record> = collection.gaps.into_values().collect();
    let mut imports = collection.imports;
    imports.sort_by(|left, right| left.id.cmp(&right.id));
    let mut features = FEATURES.to_vec();
    if collection.bundler {
        features.push("bundler-mode-v1");
    }
    let pending = Pending {
        kept: collection.kept,
        order: collection.order,
        sites: collection.sites,
        partial,
    };
    let facts = Facts {
        provenance,
        git_head: request.git_head.clone(),
        dirty: request.dirty.clone(),
        scope,
        sections: vec![(SECTIONS[0], imports), (SECTIONS[1], gaps.clone())],
        features,
        constructs: Vec::new(),
        inputs: collection.snapshot.inputs(),
        files,
        imports: collection.targets,
        selected_files,
        files_read: collection.read,
        gaps,
        evidence: collection.evidence.into_values().collect(),
    };
    (facts, pending)
}

impl Collection<'_> {
    /// A 9.0.0 request removes test sources, by their path or by their real path.
    fn excluded_test(&mut self, rel: &str) -> bool {
        self.request.exclude_test_sources
            && (is_test_source(rel)
                || self
                    .snapshot
                    .real(rel)
                    .is_some_and(|real| is_test_source(&real)))
    }

    fn file(&mut self, rel: &str) {
        let Some(content) = self.snapshot.read(rel) else {
            let reason = self
                .snapshot
                .size_gap(rel)
                .unwrap_or_else(|| format!("Unreadable selected source: {rel}"));
            self.gap(&reason, None, "", GapKind::Collection);
            return;
        };
        let Ok(module) = module_identity(self.namespace, rel) else {
            self.gap(
                &format!("Source path has no module identity: {rel}"),
                None,
                "",
                GapKind::Collection,
            );
            return;
        };
        self.read += 1;
        self.snapshot.select(rel);
        let text = String::from_utf8_lossy(&content);
        let evidence = self.file_evidence(rel, &text);
        self.files.push(FileFact {
            id: stable_id("FILE", &[Part::Text(&module)]),
            rel_path: rel.to_owned(),
            package: package_of(&module).to_owned(),
            blank: text.trim_matches(|c| COMPILER_SPACE.contains(c)).is_empty(),
            evidence_id: evidence.clone(),
            module: module.clone(),
        });
        self.references(rel, &module, &evidence, &text);
    }

    /// `source_records.file_evidence`: line 1 shows the file; an empty first line cites line 0.
    fn file_evidence(&mut self, rel: &str, text: &str) -> String {
        let first = text
            .split('\n')
            .next()
            .unwrap_or("")
            .trim_end_matches(is_space);
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        let id = evidence_id(rel, line, line, column);
        self.evidence.insert(
            id.clone(),
            Evidence {
                id: id.clone(),
                file: rel.to_owned(),
                line,
                end_line: line,
                column,
                excerpt: first.to_owned(),
            },
        );
        id
    }

    /// `collect._cite`: file one source location as evidence.
    fn cite(&mut self, rel: &str, span: &crate::source::Span) -> String {
        let id = evidence_id(rel, span.line, span.end_line, span.column);
        self.evidence.insert(
            id.clone(),
            Evidence {
                id: id.clone(),
                file: rel.to_owned(),
                line: span.line,
                end_line: span.end_line,
                column: span.column,
                excerpt: span.excerpt.clone(),
            },
        );
        id
    }

    /// `collect._gap`: one UNKNOWN record; the same reason, evidence and module give one record.
    fn gap(&mut self, reason: &str, evidence: Option<&str>, module: &str, kind: GapKind) {
        let mut parts = vec![Part::Text(reason)];
        parts.extend(evidence.map(Part::Text));
        parts.push(Part::Text(module));
        let id = stable_id("UNKNOWN", &parts);
        let mut data = Map::new();
        data.insert("reason".to_owned(), Value::from(reason));
        data.insert("module".to_owned(), Value::from(module));
        let kind = match kind {
            GapKind::Collection => "collection_gap",
            GapKind::Resolution => {
                data.insert("resolution_dimension".to_owned(), Value::from("imports"));
                "source_resolution_gap"
            }
        };
        self.gaps.entry(id.clone()).or_insert(Record {
            id,
            evidence_class: "UNKNOWN",
            area: "source",
            kind,
            title: reason.to_owned(),
            subjects: [module]
                .into_iter()
                .filter(|m| !m.is_empty())
                .map(str::to_owned)
                .collect(),
            evidence_ids: evidence.into_iter().map(str::to_owned).collect(),
            fact_ids: Vec::new(),
            data,
        });
    }
}

#[path = "imports.rs"]
mod imports;

#[cfg(test)]
#[path = "collect_tests.rs"]
mod tests;
