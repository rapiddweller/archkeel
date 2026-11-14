// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import survey of one package (AD-450): the selected sources with their digests, the file
//! fact of each library, the owner of each part, the import records with their targets and a
//! gap for each case that the survey does not prove.
//!
//! The survey is not the whole collection. It parses the directives only, so it gives no
//! symbol, call, reference or binding, and the reply declares the sections `imports` and
//! `unknowns` only.

mod edges;
mod names;
mod package;
mod parts;
mod uri;

use std::collections::{BTreeMap, HashMap};

use archkeel_facts::envelope::{Coverage, Evidence, FileFact, Input, Target};
use archkeel_facts::ids::{FactId, ModuleName};
use archkeel_facts::request::DartRequest;
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_snapshot::Snapshot;

use crate::discover::{discover, scan_roots, Discovery, Source};
use crate::parse::DartParser;
use crate::pytext::is_blank;
use crate::records::{discovery_gaps, file_evidence, inputs, parse_gaps, pattern};
use crate::syntax::{DirectiveKind, Syntax};
pub use names::{GapName, NamedGap};
use names::{Gaps, Place};

/// The parse budget of one source in bytes (#1097). A larger source is not parsed.
pub const PARSE_BUDGET_BYTES: usize = 1 << 20;

/// The owner of one part file: the library whose module holds the edges of the part.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PartOwner {
    pub part: String,
    pub library: String,
    pub module: ModuleName,
}

/// The typed result of the survey. `unknowns` and `coverage.gaps` hold the same records.
#[derive(Debug)]
pub struct Survey {
    /// Sorted by path: the selected sources and the `pubspec.yaml`.
    pub inputs: Vec<Input>,
    /// The glob of each scan root.
    pub scope: Vec<String>,
    /// One file fact for each library that the survey proves, sorted by path.
    pub files: Vec<FileFact>,
    /// Sorted by the path of the part.
    pub parts: Vec<PartOwner>,
    /// Sorted by id; `targets` holds one target for each record, in the same order.
    pub imports: Vec<Record<ImportFact>>,
    pub targets: Vec<Target>,
    /// Sorted by id.
    pub unknowns: Vec<Record<GapFact>>,
    /// The survey gaps of `unknowns` with their names, sorted by id.
    pub named: Vec<NamedGap>,
    pub coverage: Coverage,
    /// Sorted by id.
    pub evidence: Vec<Evidence>,
}

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
    by_rel: HashMap<&'a str, usize>,
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

/// The survey of `request`. An error is a refusal of the whole request, never a partial survey.
pub fn survey(request: &DartRequest) -> Result<Survey, String> {
    if request.excludes_test_sources() {
        return Err("the Dart import survey does not support exclude_test_sources".to_owned());
    }
    let roots = scan_roots(&request.scope.roots);
    let mut snapshot = Snapshot::open_root(&request.snapshot.root)?;
    let found = discover(&mut snapshot, &request.scope.namespace, &roots)?;
    let mut gaps = Gaps::default();
    discovery_gaps(&found, &mut gaps.evidence, &mut gaps.records);
    package::package_gaps(&mut snapshot, &found, &mut gaps);
    let index = index(&found, &mut gaps)?;
    let owners = parts::owners(&mut snapshot, &index, &mut gaps);
    let built = edges::edges(&mut snapshot, &index, &owners, &mut gaps);
    let files = file_facts(&index, &mut gaps);
    let parts = owners
        .iter()
        .map(|(part, library)| PartOwner {
            part: found.sources[*part].rel_path.clone(),
            library: found.sources[*library].rel_path.clone(),
            module: ModuleName::new(&found.sources[*library].module),
        })
        .collect();
    let unknowns: Vec<Record<GapFact>> = gaps.records.into_values().collect();
    let named = gaps
        .named
        .into_iter()
        .map(|(id, name)| NamedGap {
            name,
            id: FactId::new(id),
        })
        .collect();
    let selected: Vec<String> = found.sources.iter().map(|s| s.rel_path.clone()).collect();
    let read = selected.len() + usize::from(found.pubspec_digest.is_some());
    Ok(Survey {
        inputs: inputs(&found),
        scope: roots.iter().map(|root| pattern(root)).collect(),
        coverage: Coverage::of((read, files.len()), selected, unknowns.clone()),
        files,
        parts,
        imports: built.imports,
        targets: built.targets,
        unknowns,
        named,
        evidence: gaps.evidence.into_values().collect(),
    })
}

