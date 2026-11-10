// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of PR 4.3a-3a: the imports expanded to one record for each bound name
//! (`_named_imports`, `_export_binding`) and the string comparisons (`_constructs`).
//!
//! The reply carries them under the capability `inner-uml-v1` (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.
//! The evidence that the new records cite is kept apart, so the evidence of the reply is unchanged.

use std::collections::{HashMap, HashSet};
use std::io::{self, Write};

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::FactId;
use archkeel_facts::reply::Target;
use archkeel_facts::{ImportFact, Section};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::{Facts, Record, ReplySection};
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};
#[cfg(any(test, feature = "dump"))]
use archkeel_wire::stream::{Emit, TypedEmit};
use serde_json::json;

use crate::cited::Cited;
use crate::import_bindings::ImportBinding;
use crate::kept::{Kept, Pending};
use crate::resolution::{local_imports, Imports};
use crate::site_records::{self, Pass};
use crate::source::Span;
use crate::symbol_table::SymbolTable;
use crate::symbols;

/// The string comparison construct of `ForbiddenConstructKind`.
pub const STRING_LITERAL_COMPARE: &str = "string_literal_compare";

/// An import record of archkeel-facts (AD-345).
pub type ImportRecord = archkeel_facts::Record<ImportFact>;

/// The records of this phase, as the Python collector builds them.
#[derive(Default)]
pub struct Records {
    /// All import records, sorted by id: a statement with bound names is replaced by one record for
    /// each name.
    pub imports: Vec<ImportRecord>,
    /// The targets in the order of the walk, with the expanded statements in place.
    pub targets: Vec<Target>,
    /// The `ESM_EXPORT` records that the expanded imports cite, in the order of their first use.
    pub witnesses: Vec<Record>,
    /// The `TSCONSTRUCT` records, sorted by id.
    pub constructs: Vec<Record>,
    /// The `TSDEF` records, in the order of the symbol table (PR 4.3a-3b).
    #[cfg(any(test, feature = "dump"))]
    pub symbols: Vec<Record>,
    /// The `TSCALL`, `TSREF` and result binding records (PR 4.3a-3c).
    #[cfg(any(test, feature = "dump"))]
    pub calls: Vec<Record>,
    #[cfg(any(test, feature = "dump"))]
    pub references: Vec<Record>,
    #[cfg(any(test, feature = "dump"))]
    pub bindings: Vec<Record>,
    /// The ids of the evidence that the records above cite.
    #[cfg(feature = "dump")]
    pub touched: Vec<String>,
}

/// `classified`: the subjects without empty names, sorted; the evidence ids sorted.
fn sorted(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values
}

