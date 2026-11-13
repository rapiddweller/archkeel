// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply of the producer as lists: what the unit tests and the test-only dump read.

use std::io;

use archkeel_facts::{BindingFact, IntoSection, Record, Section};
use archkeel_wire::stream::{SectionSink, TypedEmit};

use crate::collected::{Facts, Records};
use crate::kept::Pending;
use crate::records::plan;

/// The lists of a producer run: the sink of the unit tests and the test-only dump.
#[derive(Default)]
pub(crate) struct Lists {
    pub sections: Vec<Section>,
}

impl SectionSink for Lists {
    fn typed_section<D: IntoSection>(
        &mut self,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()> {
        let mut records = Vec::new();
        fill(&mut |record: &Record<D>| records.push(record.clone()));
        self.sections.push(D::section(records));
        Ok(())
    }
}

/// The facts with every section in a list, and the ids that the records cite. This runs the
/// producer of the reply, so what a test sees is what the reply holds.
pub(crate) fn listed(facts: Facts, pending: &Pending) -> Result<(Facts, Vec<String>), String> {
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

/// The records of the section of `D`.
pub(crate) fn section_of<D: IntoSection>(sections: &[Section]) -> Vec<Record<D>> {
    sections
        .iter()
        .find_map(D::records)
        .map(<[Record<D>]>::to_vec)
        .unwrap_or_default()
}

/// An export witness: the record of `bindings` that proves a module exports a name.
fn is_witness(record: &Record<BindingFact>) -> bool {
    matches!(&record.data, BindingFact::Bindings(data) if data.exports_name())
}

/// The records of the sections by the names that the tests and the dump use: the result bindings
/// are the records of `bindings` that are not export witnesses.
pub(crate) fn records_of(facts: &Facts, touched: Vec<String>) -> Records {
    #[cfg(not(feature = "dump"))]
    drop(touched);
    let (witnesses, bindings) = section_of(&facts.sections)
        .into_iter()
        .partition(is_witness);
    Records {
        imports: section_of(&facts.sections),
        targets: facts.imports.clone(),
        witnesses,
        constructs: section_of(&facts.sections),
        symbols: section_of(&facts.sections),
        calls: section_of(&facts.sections),
        references: section_of(&facts.sections),
        bindings,
        #[cfg(feature = "dump")]
        touched,
    }
}

/// A record as plain JSON: the tests read the fields by the names of the wire.
#[cfg(test)]
#[derive(Clone)]
pub(crate) struct Plain {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub data: serde_json::Value,
}

#[cfg(test)]
pub(crate) fn plains<D: archkeel_facts::FactData>(records: &[Record<D>]) -> Vec<Plain> {
    let plain = |record: &Record<D>| {
        let value = serde_json::to_value(record).unwrap();
        Plain {
            id: record.id.as_str().to_owned(),
            kind: record.data.wire_kind().to_owned(),
            title: record.title.clone(),
            data: value["data"].clone(),
        }
    };
    records.iter().map(plain).collect()
}