/// Parse the directives of each source within the budget and give each source its kind. The
/// parse gaps are added to `gaps`; a concern of a URI that is not a plain string gets its name.
fn index<'a>(found: &'a Discovery, gaps: &mut Gaps) -> Result<Index<'a>, String> {
    let mut parser = DartParser::new()?;
    let collided: Vec<&str> = found
        .problems
        .iter()
        .filter(|problem| problem.kind == archkeel_facts::vocab::ExceptionName::DartModuleCollision)
        .map(|problem| problem.path.as_str())
        .collect();
    let mut syntax = Vec::with_capacity(found.sources.len());
    let mut kinds = Vec::with_capacity(found.sources.len());
    for source in &found.sources {
        if source.content.len() > PARSE_BUDGET_BYTES {
            let message = format!("the source is over the parse budget of {PARSE_BUDGET_BYTES} bytes; it is not parsed");
            gaps.named(
                GapName::DartParseBudget,
                Place::File(&source.rel_path),
                &message,
            );
            syntax.push(None);
            kinds.push(Kind::Unknown);
            continue;
        }
        let parsed = parser.directives(&source.content);
        for (span, kind, message) in parse_gaps(&parsed) {
            if kind == archkeel_facts::vocab::ExceptionName::DirectiveError {
                gaps.named(
                    GapName::DartUriNotLiteral,
                    Place::Span(source, span),
                    message,
                );
            } else {
                let cited = crate::records::cite(&mut gaps.evidence, source, span);
                gaps.plain((&source.rel_path, span.line), kind, message, Some(cited));
            }
        }
        let part = parsed
            .directives
            .iter()
            .any(|directive| directive.kind == DirectiveKind::PartOf);
        kinds.push(
            if parsed.first_error.is_some() || collided.contains(&source.rel_path.as_str()) {
                Kind::Unknown
            } else if part {
                Kind::Part
            } else {
                Kind::Library
            },
        );
        syntax.push(Some(parsed));
    }
    Ok(Index {
        package: &found.package_name,
        sources: &found.sources,
        by_rel: found
            .sources
            .iter()
            .enumerate()
            .map(|(at, source)| (source.rel_path.as_str(), at))
            .collect(),
        syntax,
        kinds,
    })
}

/// The file fact of each library, sorted by path as the sources are.
fn file_facts(index: &Index<'_>, gaps: &mut Gaps) -> Vec<FileFact> {
    index
        .sources
        .iter()
        .zip(&index.kinds)
        .filter(|(_, kind)| **kind == Kind::Library)
        .map(|(source, _)| {
            let cited = file_evidence(&mut gaps.evidence, &source.rel_path, &source.content);
            FileFact::of(
                (&source.rel_path, &source.module),
                is_blank(&source.content),
                cited,
            )
        })
        .collect()
}

/// Each edge as `<source module> import|export <target module>`, sorted.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn edge_rows(found: &Survey) -> Vec<String> {
    let mut rows: Vec<String> = found
        .imports
        .iter()
        .map(|record| {
            let data = record.data.data();
            let verb = if data.reexport { "export" } else { "import" };
            format!(
                "{} {verb} {}",
                data.source_module.as_str(),
                data.target_module.as_str()
            )
        })
        .collect();
    rows.sort();
    rows
}

/// The count of the gaps by survey name, or by problem kind for a gap without a name.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn gap_rows(found: &Survey) -> BTreeMap<String, usize> {
    let mut rows = BTreeMap::new();
    for record in &found.unknowns {
        let named = found.named.iter().find(|gap| gap.id == record.id);
        let key = match (named, &record.data) {
            (Some(gap), _) => gap.name.as_str().to_owned(),
            (None, GapFact::ExceptionGap { exception, .. }) => exception.as_str().to_owned(),
            (None, _) => "other".to_owned(),
        };
        *rows.entry(key).or_insert(0) += 1;
    }
    rows
}

/// The owner of each owned part, keyed by the index of the part.
pub(crate) type Owners = BTreeMap<usize, usize>;

#[cfg(test)]
#[path = "survey/survey_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "survey/fixture_tests.rs"]
mod fixture_tests;

#[cfg(test)]
#[path = "survey/plant_tests.rs"]
mod plant_tests;
