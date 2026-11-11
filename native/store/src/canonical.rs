// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `architecture.json` 2.9 in the canonical columnar form (AD-346; owner decision, stage 1).
//!
//! The bytes equal `canonical_report_bytes` of `ir/codec_observation.py`: the record sections and
//! the evidence become rows, the repeated texts of the rows move to a sorted string table
//! (`ir/codec_strings.intern_strings`, observation policy), and the whole object is written with
//! sorted keys.
//!
//! The Python shell passes its parts of the observation as JSON: its own records are untyped
//! observation records until the observation moves to the core (WP6). A record or an evidence
//! entry that the store holds is passed as its id. Two passes read each stored record from its
//! typed form, one record at a time: the first collects the data fields and counts the texts, the
//! second writes the rows. Evidence of the store is written from its typed form.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::Write;

use archkeel_facts::envelope::Evidence;
use serde_json::{json, Map, Value};

use crate::pyjson::{write_list, write_text, write_value, Chunked, Plain, Texts};
use crate::shell::{Entry, Shell, Top};
use crate::stored::Store;
use crate::texts::{Counts, Interned};

/// `CLASSIFIED_SECTIONS` of `ir/model.py`.
pub(crate) const CLASSIFIED_SECTIONS: [&str; 20] = [
    "metrics",
    "declarations",
    "scope_observations",
    "packages",
    "modules",
    "symbols",
    "imports",
    "dependency_edges",
    "transitive_paths",
    "path_observations",
    "cycles",
    "calls",
    "references",
    "bindings",
    "typing_signals",
    "constructs",
    "contexts",
    "context_evidence",
    "violations",
    "unknowns",
];

/// `RECORD_FIELDS` and `EVIDENCE_FIELDS` of `ir/facts.py`.
pub(crate) const RECORD_FIELDS: [&str; 11] = [
    "id",
    "evidence_class",
    "area",
    "kind",
    "title",
    "subjects",
    "evidence_ids",
    "rule_ids",
    "fact_ids",
    "provenance",
    "data",
];
const EVIDENCE_FIELDS: [&str; 6] = ["id", "file", "line", "end_line", "column", "excerpt"];
const MISSING: &str = "$m";
// `entries` makes rows only in a record section.
const ROW_EVIDENCE: &str = "an evidence entry is never a row";

/// The entries of the coverage failures, which the shell sends as plain JSON: ids or objects.
fn failure_entries(value: Value) -> Result<Vec<Entry>, String> {
    let Value::Array(items) = value else {
        return Err("coverage.failures must be an array".to_owned());
    };
    items
        .into_iter()
        .map(|item| match item {
            Value::String(id) => Ok(Entry::Stored(id)),
            Value::Object(object) => Ok(Entry::Shell(Box::new(object))),
            _ => Err("coverage.failures holds an entry of an unknown form".to_owned()),
        })
        .collect()
}

/// Where the records of one section come from: the store, or the rows of the shell.
#[derive(Clone, Copy)]
struct Source<'a> {
    store: &'a Store,
    shell: &'a Shell,
    fields: &'a [String],
}

/// Run `action` on the object of a record; a stored record or a row lives only for the call.
fn with_record<T>(
    entry: &Entry,
    source: Source<'_>,
    action: impl FnOnce(&Map<String, Value>) -> Result<T, String>,
) -> Result<T, String> {
    match entry {
        Entry::Stored(id) => action(&source.store.saved(id)?),
        Entry::Shell(object) => action(object),
        Entry::Row(start, end) => {
            let head = &RECORD_FIELDS[..RECORD_FIELDS.len() - 1];
            action(&source.shell.record(*start, *end, head, source.fields)?)
        }
    }
}

fn field<'a>(item: &'a Map<String, Value>, key: &str) -> Result<&'a Value, String> {
    item.get(key)
        .ok_or_else(|| format!("a record has no field {key}"))
}

