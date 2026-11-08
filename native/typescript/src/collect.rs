// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The imports-only facts of the walking skeleton.
//!
//! The files, inputs, coverage and file evidence follow `analyzer/typescript/collect.py`. This
//! collector does not extract imports yet, so each observed file has one resolution gap. The
//! gap keeps every import rule UNKNOWN: no evidence is invented, and nothing reads as PASS.

use std::collections::BTreeMap;

use archkeel_wire::identity::{evidence_id, module_identity, package_of, stable_id, Part};
use archkeel_wire::reply::{Evidence, Facts, FileFact, Provenance, Record};
use archkeel_wire::request::Request;
use serde_json::{Map, Value};

use crate::config::load_config;
use crate::paths::join;
use crate::snapshot::Snapshot;
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
pub const IMPORT_GAP: &str = "Imports are not extracted by the native collector yet";
// Python `str.isspace`, which `str.rstrip()` removes.
const PYTHON_SPACE: &str = "\t\n\u{b}\u{c}\r\u{1c}\u{1d}\u{1e}\u{1f} \u{85}\u{a0}\u{1680}\u{2000}\u{2001}\u{2002}\u{2003}\u{2004}\u{2005}\u{2006}\u{2007}\u{2008}\u{2009}\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}";
// What the compiler's `trim()` removes (`collect._WHITESPACE`).
const COMPILER_SPACE: &str = " \t\n\u{b}\u{c}\r\u{a0}\u{1680}\u{2000}\u{2001}\u{2002}\u{2003}\u{2004}\u{2005}\u{2006}\u{2007}\u{2008}\u{2009}\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}\u{feff}";

enum GapKind {
    Collection,
    Resolution,
}

struct Collection<'a> {
    request: &'a Request,
    snapshot: Snapshot,
    gaps: BTreeMap<String, Record>,
    evidence: BTreeMap<String, Evidence>,
    files: Vec<FileFact>,
    read: usize,
}

/// Collect the facts of one request.
pub fn collect(request: &Request, provenance: Provenance) -> Facts {
    let roots: Vec<String> = request.roots.iter().map(|root| join(".", root)).collect();
    let mut snapshot = Snapshot::new(&request.root);
    let listed = load_config(&mut snapshot, &request.tsconfig, &roots);
    let mut collection = Collection {
        request,
        snapshot,
        gaps: BTreeMap::new(),
        evidence: BTreeMap::new(),
        files: Vec::new(),
        read: 0,
    };
    let queue: Vec<String> = listed
        .iter()
        .filter(|rel| !collection.excluded_test(rel))
        .cloned()
        .collect();
    if request.exclude_test_sources && !listed.is_empty() && queue.is_empty() {
        collection
            .snapshot
            .problems
            .insert(NO_PRODUCTION_SOURCE.to_owned());
    }
    if request.bundler {
        collection.gap(
            "Bundler mode is not observed by the native collector",
            None,
            "",
            GapKind::Collection,
        );
    }
    for rel in &queue {
        collection.file(rel);
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
    let mut selected_files = queue;
    selected_files.sort();
    let gaps: Vec<Record> = collection.gaps.into_values().collect();
    Facts {
        provenance,
        git_head: request.git_head.clone(),
        dirty: request.dirty.clone(),
        scope,
        sections: vec![(SECTIONS[0], Vec::new()), (SECTIONS[1], gaps.clone())],
        features: FEATURES.to_vec(),
        inputs: collection.snapshot.inputs(),
        files,
        selected_files,
        files_read: collection.read,
        gaps,
        evidence: collection.evidence.into_values().collect(),
    }
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
        let Ok(module) = module_identity(&self.request.namespace, rel) else {
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
        self.gap(IMPORT_GAP, Some(&evidence), &module, GapKind::Resolution);
    }

    /// `source_records.file_evidence`: line 1 shows the file; an empty first line cites line 0.
    fn file_evidence(&mut self, rel: &str, text: &str) -> String {
        let first = text
            .split('\n')
            .next()
            .unwrap_or("")
            .trim_end_matches(|c| PYTHON_SPACE.contains(c));
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
            data,
        });
    }
}

#[cfg(test)]
#[path = "collect_tests.rs"]
mod tests;
