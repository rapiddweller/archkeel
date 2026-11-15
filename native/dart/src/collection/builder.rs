// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of the collection assembly and the helpers that every pass of it shares. This is the
//! leaf of `collection`: no pass calls back into the module that runs them.

use super::types::{Fact, Input, Output, RecordKind};
use crate::declarations::work::Stop;
use crate::declarations::{types as decl, Assembly};
use crate::syntax::{Site, Span};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::vocab::{Area, ExceptionName};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct Builder<'a> {
    pub(super) input: &'a Input,
    pub(super) decl: Assembly,
    pub(super) files: Vec<decl::File>,
    pub(super) by_path: BTreeMap<String, usize>,
    pub(super) parsed: BTreeSet<String>,
    pub(super) incomplete_paths: BTreeSet<String>,
    pub(super) incomplete_ids: BTreeSet<String>,
    pub(super) symbol_indices: BTreeMap<String, usize>,
    pub(super) directive_indices: BTreeMap<(String, usize), usize>,
    pub(super) name_indices: BTreeMap<(String, String), usize>,
    pub(super) site_indices: BTreeMap<String, usize>,
    pub(super) construction_indices: BTreeMap<(String, usize, String), usize>,
    pub(super) scopes: BTreeMap<(String, Option<String>), Vec<usize>>,
    pub(super) sdk_supported: bool,
    pub(super) output: Output,
}

impl<'a> Builder<'a> {
    pub(super) fn new(input: &'a Input) -> Self {
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

    pub(super) fn file(&self, rel: &str) -> Result<&decl::File, Stop> {
        self.by_path
            .get(rel)
            .and_then(|index| self.files.get(*index))
            .ok_or(Stop::Input)
    }

    pub(super) fn cite(&mut self, rel: &str, span: &Span) -> Result<String, Stop> {
        self.decl.work.copies(span)?;
        let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
        let file = self.files.get(index).ok_or(Stop::Input)?;
        Ok(self.decl.cite(file, span))
    }

    pub(super) fn gap(
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

    pub(super) fn symbol_index(&self, name: &str) -> Option<usize> {
        self.symbol_indices.get(name).copied()
    }

    pub(super) fn symbol_kind(&self, name: &str) -> Option<decl::Kind> {
        self.symbol_index(name)
            .and_then(|index| self.decl.output.symbols.get(index))
            .map(|symbol| symbol.kind)
    }

    pub(super) fn names(&self, rel: &str, name: &str) -> Result<Vec<String>, Stop> {
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
}

pub(super) fn file_span() -> Span {
    Span {
        line: 1,
        end_line: 1,
        column: 0,
        excerpt: String::new(),
        start_byte: 0,
        end_byte: 0,
    }
}

pub(super) fn id(prefix: &str, rel: &str, start: usize, rest: &[Part<'_>]) -> String {
    let mut parts = vec![
        Part::Text(rel),
        Part::Number(i64::try_from(start).unwrap_or(i64::MAX)),
    ];
    parts.extend_from_slice(rest);
    stable_id(prefix, &parts)
}

pub(super) fn package(module: &str) -> String {
    module
        .rsplit_once('.')
        .map_or("", |(value, _)| value)
        .to_owned()
}

pub(super) fn fact<T>(
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

pub(super) fn expression(site: &Site) -> String {
    site.expression_source
        .as_ref()
        .filter(|text| !text.is_empty())
        .unwrap_or(&site.expression)
        .clone()
}