/// One record section: its sorted data fields, its entries and the data fields of its shell rows.
struct Rows {
    fields: Vec<String>,
    entries: Vec<Entry>,
    shell: Vec<String>,
}

/// The first pass over a section: its data fields, and the texts of its rows.
fn rows(entries: Vec<Entry>, source: Source<'_>, counts: &mut Counts) -> Result<Rows, String> {
    let mut fields = BTreeSet::new();
    let head = RECORD_FIELDS.len() - 1;
    for entry in &entries {
        if let Entry::Row(start, end) = entry {
            // A shell row counts its texts by index; its record is never built here.
            let row = source.shell.row(*start, *end);
            if row.len() != head + source.fields.len() {
                return Err("a shell row does not match its fields".to_owned());
            }
            row.iter().for_each(|at| counts.cell(*at));
            let present = source.fields.iter().zip(&row[head..]);
            fields.extend(
                present
                    .filter(|(_, at)| !source.shell.missing(**at))
                    .map(|(key, _)| key.clone()),
            );
            continue;
        }
        fields.extend(count_entry(entry, source, counts)?);
    }
    Ok(Rows {
        fields: fields.into_iter().collect(),
        entries,
        shell: source.fields.to_vec(),
    })
}

/// Count the texts of a stored record or a shell object; the answer is its data fields.
fn count_entry(
    entry: &Entry,
    source: Source<'_>,
    counts: &mut Counts,
) -> Result<Vec<String>, String> {
    with_record(entry, source, |item| {
        for key in &RECORD_FIELDS[..RECORD_FIELDS.len() - 1] {
            counts.value(field(item, key)?);
        }
        let Value::Object(data) = field(item, "data")? else {
            return Err("data must be an object".to_owned());
        };
        data.values().for_each(|value| counts.value(value));
        Ok(data.keys().cloned().collect())
    })
}

/// The second pass of the counts: the exact count of each text that may repeat (`texts.rs`).
fn recount(
    sections: &BTreeMap<String, Part>,
    evidence: &[Entry],
    plain: Source<'_>,
    counts: &mut Counts,
) -> Result<(), String> {
    counts.exact();
    for part in sections.values() {
        let Part::Section(Some(rows)) = part else {
            continue;
        };
        let source = Source {
            fields: &rows.shell,
            ..plain
        };
        for entry in rows
            .entries
            .iter()
            .filter(|entry| !matches!(entry, Entry::Row(..)))
        {
            count_entry(entry, source, counts)?;
        }
    }
    for entry in evidence {
        count_evidence(entry, plain.store, counts)?;
    }
    Ok(())
}

fn write_record(
    item: &Map<String, Value>,
    fields: &[String],
    texts: &Interned<'_>,
    out: &mut Vec<u8>,
) -> Result<(), String> {
    out.push(b'[');
    for key in &RECORD_FIELDS[..RECORD_FIELDS.len() - 1] {
        write_value(field(item, key)?, texts, out)?;
        out.push(b',');
    }
    let data = field(item, "data")?;
    out.push(b'[');
    for (index, key) in fields.iter().enumerate() {
        if index > 0 {
            out.push(b',');
        }
        match data.get(key) {
            Some(value) => write_value(value, texts, out)?,
            None => write_text(MISSING, out)?,
        }
    }
    out.extend_from_slice(b"]]");
    Ok(())
}

fn count_evidence(entry: &Entry, store: &Store, counts: &mut Counts) -> Result<(), String> {
    match entry {
        Entry::Stored(id) => {
            let item = store.evidence(id)?;
            [item.id.as_str(), &item.file, &item.excerpt]
                .iter()
                .for_each(|text| counts.text(text));
        }
        Entry::Shell(item) => {
            for key in EVIDENCE_FIELDS {
                counts.value(field(item, key)?);
            }
        }
        Entry::Row(..) => return Err(ROW_EVIDENCE.to_owned()),
    }
    Ok(())
}

