// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Build the reply sections that the discovery decides, as `collect._Collection` of the Python
//! Dart collector builds them: the inputs, the source listing, the file facts, the gaps of the
//! problems and their evidence.
//!
//! Slice 1 of #880 has no parse: each selected source gets a file fact. The Python collector
//! drops the file fact of a source with a syntax error or of a `part of` file; the parse slices
//! add that rule.

use std::collections::BTreeMap;

use archkeel_facts::data::GapData;
use archkeel_facts::envelope::{Evidence, FileFact, Input, Role};
use archkeel_facts::identity::{sha256_hex, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::Record;
use serde_json::json;

use crate::discover::{Discovery, Problem};
use crate::pytext::{is_blank, rstrip, splitlines};

/// The reply sections of a discovery.
pub(crate) struct Sections {
    /// Sorted by path.
    pub(crate) inputs: Vec<Input>,
    /// The SHA-256 of the input listing (`SourceInfo.source_digest`).
    pub(crate) source_digest: String,
    /// The glob of each scan root.
    pub(crate) scope: Vec<String>,
    pub(crate) files: Vec<FileFact>,
    /// Sorted by id.
    pub(crate) gaps: Vec<Record<GapFact>>,
    /// Sorted by id.
    pub(crate) evidence: Vec<Evidence>,
    pub(crate) selected_files: Vec<String>,
}

/// Build the sections of `discovery` for the scan roots `roots`.
pub(crate) fn sections(discovery: &Discovery, roots: &[String]) -> Sections {
    let mut evidence = BTreeMap::new();
    let mut inputs: Vec<Input> = discovery
        .sources
        .iter()
        .map(|source| Input {
            digest: source.digest.clone(),
            path: source.rel_path.clone(),
            role: Role::Selected,
        })
        .collect();
    if let Some(digest) = &discovery.pubspec_digest {
        inputs.push(Input {
            digest: digest.clone(),
            path: "pubspec.yaml".to_owned(),
            role: Role::Resolution,
        });
    }
    inputs.sort_by(|a, b| a.path.cmp(&b.path));
    let files = discovery
        .sources
        .iter()
        .map(|source| {
            let id = file_evidence(&mut evidence, &source.rel_path, &source.content);
            FileFact::of(
                (&source.rel_path, &source.module),
                is_blank(&source.content),
                id,
            )
        })
        .collect();
    let mut gaps = BTreeMap::new();
    for found in &discovery.problems {
        let content = discovery
            .sources
            .iter()
            .find(|source| source.rel_path == found.path)
            .map(|source| source.content.as_slice());
        let cited = content.map(|content| file_evidence(&mut evidence, &found.path, content));
        let (id, record) = gap(found, cited);
        gaps.entry(id).or_insert(record);
    }
    Sections {
        source_digest: listing_digest(&inputs),
        inputs,
        scope: roots.iter().map(|root| pattern(root)).collect(),
        files,
        gaps: gaps.into_values().collect(),
        evidence: evidence.into_values().collect(),
        selected_files: discovery
            .sources
            .iter()
            .map(|source| source.rel_path.clone())
            .collect(),
    }
}

/// `source_records.file_evidence`: line 1 when the first line holds text, else line 0.
fn file_evidence(evidence: &mut BTreeMap<String, Evidence>, rel: &str, content: &[u8]) -> String {
    let text = String::from_utf8_lossy(content);
    let first = splitlines(&text)
        .first()
        .map_or("", |line| rstrip(line))
        .to_owned();
    let found = if first.is_empty() {
        Evidence::at(rel, 0, 0, 0, "")
    } else {
        Evidence::at(rel, 1, 1, 0, &first)
    };
    let id = found.id.as_str().to_owned();
    evidence.insert(id.clone(), found);
    id
}

/// The UNKNOWN record of one problem, at line 1 of its path, as `_Collection._gap` writes it.
fn gap(found: &Problem, cited: Option<String>) -> (String, Record<GapFact>) {
    let kind = found.kind.as_str();
    let id = stable_id(
        "COVERAGE",
        &[
            Part::Text(&found.path),
            Part::Number(1),
            Part::Text(kind),
            Part::Text(&found.message),
        ],
    );
    let mut data = GapData::at("", "");
    data.reason = None;
    data.module = None;
    data.file = Some(found.path.clone());
    data.line = Some(1);
    data.message = Some(found.message.clone());
    let record = Record {
        id: FactId::new(id.clone()),
        evidence_class: EvidenceClass::Unknown,
        area: Area::AnalysisCoverage,
        title: format!("{}:1 could not be analyzed: {}", found.path, found.message),
        subjects: vec![format!("{}:1", found.path)],
        evidence_ids: cited.map(EvidenceId::new).into_iter().collect(),
        fact_ids: Vec::new(),
        data: GapFact::ExceptionGap {
            exception: found.kind,
            data,
        },
    };
    (id, record)
}

/// The Python listing: the compact JSON object of each input, joined with no separator.
fn listing_digest(inputs: &[Input]) -> String {
    let listing: String = inputs
        .iter()
        .map(|input| {
            // `preserve_order` keeps the keys in the Python order.
            json!({"path": input.path, "digest": input.digest, "role": input.role.as_str()})
                .to_string()
        })
        .collect();
    sha256_hex(listing.as_bytes())
}

fn pattern(root: &str) -> String {
    if root == "." {
        "**/*.dart".to_owned()
    } else {
        format!("{root}/**/*.dart")
    }
}

#[cfg(test)]
#[path = "records_tests.rs"]
mod tests;
