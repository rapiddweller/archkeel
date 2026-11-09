// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of PR 4.3a-3a: the imports expanded to one record for each bound name
//! (`_named_imports`, `_export_binding`) and the string comparisons (`_constructs`).
//!
//! The reply does not carry them yet (AD-340): the capability stays
//! legacy until PR 4.3a-3d, so the host never reads them. The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.
//! The evidence that the new records cite is kept apart, so the evidence of the reply is unchanged.

use std::collections::{HashMap, HashSet};

use archkeel_wire::identity::{stable_id, Part};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::{Facts, Record, Target};
use archkeel_wire::stream::{encode_stream, Head, Tail};
use serde_json::{json, Value};

use crate::cited::Cited;
use crate::import_bindings::ImportBinding;
use crate::kept::{Kept, Pending};
use crate::resolution::local_imports;
use crate::site_records::{self, Pass};
use crate::source::Span;
use crate::symbol_table::SymbolTable;
use crate::symbols;

/// The string comparison construct of `ForbiddenConstructKind`.
pub const STRING_LITERAL_COMPARE: &str = "string_literal_compare";

/// The records of this phase, as the Python collector builds them.
#[derive(Default)]
pub struct Records {
    /// All import records, sorted by id: a statement with bound names is replaced by one record for
    /// each name.
    pub imports: Vec<Record>,
    /// The targets in the order of the walk, with the expanded statements in place.
    pub targets: Vec<Target>,
    /// The `ESM_EXPORT` records that the expanded imports cite, in the order of their first use.
    pub witnesses: Vec<Record>,
    /// The `TSCONSTRUCT` records, sorted by id.
    pub constructs: Vec<Record>,
    /// The `TSDEF` records, in the order of the symbol table (PR 4.3a-3b).
    pub symbols: Vec<Record>,
    /// The `TSCALL`, `TSREF` and result binding records (PR 4.3a-3c).
    pub calls: Vec<Record>,
    pub references: Vec<Record>,
    pub bindings: Vec<Record>,
    /// The ids of the evidence that the records above cite.
    pub touched: Vec<String>,
}

/// `classified`: the subjects without empty names, sorted; the evidence ids sorted.
fn sorted(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values
}

/// Build the records of this phase from the facts of a collection and the kept syntax.
pub fn build(facts: &mut Facts, pending: &Pending) -> Records {
    let mut cited = Cited::owning(std::mem::take(&mut facts.evidence));
    let mut records = Records::default();
    expand(&*facts, pending, &mut cited, &mut records);
    records
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let table = SymbolTable::build(pending);
    records.symbols = symbols::build(&table, &mut cited);
    let sites = site_records::build(&table, pending, &*facts, &mut cited);
    (records.calls, records.references, records.bindings) =
        (sites.calls, sites.references, sites.bindings);
    constructs(pending, &mut cited, &mut records);
    (facts.evidence, records.touched) = cited.finish();
    records
}

/// The reply of the inner-UML capability, written section by section (AD-340, PR 4.3a-3d). The
/// records of the symbols, the calls and the references are made and written one at a time, so the
/// records of a project are never alive together. The sections come in the order of the capability,
/// and the evidence is cited in the order of Python: imports, symbols, calls, references, constructs.
pub fn write_reply(
    version: Version,
    mut facts: Facts,
    pending: &Pending,
) -> Result<Vec<u8>, String> {
    let mut cited = Cited::owning(std::mem::take(&mut facts.evidence));
    let mut expanded = Records::default();
    expand(&facts, pending, &mut cited, &mut expanded);
    expanded
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let table = SymbolTable::build(pending);
    let imports = local_imports(pending, &facts);
    facts.features.insert(4, "inner-uml-v1");
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
    let gaps = std::mem::take(&mut facts.gaps);
    encode_stream(version, head, |writer| {
        writer.section("imports", |emit| expanded.imports.iter().for_each(emit))?;
        writer.section("unknowns", |emit| gaps.iter().for_each(emit))?;
        writer.section("symbols", |emit| {
            symbols::each(&table, &mut cited, &mut |record| emit(&record));
        })?;
        let mut bindings = std::mem::take(&mut expanded.witnesses);
        writer.section("calls", |emit| {
            let found = site_records::pass(
                &table,
                pending,
                &imports,
                &mut cited,
                Pass::Calls,
                &mut |record| emit(&record),
            );
            bindings.extend(found);
        })?;
        writer.section("references", |emit| {
            let none = site_records::pass(
                &table,
                pending,
                &imports,
                &mut cited,
                Pass::References,
                &mut |record| emit(&record),
            );
            debug_assert!(none.is_empty(), "a reference has no result binding");
        })?;
        writer.section("bindings", |emit| bindings.iter().for_each(emit))?;
        constructs(pending, &mut cited, &mut expanded);
        writer.section("constructs", |emit| {
            expanded.constructs.iter().for_each(emit)
        })?;
        Ok(Tail {
            selected_files: std::mem::take(&mut facts.selected_files),
            files_read: facts.files_read,
            gaps,
            evidence: cited.finish().0,
        })
    })
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

/// The sections, the targets and the capabilities of the inner-UML reply: what the native collector
/// produces now (AD-340, PR 4.3a-3d). Script facts are still missing, so the 4.2 gap stays and the
/// feature `script-globals-v1` is not declared.
#[cfg_attr(not(test), allow(dead_code))]
pub fn apply(facts: &mut Facts, records: Records) {
    let gaps = facts.gaps.clone();
    let mut bindings = records.witnesses;
    bindings.extend(records.bindings);
    facts.sections = vec![
        ("imports", records.imports),
        ("unknowns", gaps),
        ("symbols", records.symbols),
        ("calls", records.calls),
        ("references", records.references),
        ("bindings", bindings),
        ("constructs", records.constructs),
    ];
    facts.imports = records.targets;
    facts.constructs = vec![(STRING_LITERAL_COMPARE, "partial")];
    facts.features.insert(4, "inner-uml-v1");
}

/// `_named_imports`.
fn expand(facts: &Facts, pending: &Pending, cited: &mut Cited, records: &mut Records) {
    let by_id: HashMap<&str, &Record> = facts
        .sections
        .iter()
        .filter(|(name, _)| *name == "imports")
        .flat_map(|(_, list)| list.iter())
        .map(|record| (record.id.as_str(), record))
        .collect();
    let mut seen = HashSet::new();
    for target in &facts.imports {
        let Some(item) = by_id.get(target.import_id()) else {
            continue;
        };
        let bindings = pending.sites.get(&item.id).and_then(|(rel, line, column)| {
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
                &[Part::Text(&item.id), Part::Number(ordinal)],
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
    item: &Record,
    id: &str,
    binding: &ImportBinding,
    target: &Target,
    fact_ids: Vec<String>,
) -> Record {
    let known = !fact_ids.is_empty();
    let mut data = item.data.clone();
    let symbol = if binding.namespace {
        Value::Null
    } else {
        json!(binding.imported)
    };
    let chain = match target {
        Target::Local { module, .. } if known => vec![format!("{module}.{}", binding.imported)],
        _ => Vec::new(),
    };
    data.insert("symbol".to_owned(), symbol);
    data.insert("binding".to_owned(), json!(binding.local));
    data.insert("symbols_known".to_owned(), json!(known));
    data.insert("reexport_chain".to_owned(), json!(chain));
    data.insert("type_only".to_owned(), json!(binding.type_only));
    data.insert("under_type_checking".to_owned(), json!(binding.type_only));
    Record {
        id: id.to_owned(),
        fact_ids,
        data,
        ..item.clone()
    }
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