/// What the producer holds before the first record is written: the targets of the imports, the
/// table of symbols and the evidence, which the records cite while they are written.
pub struct Plan<'p> {
    pending: &'p Pending,
    table: SymbolTable<'p>,
    imports: Imports,
    expanded: Records,
    cited: Cited,
    gaps: Vec<archkeel_facts::Record<archkeel_facts::GapFact>>,
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
    expanded
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let imports = local_imports(pending, &facts);
    let head = Head {
        provenance: facts.provenance.clone(),
        git_head: facts.git_head.clone(),
        dirty: facts.dirty.clone(),
        scope: std::mem::take(&mut facts.scope),
        sections: SECTIONS.to_vec(),
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
        sink.write_typed_section("imports", |emit| expanded.imports.iter().for_each(emit))?;
        sink.write_typed_section("unknowns", |emit| gaps.iter().for_each(emit))?;
        sink.write_section("symbols", |emit| {
            symbols::each(table, cited, &mut |record| emit(&record));
        })?;
        let mut bindings = std::mem::take(&mut expanded.witnesses);
        sink.write_section("calls", |emit| {
            let pass = site_records::pass(table, pending, imports, cited, Pass::Calls, &mut |r| {
                emit(&r);
            });
            bindings.extend(pass);
        })?;
        let mut stray = 0;
        sink.write_section("references", |emit| {
            let pass =
                site_records::pass(table, pending, imports, cited, Pass::References, &mut |r| {
                    emit(&r);
                });
            stray = pass.len();
        })?;
        if stray > 0 {
            let reason = "a reference site made a result binding";
            return Err(io::Error::new(io::ErrorKind::InvalidData, reason));
        }
        sink.write_section("bindings", |emit| bindings.iter().for_each(emit))?;
        constructs(pending, cited, expanded);
        sink.write_section("constructs", |emit| {
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
const SECTIONS: [&str; 7] = [
    "imports",
    "unknowns",
    "symbols",
    "calls",
    "references",
    "bindings",
    "constructs",
];

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

/// The lists of a producer run: the sink of the unit tests and the test-only dump.
#[cfg(any(test, feature = "dump"))]
#[derive(Default)]
pub struct Lists {
    pub sections: Vec<ReplySection>,
}

#[cfg(any(test, feature = "dump"))]
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
#[cfg(any(test, feature = "dump"))]
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
#[cfg(any(test, feature = "dump"))]
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

/// The typed import records of the facts.
pub fn import_section(facts: &Facts) -> &[ImportRecord] {
    facts
        .sections
        .iter()
        .find_map(|section| match section {
            ReplySection::Typed(Section::Imports(records)) => Some(records.as_slice()),
            _ => None,
        })
        .unwrap_or_default()
}

/// `_named_imports`.
fn expand(facts: &Facts, pending: &Pending, cited: &mut Cited, records: &mut Records) {
    let by_id: HashMap<&str, &ImportRecord> = import_section(facts)
        .iter()
        .map(|record| (record.id.as_str(), record))
        .collect();
    let mut seen = HashSet::new();
    for target in &facts.imports {
        let Some(item) = by_id.get(target.import_id()) else {
            continue;
        };
        let bindings = pending
            .sites
            .get(item.id.as_str())
            .and_then(|(rel, line, column)| {
                let kept = pending.kept.get(rel)?;
                let own: &[ImportBinding] = kept.bindings.get(&(*line, *column))?;
                Some((kept, own))
            });
        let Some((kept, own)) = bindings else {
            records.imports.push((*item).clone());
            records.targets.push(target.clone());
            continue;
        };
        for (ordinal, binding) in (0_i64..).zip(own.iter()) {
            let bound_id = stable_id(
                "IMP_BINDING",
                &[Part::Text(item.id.as_str()), Part::Number(ordinal)],
            );
            let fact_ids = match known_witness(pending, kept, binding, target) {
                Some(witness) => vec![add_witness(cited, records, &mut seen, &witness)],
                None => Vec::new(),
            };
            records
                .imports
                .push(bound_record(item, &bound_id, binding, target, fact_ids));
            records.targets.push(target.with_import_id(&bound_id));
        }
    }
}

/// Record the witness of a proven name once and give its id.
fn add_witness(
    cited: &mut Cited,
    records: &mut Records,
    seen: &mut HashSet<String>,
    witness: &Witness,
) -> String {
    let (module, file, name, spans) = witness;
    let id = stable_id("ESM_EXPORT", &[Part::Text(module), Part::Text(name)]);
    if seen.insert(id.clone()) {
        let record = export_record(cited, &id, module, file, name, spans);
        records.witnesses.push(record);
    }
    id
}

/// The witness of a name that is proven: `(module, file, name, (declaration, export))`.
type Witness<'a> = (String, String, String, (&'a Span, &'a Span));

/// `known` of `_named_imports`: the name resolves to one export of a file that has no error.
fn known_witness<'a>(
    pending: &'a Pending,
    kept: &Kept,
    binding: &ImportBinding,
    target: &Target,
) -> Option<Witness<'a>> {
    let Target::Local {
        module,
        file,
        runtime_file: Some(_),
        ..
    } = target
    else {
        return None;
    };
    let destination = pending.kept.get(file)?;
    let [(declaration, export)] = destination.exports.get(&binding.imported)?.as_slice() else {
        return None;
    };
    // Faithful copies of Python conditions that other conditions already imply: some of them are
    // equivalent mutants, so no test should try to kill them one by one.
    let proven = binding.source_unique
        && !binding.namespace
        && !binding.type_only
        && !kept.has_error
        && !pending.partial
        && !destination.has_error;
    proven.then(|| {
        (
            module.clone(),
            file.clone(),
            binding.imported.clone(),
            (declaration, export),
        )
    })
}

/// One expanded import record: the statement record with the bound name written into its data.
fn bound_record(
    item: &ImportRecord,
    id: &str,
    binding: &ImportBinding,
    target: &Target,
    fact_ids: Vec<String>,
) -> ImportRecord {
    let known = !fact_ids.is_empty();
    let chain = match target {
        Target::Local { module, .. } if known => vec![format!("{module}.{}", binding.imported)],
        _ => Vec::new(),
    };
    let mut record = item.clone();
    let data = record.data.data_mut();
    data.symbol = (!binding.namespace).then(|| binding.imported.clone());
    data.binding = Some(binding.local.clone());
    data.symbols_known = known;
    data.reexport_chain = Some(chain);
    data.type_only = Some(binding.type_only);
    data.under_type_checking = binding.type_only;
    record.id = FactId::new(id);
    record.fact_ids = fact_ids.into_iter().map(FactId::new).collect();
    record
}

/// `_export_binding`: the witness that a module exports a name once.
fn export_record(
    cited: &mut Cited,
    id: &str,
    module: &str,
    file: &str,
    name: &str,
    spans: &(&Span, &Span),
) -> Record {
    let mut evidence_ids = vec![cited.cite(file, spans.0)];
    let export = cited.cite(file, spans.1);
    if !evidence_ids.contains(&export) {
        evidence_ids.push(export);
    }
    let mut data = serde_json::Map::new();
    data.insert("module".to_owned(), json!(module));
    data.insert("source_module".to_owned(), json!(module));
    data.insert("source_scope".to_owned(), json!(module));
    data.insert("name".to_owned(), json!(name));
    Record {
        id: id.to_owned(),
        evidence_class: "FACT",
        area: "source",
        kind: "bindings",
        title: "Exported source binding".to_owned(),
        subjects: sorted(vec![module.to_owned()]),
        evidence_ids: sorted(evidence_ids),
        fact_ids: Vec::new(),
        data,
    }
}

/// `_constructs`: one record for each written string comparison.
fn constructs(pending: &Pending, cited: &mut Cited, records: &mut Records) {
    let mut out = Vec::new();
    for (rel, kept) in &pending.kept {
        for (span, scope) in &kept.comparisons {
            let owner = match scope.as_deref().filter(|name| !name.is_empty()) {
                Some(name) => format!("{}.{name}", kept.module),
                None => kept.module.clone(),
            };
            let id = stable_id(
                "TSCONSTRUCT",
                &[
                    Part::Text(rel),
                    Part::Number(span.line),
                    Part::Number(span.column),
                    Part::Text(STRING_LITERAL_COMPARE),
                ],
            );
            let evidence = cited.cite(rel, span);
            let mut data = serde_json::Map::new();
            data.insert("owner".to_owned(), json!(owner));
            data.insert("construct".to_owned(), json!(STRING_LITERAL_COMPARE));
            out.push(Record {
                id,
                evidence_class: "FACT",
                area: "constructs",
                kind: STRING_LITERAL_COMPARE,
                title: format!("{owner} compares a written string literal"),
                subjects: sorted(vec![owner]),
                evidence_ids: vec![evidence],
                fact_ids: Vec::new(),
                data,
            });
        }
    }
    out.sort_by(|left, right| left.id.cmp(&right.id));
    records.constructs = out;
}

#[cfg(test)]
#[path = "records_tests.rs"]
mod tests;
