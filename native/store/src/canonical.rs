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

use archkeel_facts::envelope::Evidence;
use serde_json::{json, Map, Value};

use crate::pyjson::{write_text, write_value, Plain, Texts};
use crate::shell::Shell;
use crate::stored::Store;

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

/// A record or an evidence entry of the observation: held by the store, or sent by the shell as
/// an object or, in a record section, as a compact row (`shell.rs`).
enum Entry {
    Stored(String),
    Shell(Map<String, Value>),
    Row(Vec<Value>),
}

fn entries(value: Value, label: &str, rows: bool) -> Result<Vec<Entry>, String> {
    let Value::Array(items) = value else {
        return Err(format!("{label} must be an array"));
    };
    items
        .into_iter()
        .map(|item| match item {
            Value::String(id) => Ok(Entry::Stored(id)),
            Value::Object(object) => Ok(Entry::Shell(object)),
            Value::Array(row) if rows => Ok(Entry::Row(row)),
            _ => Err(format!("{label} holds an entry of an unknown form")),
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
        Entry::Row(row) => {
            let head = &RECORD_FIELDS[..RECORD_FIELDS.len() - 1];
            action(&source.shell.record(row, head, source.fields)?)
        }
    }
}

fn field<'a>(item: &'a Map<String, Value>, key: &str) -> Result<&'a Value, String> {
    item.get(key)
        .ok_or_else(|| format!("a record has no field {key}"))
}

/// Whether a text can enter the table at all; `profitable` needs 8 code points or `$$m`. Only
/// these texts are counted, so the counts hold no short id or word.
fn candidate(text: &str) -> bool {
    text == "$$m" || text.chars().nth(7).is_some()
}

/// The texts of a row value, without the keys of its objects.
fn count(value: &Value, counts: &mut HashMap<String, u64>) {
    match value {
        Value::String(text) => count_text(text, counts),
        Value::Array(items) => items.iter().for_each(|item| count(item, counts)),
        Value::Object(map) => map.values().for_each(|item| count(item, counts)),
        _ => {}
    }
}

fn count_text(text: &str, counts: &mut HashMap<String, u64>) {
    if !candidate(text) {
        return;
    }
    match counts.get_mut(text) {
        Some(count) => *count += 1,
        None => {
            counts.insert(text.to_owned(), 1);
        }
    }
}

/// `observation_profitable` of `ir/codec_strings.py`; a length counts code points.
fn profitable(text: &str, occurrences: u64) -> bool {
    let length = text.chars().count() as u64;
    text == "$$m"
        || (occurrences >= 2 && length >= 8 && (occurrences - 1) * length > occurrences * 8 + 100)
}

/// `observation_escaped`: the missing marker and the spellings of a reference.
fn escaped(text: &str) -> bool {
    let digits = |rest: &str| !rest.is_empty() && rest.bytes().all(|b| b.is_ascii_digit());
    text == "$m"
        || text == "$$m"
        || text.strip_prefix('$').is_some_and(digits)
        || text
            .strip_prefix("$$")
            .is_some_and(|rest| digits(rest.trim_start_matches('$')))
}

/// Writes a text as its table reference, or escaped when it looks like a reference.
struct Interned {
    references: HashMap<String, usize>,
}

impl Texts for Interned {
    fn write(&self, text: &str, out: &mut Vec<u8>) -> Result<(), String> {
        if let Some(index) = self.references.get(text) {
            out.extend_from_slice(format!("\"${index}\"").as_bytes());
            Ok(())
        } else if escaped(text) {
            write_text(&format!("${text}"), out)
        } else {
            write_text(text, out)
        }
    }
}

/// One record section: its sorted data fields, its entries and the data fields of its shell rows.
struct Rows {
    fields: Vec<String>,
    entries: Vec<Entry>,
    shell: Vec<String>,
}

/// The first pass over a section: its data fields, and the texts of its rows.
fn rows(
    entries: Vec<Entry>,
    source: Source<'_>,
    counts: &mut HashMap<String, u64>,
) -> Result<Rows, String> {
    let mut fields = BTreeSet::new();
    for entry in &entries {
        with_record(entry, source, |item| {
            for key in &RECORD_FIELDS[..RECORD_FIELDS.len() - 1] {
                count(field(item, key)?, counts);
            }
            let Value::Object(data) = field(item, "data")? else {
                return Err("data must be an object".to_owned());
            };
            fields.extend(data.keys().cloned());
            data.values().for_each(|value| count(value, counts));
            Ok(())
        })?;
    }
    Ok(Rows {
        fields: fields.into_iter().collect(),
        entries,
        shell: source.fields.to_vec(),
    })
}

