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
use archkeel_wire::reply::{Evidence, Facts, Record, Target};
use serde_json::{json, Value};

use crate::cited::Cited;
use crate::import_bindings::ImportBinding;
use crate::kept::{Kept, Pending};
use crate::site_records;
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
    /// The evidence that the records above cite and the reply does not hold yet.
    pub evidence: Vec<Evidence>,
}

/// `classified`: the subjects without empty names, sorted; the evidence ids sorted.
fn sorted(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values
}

/// Build the records of this phase from the facts of a collection and the kept syntax.
pub fn build(facts: &Facts, pending: &Pending) -> Records {
    let mut cited = Cited::seeded(&facts.evidence);
    let mut records = Records::default();
    expand(facts, pending, &mut cited, &mut records);
    records
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let table = SymbolTable::build(pending);
    records.symbols = symbols::build(&table, &mut cited);
    let sites = site_records::build(&table, pending, facts, &mut cited);
    (records.calls, records.references, records.bindings) =
        (sites.calls, sites.references, sites.bindings);
    constructs(pending, &mut cited, &mut records);
    records.evidence = cited.cited();
    records
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
