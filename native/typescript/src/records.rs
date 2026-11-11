// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of PR 4.3a-3a: the imports expanded to one record for each bound name
//! (`_named_imports`, `_export_binding`) and the string comparisons (`_constructs`).
//!
//! The reply carries them under the capability `inner-uml-v1` (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.
//! The evidence that the new records cite is kept apart, so the evidence of the reply is unchanged.

use std::io::{self, Write};

use archkeel_facts::{
    BindingFact, CallFact, ConstructFact, ImportFact, IntoSection, Record, ReferenceFact,
    SymbolFact,
};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};

use crate::bound_names::expand;
use crate::cited::Cited;
use crate::collected::{Facts, Records};
use crate::construct_records::{constructs, STRING_LITERAL_COMPARE};
use crate::kept::Pending;
use crate::resolution::{local_imports, Imports};
use crate::script_effects::effect_record;
use crate::site_records::{self, Pass};
use crate::symbol_table::SymbolTable;
use crate::symbols;

/// What the producer holds before the first record is written: the targets of the imports, the
/// table of symbols and the evidence, which the records cite while they are written.
pub struct Plan<'p> {
    pending: &'p Pending,
    table: SymbolTable<'p>,
    imports: Imports,
    expanded: Records,
    cited: Cited,
    gaps: Vec<Record<archkeel_facts::GapFact>>,
    selected_files: Vec<String>,
    files_read: usize,
}

/// The one producer of the reply (AD-340, PR 4.3a-3d): the head, and the plan whose `write` gives
/// each section to a sink. The stream of the reply and the lists of the tests and the dump both run
/// this code, so a record that it drops or changes is dropped or changed in both. `track` keeps the
/// ids of the cited evidence, which only the dump needs.
pub fn plan(mut facts: Facts, pending: &Pending, track: bool) -> (Head, Plan<'_>) {
    let mut cited = Cited::owning(std::mem::take(&mut facts.evidence), track);
    let mut expanded = Records::default();
    expand(&facts, pending, &mut cited, &mut expanded);
    // The script analysis comes after the named imports and before the symbols, as in Python.
    for (rel, span) in &pending.script.cites {
        cited.cite(rel, span);
    }
    if !expanded.witnesses.is_empty() || pending.dependency_scope {
        let at = facts
            .features
            .iter()
            .position(|name| *name == "inner-uml-v1");
        facts.features.insert(
            at.map_or(facts.features.len(), |at| at.saturating_add(1)),
            "script-globals-v1",
        );
    }
    expanded
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let imports = local_imports(pending, &facts);
    let head = Head {
        provenance: facts.provenance.clone(),
        git_head: facts.git_head.clone(),
        dirty: facts.dirty.clone(),
        scope: std::mem::take(&mut facts.scope),
        sections: sections(),
        features: std::mem::take(&mut facts.features),
        constructs: vec![(STRING_LITERAL_COMPARE, "partial")],
        inputs: std::mem::take(&mut facts.inputs),
        files: std::mem::take(&mut facts.files),
        imports: std::mem::take(&mut expanded.targets),
    };
    let plan = Plan {
        pending,
        table: SymbolTable::build(pending),
        imports,
        expanded,
        cited,
        gaps: std::mem::take(&mut facts.gaps),
        selected_files: std::mem::take(&mut facts.selected_files),
        files_read: facts.files_read,
    };
    (head, plan)
}

impl Plan<'_> {
    /// Write the sections in the order of the capability. The records of the symbols, the calls and
    /// the references are made and given one at a time, so the records of a project are never alive
    /// together. The evidence is cited in the order of Python: imports, symbols, calls, references,
    /// constructs. The tail has the evidence; the second value has the ids that the records cited.
    pub fn write(mut self, sink: &mut impl SectionSink) -> io::Result<(Tail, Vec<String>)> {
        let Self {
            pending,
            table,
            imports,
            expanded,
            cited,
            gaps,
            ..
        } = &mut self;
        sink.write_typed_section::<ImportFact>(|emit| expanded.imports.iter().for_each(emit))?;
        sink.write_typed_section::<archkeel_facts::GapFact>(|emit| gaps.iter().for_each(emit))?;
        sink.write_typed_section::<SymbolFact>(|emit| {
            symbols::each(table, cited, &mut |record| emit(&record));
        })?;
        let mut head = pending.script.publications.clone();
        head.extend(std::mem::take(&mut expanded.witnesses));
        let mut placed = Vec::new();
        sink.write_typed_section::<CallFact>(|emit| {
            placed.extend(site_records::pass(
                table,
                pending,
                imports,
                cited,
                Pass::Calls(emit),
            ));
        })?;
        sink.write_typed_section::<ReferenceFact>(|emit| {
            placed.extend(site_records::pass(
                table,
                pending,
                imports,
                cited,
                Pass::References(&mut *emit),
            ));
            for effect in &pending.script.effects {
                emit(&effect_record(cited, effect));
            }
        })?;
        // Python makes the bindings of the calls and the references in one pass over the sites.
        placed.sort_by_key(|(at, _)| *at);
        head.extend(placed.into_iter().map(|(_, record)| record));
        let bindings = head;
        sink.write_typed_section::<BindingFact>(|emit| bindings.iter().for_each(emit))?;
        constructs(pending, cited, expanded);
        sink.write_typed_section::<ConstructFact>(|emit| {
            expanded.constructs.iter().for_each(emit)
        })?;
        let (evidence, touched) = self.cited.finish();
        let tail = Tail {
            selected_files: self.selected_files,
            files_read: self.files_read,
            gaps: self.gaps,
            evidence,
        };
        Ok((tail, touched))
    }
}

/// The sections that the capability declares, in the order that the reply writes them.
fn sections() -> Vec<&'static str> {
    vec![
        ImportFact::section_name(),
        archkeel_facts::GapFact::section_name(),
        SymbolFact::section_name(),
        CallFact::section_name(),
        ReferenceFact::section_name(),
        BindingFact::section_name(),
        ConstructFact::section_name(),
    ]
}

/// The reply of the facts of a request, written into `out` (a compressed 8.0.0 or 9.0.0 reply).
pub fn write_reply(
    version: Version,
    facts: Facts,
    pending: &Pending,
    out: impl Write,
) -> Result<(), String> {
    let (head, plan) = plan(facts, pending, false);
    encode_stream(version, head, out, |writer| {
        plan.write(writer).map(|(tail, _)| tail)
    })
}

#[cfg(test)]
#[path = "records_tests.rs"]
mod tests;
