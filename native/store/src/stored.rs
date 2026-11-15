// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of one validated reply, kept in their typed form (AD-346).
//!
//! The store keeps the decoded `Reply` and finds a record by its id. One section dispatch
//! (`visit`) gives each record to a typed visitor. The Python byte formats (`canonical`, `pyrepr`,
//! `inventory`) see one record at a time as JSON (`saved`); no record is held in that form.
//!
//! An import record gets the projection of `check/evaluation/evaluate.py:evaluate_source` when it
//! is saved: an unresolved import gets `resolution`; a TypeScript import gets its external package
//! or builtin flag; a resolved import loses the five keys of the re-export bookkeeping.

use archkeel_facts::envelope::Reply;
use archkeel_facts::{FactData, Record, Section};

/// A typed visitor of the records of one section.
pub(crate) trait Visitor {
    fn record<D: FactData>(&mut self, section: &Section, record: &Record<D>) -> Result<(), String>;
}

fn each<D: FactData, V: Visitor>(
    section: &Section,
    records: &[Record<D>],
    visitor: &mut V,
) -> Result<(), String> {
    records
        .iter()
        .try_for_each(|record| visitor.record(section, record))
}

/// Give the records of `section` from `start` to `end` to `visitor`.
pub(crate) fn visit<V: Visitor>(
    section: &Section,
    start: usize,
    end: usize,
    visitor: &mut V,
) -> Result<(), String> {
    let range = start..end;
    match section {
        Section::Imports(records) => each(section, &records[range], visitor),
        Section::Symbols(records) => each(section, &records[range], visitor),
        Section::Calls(records) => each(section, &records[range], visitor),
        Section::References(records) => each(section, &records[range], visitor),
        Section::Bindings(records) => each(section, &records[range], visitor),
        Section::Constructs(records) => each(section, &records[range], visitor),
        Section::TypingSignals(records) => each(section, &records[range], visitor),
        Section::Unknowns(records) => each(section, &records[range], visitor),
    }
}

/// The validated reply.
pub(crate) struct Store {
    reply: Reply,
}

impl Store {
    pub(crate) fn new(reply: Reply) -> Self {
        Store { reply }
    }

    pub(crate) fn reply(&self) -> &Reply {
        &self.reply
    }
}
