// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Build the reply sections that the discovery decides, as `collect._Collection` of the Python
//! Dart collector builds them: the inputs, the source listing, the file facts, the gaps of the
//! problems and their evidence.
//!
//! Slice 3a of #880 adds the parse: a source with a syntax error has no file fact and a
//! `SyntaxError` gap, and each other concern of the parse is a gap. The Python collector also
//! drops the file fact of a `part of` file and of a source with no unique owner; slices 4a and
//! 4b add those rules.

use std::collections::BTreeMap;

use archkeel_facts::data::GapData;
use archkeel_facts::envelope::{Evidence, FileFact, Input, Role};
use archkeel_facts::identity::{sha256_hex, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::{Area, EvidenceClass, ExceptionName};
use archkeel_facts::Record;
use serde_json::json;

use crate::discover::{Discovery, Source};
use crate::pubspec::SdkState;
use crate::syntax::{ConcernKind, Span, Syntax};
use archkeel_pytext::splitlines;

use crate::pytext::{is_blank, rstrip};

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

/// Build the sections of `discovery` for the scan roots `roots`. `syntax` holds the parse of
/// each source, in the order of `discovery.sources`.
pub(crate) fn sections(discovery: &Discovery, roots: &[String], syntax: &[Syntax]) -> Sections {
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
    // `_prepare_sources`: the gaps of the parse first, then the snapshot problems. The first gap
    // of an id stays, and the file evidence is written last, as `_files` writes it.
    let mut gaps = BTreeMap::new();
    for (source, parsed) in discovery.sources.iter().zip(syntax) {
        for (span, kind, message) in parse_gaps(parsed) {
            let cited = cite(&mut evidence, source, span);
            let (id, record) = gap(&source.rel_path, span.line, kind, message, Some(cited));
            gaps.entry(id).or_insert(record);
        }
    }
    for found in &discovery.problems {
        let content = discovery
            .sources
            .iter()
            .find(|source| source.rel_path == found.path)
            .map(|source| source.content.as_slice());
        let cited = content.map(|content| file_evidence(&mut evidence, &found.path, content));
        let (id, record) = gap(&found.path, 1, found.kind, &found.message, cited);
        gaps.entry(id).or_insert(record);
    }
    let (_, sdk_gaps, _) = sdk_support(discovery.sdk_state, discovery.sdk.as_deref());
    for record in sdk_gaps {
        gaps.entry(record.id.as_str().to_owned()).or_insert(record);
    }
    // A source with a syntax error has no file fact (`_prepare_sources` leaves it unparsed).
    let files = discovery
        .sources
        .iter()
        .zip(syntax)
        .filter(|(_, parsed)| parsed.first_error.is_none())
        .map(|(source, _)| {
            let id = file_evidence(&mut evidence, &source.rel_path, &source.content);
            FileFact::of(
                (&source.rel_path, &source.module),
                is_blank(&source.content),
                id,
            )
        })
        .collect();
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

/// `_sdk_constraints` writes one file-level gap without evidence: pubspec is not a source.
pub(crate) fn sdk_support(
    state: SdkState,
    value: Option<&str>,
) -> (bool, Vec<Record<GapFact>>, usize) {
    let support = crate::sdk::check(state, value);
    let gaps = support
        .message
        .map(|message| {
            gap(
                "pubspec.yaml",
                1,
                ExceptionName::SdkConstraintError,
                message,
                None,
            )
            .1
        })
        .into_iter()
        .collect();
    (support.message.is_none(), gaps, support.work)
}

/// The gaps of one parse, as `_prepare_sources` writes them: the first error as `SyntaxError`,
/// then each concern that is not a syntax error, with the kind of the concern.
fn parse_gaps(parsed: &Syntax) -> Vec<(&Span, ExceptionName, &str)> {
    let mut found = Vec::new();
    if let Some(span) = &parsed.first_error {
        let message = "syntax errors prevent complete source facts";
        found.push((span, ExceptionName::SyntaxError, message));
    }
    for concern in &parsed.concerns {
        let kind = match concern.kind {
            ConcernKind::SyntaxError if parsed.first_error.is_some() => continue,
            ConcernKind::SyntaxError => ExceptionName::DartSyntaxError,
            ConcernKind::InvalidEncoding => ExceptionName::InvalidEncoding,
            ConcernKind::LanguageVersionError => ExceptionName::LanguageVersionError,
            ConcernKind::UnsupportedDirective => ExceptionName::DirectiveError,
            ConcernKind::UnsupportedDeclaration => ExceptionName::UnsupportedDeclaration,
        };
        found.push((&concern.span, kind, concern.message.as_str()));
    }
    found
}

/// `_Collection._gap` evidence: the span when it has an excerpt, else the first line.
fn cite(evidence: &mut BTreeMap<String, Evidence>, source: &Source, span: &Span) -> String {
    if span.excerpt.is_empty() {
        return file_evidence(evidence, &source.rel_path, &source.content);
    }
    let found = Evidence::at(
        &source.rel_path,
        number(span.line),
        number(span.end_line),
        number(span.column),
        &span.excerpt,
    );
    let id = found.id.as_str().to_owned();
    evidence.insert(id.clone(), found);
    id
}

/// A line or a column as the evidence holds it. A source holds at most 4 MiB, so it fits.
fn number(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
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

/// The UNKNOWN record of one gap at `line` of `rel`, as `_Collection._gap` writes it.
fn gap(
    rel: &str,
    line: usize,
    kind: ExceptionName,
    message: &str,
    cited: Option<String>,
) -> (String, Record<GapFact>) {
    let id = stable_id(
        "COVERAGE",
        &[
            Part::Text(rel),
            Part::Number(number(line)),
            Part::Text(kind.as_str()),
            Part::Text(message),
        ],
    );
    let mut data = GapData::at("", "");
    data.reason = None;
    data.module = None;
    data.file = Some(rel.to_owned());
    data.line = Some(number(line));
    data.message = Some(message.to_owned());
    let record = Record {
        id: FactId::new(id.clone()),
        evidence_class: EvidenceClass::Unknown,
        area: Area::AnalysisCoverage,
        title: format!("{rel}:{line} could not be analyzed: {message}"),
        subjects: vec![format!("{rel}:{line}")],
        evidence_ids: cited.map(EvidenceId::new).into_iter().collect(),
        fact_ids: Vec::new(),
        data: GapFact::ExceptionGap {
            exception: kind,
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
