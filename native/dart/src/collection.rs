// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The complete raw collection assembly; resolution remains a typed input (AD-400).

mod imports;
mod inventories;
mod prepare;
mod sites;
mod targets;
pub(crate) mod types;

use crate::declarations::work::Stop;
use crate::declarations::{types as decl, Assembly};
use crate::syntax::{Site, Span};
use archkeel_facts::envelope::{Capabilities, FileFact, SectionName};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::vocab::{Area, ExceptionName};
use std::collections::{BTreeMap, BTreeSet};
use types::*;

const SECTIONS: [SectionName; 6] = [
    SectionName::Imports,
    SectionName::Unknowns,
    SectionName::Symbols,
    SectionName::Calls,
    SectionName::References,
    SectionName::Bindings,
];

pub(crate) fn build(input: &Input) -> Output {
    let mut builder = Builder::new(input);
    if let Err(stop) = builder.run() {
        let message = match stop {
            Stop::Input => {
                "CollectionInputGap: Dart collection resolver inputs are incomplete or inconsistent"
            }
            Stop::Work => "CollectionWorkLimit: Dart collection assembly passes the work limit",
        };
        let (_, gap) =
            crate::records::gap(".", 1, ExceptionName::UnsupportedDeclaration, message, None);
        return Output {
            gaps: vec![gap],
            work: builder.decl.work.spent(),
            ..Output::default()
        };
    }
    builder.finish()
}

struct Builder<'a> {
    input: &'a Input,
    decl: Assembly,
    files: Vec<decl::File>,
    by_path: BTreeMap<String, usize>,
    parsed: BTreeSet<String>,
    incomplete_paths: BTreeSet<String>,
    incomplete_ids: BTreeSet<String>,
    symbol_indices: BTreeMap<String, usize>,
    directive_indices: BTreeMap<(String, usize), usize>,
    name_indices: BTreeMap<(String, String), usize>,
    site_indices: BTreeMap<String, usize>,
    construction_indices: BTreeMap<(String, usize, String), usize>,
    scopes: BTreeMap<(String, Option<String>), Vec<usize>>,
    sdk_supported: bool,
    output: Output,
}

impl<'a> Builder<'a> {
    fn new(input: &'a Input) -> Self {
        Self {
            input,
            decl: Assembly::default(),
            files: Vec::new(),
            by_path: BTreeMap::new(),
            parsed: BTreeSet::new(),
            incomplete_paths: BTreeSet::new(),
            incomplete_ids: BTreeSet::new(),
            symbol_indices: BTreeMap::new(),
            directive_indices: BTreeMap::new(),
            name_indices: BTreeMap::new(),
            site_indices: BTreeMap::new(),
            construction_indices: BTreeMap::new(),
            scopes: BTreeMap::new(),
            sdk_supported: true,
            output: Output::default(),
        }
    }

    fn run(&mut self) -> Result<(), Stop> {
        self.decl.work.input(self.input)?;
        self.prepare()?;
        self.index_answers()?;
        let mut files = Vec::new();
        for file in &self.files {
            self.decl.work.copies(file)?;
            if self.parsed.contains(&file.rel) {
                files.push(file.clone());
            }
        }
        self.decl.run(&decl::Input { files })?;
        for (index, scope) in self.decl.output.scope_candidates.iter().enumerate() {
            self.decl.work.copies(scope)?;
            self.scopes
                .entry((scope.0.clone(), None))
                .or_default()
                .push(index);
            self.scopes
                .entry((scope.0.clone(), Some(scope.1.clone())))
                .or_default()
                .push(index);
        }
        for (index, symbol) in self.decl.output.symbols.iter().enumerate() {
            self.decl.work.text(&symbol.data.qualified_name)?;
            self.symbol_indices
                .insert(symbol.data.qualified_name.clone(), index);
        }
        self.imports()?;
        self.bases()?;
        self.sites()?;
        self.duplicates()?;
        for problem in &self.input.resolver.problems {
            self.decl.work.copies(problem)?;
            self.gap(
                &problem.path,
                problem.span.as_ref().unwrap_or(&file_span()),
                problem.kind,
                &problem.message,
                None,
            )?;
        }
        self.finalize_inventories()?;
        self.source_facts()?;
        Ok(())
    }