fn write_typed_evidence(
    item: &Evidence,
    texts: &Interned<'_>,
    out: &mut Vec<u8>,
) -> Result<(), String> {
    out.push(b'[');
    texts.write(item.id.as_str(), out)?;
    out.push(b',');
    texts.write(&item.file, out)?;
    let numbers = format!(",{},{},{},", item.line, item.end_line, item.column);
    out.extend_from_slice(numbers.as_bytes());
    texts.write(&item.excerpt, out)?;
    out.push(b']');
    Ok(())
}

fn write_evidence(
    entry: &Entry,
    store: &Store,
    texts: &Interned<'_>,
    out: &mut Vec<u8>,
) -> Result<(), String> {
    match entry {
        Entry::Stored(id) => write_typed_evidence(store.evidence(id)?, texts, out),
        Entry::Shell(item) => {
            out.push(b'[');
            for (index, key) in EVIDENCE_FIELDS.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_value(field(item, key)?, texts, out)?;
            }
            out.push(b']');
            Ok(())
        }
        Entry::Row(..) => Err(ROW_EVIDENCE.to_owned()),
    }
}

/// One top-level value of the encoded model.
enum Part {
    Plain(Value),
    Section(Option<Rows>),
    Evidence(Vec<Entry>),
    Table,
    Coverage(Map<String, Value>, Option<Vec<Entry>>),
}

/// The rows of one record section; a stored record or a shell row is built only while it is written.
fn write_section(
    rows: &Rows,
    plain: Source<'_>,
    texts: &Interned<'_>,
    out: &mut Chunked<'_>,
) -> Result<(), String> {
    let source = Source {
        fields: &rows.shell,
        ..plain
    };
    write_list(&rows.entries, out, |entry, buf| {
        with_record(entry, source, |item| {
            write_record(item, &rows.fields, texts, buf)
        })
    })
}

/// The coverage object without its failures, and the failures as entries: a stored gap is
/// written from the store when the coverage is written, never held as JSON.
fn coverage(model: &mut HashMap<String, Top>) -> Result<Option<Part>, String> {
    let mut coverage = match model.remove("coverage") {
        None => return Ok(None),
        Some(Top::Plain(Value::Object(coverage))) => coverage,
        Some(_) => return Err("coverage must be an object".to_owned()),
    };
    let failures = match coverage.remove("failures") {
        Some(failures) => Some(failure_entries(failures)?),
        None => None,
    };
    Ok(Some(Part::Coverage(coverage, failures)))
}

/// The coverage object in canonical form: sorted keys, each failure written plain.
fn write_coverage(
    coverage: &Map<String, Value>,
    failures: Option<&[Entry]>,
    plain: Source<'_>,
    out: &mut Chunked<'_>,
) -> Result<(), String> {
    let mut keys: Vec<&str> = coverage.keys().map(String::as_str).collect();
    if failures.is_some() {
        keys.push("failures");
    }
    keys.sort_unstable();
    out.buf.push(b'{');
    for (index, key) in keys.into_iter().enumerate() {
        if index > 0 {
            out.buf.push(b',');
        }
        write_text(key, &mut out.buf)?;
        out.buf.push(b':');
        match (coverage.get(key), failures) {
            (Some(value), _) => write_value(value, &Plain, &mut out.buf)?,
            (None, Some(failures)) => write_list(failures, out, |entry, buf| {
                with_record(entry, plain, |item| {
                    write_value(&Value::Object(item.clone()), &Plain, buf)
                })
            })?,
            (None, None) => {}
        }
    }
    out.buf.push(b'}');
    Ok(())
}

/// The observation, ready to write: its parts and its string table.
pub(crate) struct Prepared<'a> {
    parts: BTreeMap<String, Part>,
    texts: Interned<'a>,
    plain: Source<'a>,
}

#[cfg(test)]
pub(crate) fn encode(
    model: HashMap<String, Top>,
    shell: &Shell,
    store: &Store,
) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    prepare(model, shell, store)?.write_to(&mut out)?;
    Ok(out)
}

