// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply of the producer as lists: what the unit tests and the test-only dump read.

use std::io;

use archkeel_wire::reply::{Facts, Record, ReplySection};
use archkeel_wire::stream::{Emit, SectionSink, TypedEmit};

use crate::kept::Pending;
use crate::records::{import_section, plan, Records};

/// The lists of a producer run: the sink of the unit tests and the test-only dump.
#[derive(Default)]
pub struct Lists {
    pub sections: Vec<ReplySection>,
}

impl SectionSink for Lists {
    fn section(&mut self, name: &'static str, fill: &mut dyn FnMut(Emit<'_>)) -> io::Result<()> {
        let mut records = Vec::new();
        fill(&mut |record: &Record| records.push(record.clone()));
        self.sections.push(ReplySection::Records(name, records));
        Ok(())
    }

    fn typed_section<D: archkeel_facts::IntoSection>(
        &mut self,
        _name: &'static str,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()> {
        let mut records = Vec::new();
        fill(&mut |record: &archkeel_facts::Record<D>| records.push(record.clone()));
        self.sections.push(ReplySection::Typed(D::section(records)));
        Ok(())
    }
}

/// The facts with every section in a list, and the ids that the records cite. This runs the
/// producer of the reply, so what a test sees is what the reply holds.
pub fn listed(facts: Facts, pending: &Pending) -> Result<(Facts, Vec<String>), String> {
    let (head, plan) = plan(facts, pending, true);
    let mut lists = Lists::default();
    let (tail, touched) = plan.write(&mut lists).map_err(|error| error.to_string())?;
    let facts = Facts {
        provenance: head.provenance,
        git_head: head.git_head,
        dirty: head.dirty,
        scope: head.scope,
        sections: lists.sections,
        features: head.features,
        constructs: head.constructs,
        inputs: head.inputs,
        files: head.files,
        imports: head.imports,
        selected_files: tail.selected_files,
        files_read: tail.files_read,
        gaps: tail.gaps,
        evidence: tail.evidence,
    };
    Ok((facts, touched))
}

/// The records of the sections by the names that the tests and the dump use: the result bindings
/// are the records of `bindings` that are not export witnesses.
pub fn records_of(facts: &Facts, touched: Vec<String>) -> Records {
    #[cfg(not(feature = "dump"))]
    drop(touched);
    let section = |name: &str| -> Vec<Record> {
        facts
            .sections
            .iter()
            .find_map(|section| match section {
                ReplySection::Records(found, records) if *found == name => Some(records.clone()),
                _ => None,
            })
            .unwrap_or_default()
    };
    let (witnesses, bindings) = section("bindings")
        .into_iter()
        .partition(|record| record.id.starts_with("ESM_EXPORT-"));
    Records {
        imports: import_section(facts).to_vec(),
        targets: facts.imports.clone(),
        witnesses,
        constructs: section("constructs"),
        symbols: section("symbols"),
        calls: section("calls"),
        references: section("references"),
        bindings,
        #[cfg(feature = "dump")]
        touched,
    }
}