fn write_record(
    item: &Map<String, Value>,
    fields: &[String],
    texts: &Interned,
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

fn count_evidence(
    entry: &Entry,
    store: &Store,
    counts: &mut HashMap<String, u64>,
) -> Result<(), String> {
    match entry {
        Entry::Stored(id) => {
            let item = store.evidence(id)?;
            [item.id.as_str(), &item.file, &item.excerpt]
                .iter()
                .for_each(|text| count_text(text, counts));
        }
        Entry::Shell(item) => {
            for key in EVIDENCE_FIELDS {
                count(field(item, key)?, counts);
            }
        }
        Entry::Row(_) => return Err(ROW_EVIDENCE.to_owned()),
    }
    Ok(())
}

fn write_typed_evidence(
    item: &Evidence,
    texts: &Interned,
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
    texts: &Interned,
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
        Entry::Row(_) => Err(ROW_EVIDENCE.to_owned()),
    }
}

fn write_list<T>(
    items: &[T],
    out: &mut Vec<u8>,
    mut each: impl FnMut(&T, &mut Vec<u8>) -> Result<(), String>,
) -> Result<(), String> {
    out.push(b'[');
    for (index, item) in items.iter().enumerate() {
        if index > 0 {
            out.push(b',');
        }
        each(item, out)?;
    }
    out.push(b']');
    Ok(())
}

/// One top-level value of the encoded model.
enum Part {
    Plain(Value),
    Section(Option<Rows>),
    Evidence(Vec<Entry>),
    Table(Vec<String>),
}

/// The coverage failures of the shell, with each stored gap written in full.
fn coverage(model: &mut Map<String, Value>, source: Source<'_>) -> Result<(), String> {
    let Some(Value::Object(coverage)) = model.get_mut("coverage") else {
        return Ok(());
    };
    let Some(failures) = coverage.remove("failures") else {
        return Ok(());
    };
    let resolved = entries(failures, "coverage.failures", false)?
        .iter()
        .map(|entry| with_record(entry, source, |item| Ok(Value::Object(item.clone()))))
        .collect::<Result<Vec<_>, String>>()?;
    coverage.insert("failures".to_owned(), Value::Array(resolved));
    Ok(())
}

/// The canonical bytes of the observation. `model` is the part of the shell, with stored ids.
pub(crate) fn encode(
    mut model: Map<String, Value>,
    shell: &Shell,
    store: &Store,
) -> Result<Vec<u8>, String> {
    let plain = Source {
        store,
        shell,
        fields: &[],
    };
    coverage(&mut model, plain)?;
    let mut parts: BTreeMap<String, Part> = BTreeMap::new();
    let mut data_fields = Map::new();
    let mut counts: HashMap<String, u64> = HashMap::new();
    for name in CLASSIFIED_SECTIONS {
        let value = model
            .remove(name)
            .ok_or_else(|| format!("observation has no section {name}"))?;
        let section = match value {
            Value::Null => None,
            value => {
                let source = Source {
                    fields: shell.fields(name),
                    ..plain
                };
                Some(rows(entries(value, name, true)?, source, &mut counts)?)
            }
        };
        let fields = section
            .as_ref()
            .map(|rows| rows.fields.clone())
            .unwrap_or_default();
        data_fields.insert(name.to_owned(), json!(fields));
        parts.insert(name.to_owned(), Part::Section(section));
    }
    let evidence = entries(
        model.remove("evidence").unwrap_or(json!([])),
        "evidence",
        false,
    )?;
    for entry in &evidence {
        count_evidence(entry, store, &mut counts)?;
    }
    let mut table: Vec<String> = counts
        .into_iter()
        .filter(|(text, occurrences)| profitable(text, *occurrences))
        .map(|(text, _)| text)
        .collect();
    table.sort();
    let texts = Interned {
        references: table
            .iter()
            .enumerate()
            .map(|(i, text)| (text.clone(), i))
            .collect(),
    };
    for (key, value) in model {
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
    parts.insert("string_table".to_owned(), Part::Table(table));
    write(&parts, &texts, plain)
}

fn write(
    parts: &BTreeMap<String, Part>,
    texts: &Interned,
    plain: Source<'_>,
) -> Result<Vec<u8>, String> {
    let store = plain.store;
    let mut out = Vec::new();
    out.push(b'{');
    for (index, (key, part)) in parts.iter().enumerate() {
        if index > 0 {
            out.push(b',');
        }
        write_text(key, &mut out)?;
        out.push(b':');
        match part {
            Part::Plain(value) => write_value(value, &Plain, &mut out)?,
            Part::Section(None) => out.extend_from_slice(b"null"),
            Part::Section(Some(rows)) => write_list(&rows.entries, &mut out, |entry, out| {
                let source = Source {
                    fields: &rows.shell,
                    ..plain
                };
                with_record(entry, source, |item| {
                    write_record(item, &rows.fields, texts, out)
                })
            })?,
            Part::Evidence(items) => write_list(items, &mut out, |entry, out| {
                write_evidence(entry, store, texts, out)
            })?,
            Part::Table(items) => write_list(items, &mut out, |item, out| write_text(item, out))?,
        }
    }
    out.extend_from_slice(b"}\n");
    Ok(out)
}

#[cfg(test)]
#[path = "canonical_tests.rs"]
mod tests;