/// The canonical form of the observation. `model` is the part of the shell, with stored ids.
pub(crate) fn prepare<'a>(
    mut model: HashMap<String, Top>,
    shell: &'a Shell,
    store: &'a Store,
) -> Result<Prepared<'a>, String> {
    let plain = Source {
        store,
        shell,
        fields: &[],
    };
    let coverage = coverage(&mut model)?;
    let mut parts: BTreeMap<String, Part> = BTreeMap::new();
    let mut data_fields = Map::new();
    let mut counts = Counts::new(shell);
    for name in CLASSIFIED_SECTIONS {
        let value = model
            .remove(name)
            .ok_or_else(|| format!("observation has no section {name}"))?;
        let section = match value {
            Top::Plain(Value::Null) => None,
            Top::Entries(entries) => {
                let source = Source {
                    fields: shell.fields(name),
                    ..plain
                };
                Some(rows(entries, source, &mut counts)?)
            }
            Top::Plain(_) => return Err(format!("{name} must be an array or null")),
        };
        let fields = section
            .as_ref()
            .map(|rows| rows.fields.clone())
            .unwrap_or_default();
        data_fields.insert(name.to_owned(), json!(fields));
        parts.insert(name.to_owned(), Part::Section(section));
    }
    let evidence = match model.remove("evidence") {
        None => Vec::new(),
        Some(Top::Entries(entries)) => entries,
        Some(Top::Plain(_)) => return Err("evidence must be an array".to_owned()),
    };
    for entry in &evidence {
        count_evidence(entry, store, &mut counts)?;
    }
    recount(&parts, &evidence, plain, &mut counts)?;
    let texts = counts.table();
    if let Some(coverage) = coverage {
        parts.insert("coverage".to_owned(), coverage);
    }
    for (key, value) in model {
        let Top::Plain(value) = value else {
            return Err(format!("{key} must not be an array"));
        };
        parts.insert(key, Part::Plain(value));
    }
    parts.insert("evidence".to_owned(), Part::Evidence(evidence));
    let encoding = json!({
        "kind": "architecture-ir-columnar-v1",
        "record_fields": RECORD_FIELDS,
        "evidence_fields": EVIDENCE_FIELDS,
        "section_data_fields": data_fields,
        "string_reference": "$<index>",
        "escaped_literal": "additional leading $",
    });
    parts.insert("encoding".to_owned(), Part::Plain(encoding));
    parts.insert("string_table".to_owned(), Part::Table);
    Ok(Prepared {
        parts,
        texts,
        plain,
    })
}

impl Prepared<'_> {
    /// Write the canonical bytes to `sink`; the same call gives the same bytes each time.
    pub(crate) fn write_to(&self, sink: &mut dyn Write) -> Result<(), String> {
        let (texts, plain) = (&self.texts, self.plain);
        let store = plain.store;
        let mut out = Chunked {
            buf: Vec::new(),
            sink,
        };
        out.buf.push(b'{');
        for (index, (key, part)) in self.parts.iter().enumerate() {
            if index > 0 {
                out.buf.push(b',');
            }
            write_text(key, &mut out.buf)?;
            out.buf.push(b':');
            match part {
                Part::Plain(value) => write_value(value, &Plain, &mut out.buf)?,
                Part::Coverage(coverage, failures) => {
                    write_coverage(coverage, failures.as_deref(), plain, &mut out)?;
                }
                Part::Section(None) => out.buf.extend_from_slice(b"null"),
                Part::Section(Some(rows)) => write_section(rows, plain, texts, &mut out)?,
                Part::Evidence(items) => write_list(items, &mut out, |entry, out| {
                    write_evidence(entry, store, texts, out)
                })?,
                Part::Table => {
                    write_list(&texts.table, &mut out, |item, out| write_text(item, out))?
                }
            }
            out.spill(1 << 20)?;
        }
        out.buf.extend_from_slice(b"}\n");
        out.spill(0)
    }
}

#[cfg(test)]
#[path = "canonical_tests.rs"]
mod tests;