    fn index_answers(&mut self) -> Result<(), Stop> {
        for (index, answer) in self.input.resolver.directives.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .directive_indices
                .insert((answer.rel.clone(), answer.start), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.names.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .name_indices
                .insert((answer.rel.clone(), answer.name.clone()), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.sites.iter().enumerate() {
            self.decl.work.copies(answer)?;
            if self
                .site_indices
                .insert(answer.rel.clone(), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
        }
        for (index, answer) in self.input.resolver.constructions.iter().enumerate() {
            self.decl.work.copies(answer)?;
            let key = (answer.rel.clone(), answer.start, answer.expression.clone());
            if self.construction_indices.insert(key, index).is_some() {
                return Err(Stop::Input);
            }
        }
        Ok(())
    }

    fn file(&self, rel: &str) -> Result<&decl::File, Stop> {
        self.by_path
            .get(rel)
            .and_then(|index| self.files.get(*index))
            .ok_or(Stop::Input)
    }

    fn cite(&mut self, rel: &str, span: &Span) -> Result<String, Stop> {
        self.decl.work.copies(span)?;
        let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
        let file = self.files.get(index).ok_or(Stop::Input)?;
        Ok(self.decl.cite(file, span))
    }

    fn gap(
        &mut self,
        rel: &str,
        span: &Span,
        kind: ExceptionName,
        message: &str,
        evidence: Option<Vec<EvidenceId>>,
    ) -> Result<(), Stop> {
        self.decl.work.text(message)?;
        let (id, mut record) = crate::records::gap(rel, span.line, kind, message, None);
        if self.decl.gaps.contains_key(&id) {
            return Ok(());
        }
        record.evidence_ids = match evidence {
            Some(values) => values,
            None => match self
                .by_path
                .get(rel)
                .and_then(|index| self.files.get(*index))
            {
                Some(file) => vec![EvidenceId::new(self.decl.gap_cite(file, span))],
                None => Vec::new(),
            },
        };
        self.decl.gaps.insert(id, record);
        Ok(())
    }

    fn symbol_index(&self, name: &str) -> Option<usize> {
        self.symbol_indices.get(name).copied()
    }

    fn symbol_kind(&self, name: &str) -> Option<decl::Kind> {
        self.symbol_index(name)
            .and_then(|index| self.decl.output.symbols.get(index))
            .map(|symbol| symbol.kind)
    }

    fn names(&self, rel: &str, name: &str) -> Result<Vec<String>, Stop> {
        self.decl.work.text(name)?;
        let key = (rel.to_owned(), name.to_owned());
        let answer = self
            .name_indices
            .get(&key)
            .and_then(|index| self.input.resolver.names.get(*index))
            .ok_or(Stop::Input)?;
        self.decl.work.copies(&answer.targets)?;
        Ok(answer.targets.clone())
    }

    fn source_facts(&mut self) -> Result<(), Stop> {
        for rel in &self.parsed {
            self.decl.work.charge(1)?;
            let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
            let source = self.input.files.get(index).ok_or(Stop::Input)?;
            let file = self.files.get(index).ok_or(Stop::Input)?;
            if file.module != source.file.module {
                continue;
            }
            self.decl.work.text(&source.content)?;
            let evidence = self.decl.gap_cite(file, &file_span());
            self.output.files.push(FileFact::of(
                (rel, &file.module),
                crate::pytext::is_blank(source.content.as_bytes()),
                evidence,
            ));
        }
        self.decl.work.copies(&self.input.inputs)?;
        self.output.inputs = self.input.inputs.clone();
        self.output.source_digest = crate::records::listing_digest(&self.output.inputs);
        self.output.scope = self
            .input
            .roots
            .iter()
            .map(|root| crate::records::pattern(root))
            .collect();
        self.output.git_head.clone_from(&self.input.git_head);
        self.output.dirty = Some(self.input.dirty.clone());
        self.output.capabilities = Some(Capabilities {
            constructs: Vec::new(),
            resolution_features: vec!["inner-uml-v1".to_owned()],
            sections: SECTIONS.to_vec(),
        });
        self.output.selected_files = self.by_path.keys().cloned().collect();
        self.output.files_read = self.files.len();
        self.output.files_parsed = self.parsed.len();
        self.output.full_scope = self.decl.gaps.is_empty() && !self.files.is_empty();
        Ok(())
    }

    fn finish(mut self) -> Output {
        self.output.symbols = self.decl.output.symbols;
        self.output.symbols.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.imports.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.calls.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.references.sort_by(|a, b| a.id.cmp(&b.id));
        self.output.gaps = self.decl.gaps.into_values().collect();
        self.output.evidence = self.decl.evidence.into_values().collect();
        self.output.work = self.decl.work.spent();
        self.output
    }
}

fn file_span() -> Span {
    Span {
        line: 1,
        end_line: 1,
        column: 0,
        excerpt: String::new(),
        start_byte: 0,
        end_byte: 0,
    }
}

fn id(prefix: &str, rel: &str, start: usize, rest: &[Part<'_>]) -> String {
    let mut parts = vec![
        Part::Text(rel),
        Part::Number(i64::try_from(start).unwrap_or(i64::MAX)),
    ];
    parts.extend_from_slice(rest);
    stable_id(prefix, &parts)
}

fn package(module: &str) -> String {
    module
        .rsplit_once('.')
        .map_or("", |(value, _)| value)
        .to_owned()
}

fn fact<T>(
    id: String,
    kind: RecordKind,
    title: String,
    subjects: Vec<String>,
    evidence: String,
    data: T,
) -> Fact<T> {
    let area = match kind {
        RecordKind::Import => Area::Dependencies,
        RecordKind::Call | RecordKind::Reference => Area::Source,
    };
    decl::Symbol::new(
        id,
        kind,
        title,
        subjects,
        vec![EvidenceId::new(evidence)],
        data,
        area,
    )
}

fn expression(site: &Site) -> String {
    site.expression_source
        .as_ref()
        .filter(|text| !text.is_empty())
        .unwrap_or(&site.expression)
        .clone()
}
