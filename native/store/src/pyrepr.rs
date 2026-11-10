// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python `repr` text of a source record and of an evidence entry (AD-346).
//!
//! The receipt digest of a dependency proof (AD-237, `ir/dependency_binding.py`) is the stable id
//! of the `repr` of the bound records and evidence. The store holds those records, so it writes
//! the same text. A record is the Python `Record` that `facts_codec.parse_record` builds: its data
//! keys are sorted, a list is a tuple and an object is a `RecordData`.

use std::sync::OnceLock;

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::printable::HIDDEN;
use crate::pyjson::scalar;

/// The fields of a record in the order of the Python dataclass.
const RECORD_FIELDS: [&str; 10] = [
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
];

/// The ranges of `printable::HIDDEN`, parsed once. A malformed range is skipped; the test of the
/// table checks that every range parses.
fn ranges() -> &'static [(u32, u32)] {
    static RANGES: OnceLock<Vec<(u32, u32)>> = OnceLock::new();
    RANGES.get_or_init(|| {
        HIDDEN
            .split_whitespace()
            .filter_map(|range| {
                let (low, high) = range.split_once('-')?;
                Some((
                    u32::from_str_radix(low, 16).ok()?,
                    u32::from_str_radix(high, 16).ok()?,
                ))
            })
            .collect()
    })
}

fn hidden(point: u32) -> bool {
    ranges()
        .binary_search_by(|&(low, high)| {
            if high < point {
                std::cmp::Ordering::Less
            } else if low > point {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// `repr(text)` of CPython: the quote, the escapes and the printable test of `unicode_repr`.
pub(crate) fn string(text: &str, out: &mut String) {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    out.push(quote);
    for c in text.chars() {
        let point = u32::from(c);
        match c {
            _ if c == quote || c == '\\' => {
                out.push('\\');
                out.push(c);
            }
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            _ if point < 0x20 || point == 0x7F => out.push_str(&format!("\\x{point:02x}")),
            _ if point < 0x80 || !hidden(point) => out.push(c),
            _ if point <= 0xFF => out.push_str(&format!("\\x{point:02x}")),
            _ if point <= 0xFFFF => out.push_str(&format!("\\u{point:04x}")),
            _ => out.push_str(&format!("\\U{point:08x}")),
        }
    }
    out.push(quote);
}

/// `repr` of a tuple of already written items.
fn tuple(items: &[String], out: &mut String) {
    out.push('(');
    out.push_str(&items.join(", "));
    if items.len() == 1 {
        out.push(',');
    }
    out.push(')');
}

/// `repr` of a frozen JSON value: `None`, `True`, a number, a text, a tuple or a `RecordData`.
pub(crate) fn value(item: &Value, out: &mut String) -> Result<(), String> {
    match item {
        Value::String(text) => string(text, out),
        Value::Array(items) => {
            let parts = items.iter().map(text_of).collect::<Result<Vec<_>, _>>()?;
            tuple(&parts, out);
        }
        Value::Object(map) => record_data(map, out)?,
        atom => out.push_str(&scalar(atom, ["None", "True", "False"])?),
    }
    Ok(())
}

fn text_of(item: &Value) -> Result<String, String> {
    let mut out = String::new();
    value(item, &mut out)?;
    Ok(out)
}

/// `RecordData(entries=((key, value), ...))` with the keys sorted, as `_freeze_object` sorts them.
fn record_data(map: &Map<String, Value>, out: &mut String) -> Result<(), String> {
    let mut keys: Vec<&String> = map.keys().collect();
    keys.sort();
    let mut entries = Vec::with_capacity(keys.len());
    for key in keys {
        let mut entry = String::from("(");
        string(key, &mut entry);
        entry.push_str(", ");
        value(&map[key.as_str()], &mut entry)?;
        entry.push(')');
        entries.push(entry);
    }
    out.push_str("RecordData(entries=");
    tuple(&entries, out);
    out.push(')');
    Ok(())
}

/// `repr` of a Python `Record` built from the wire form of a record.
pub(crate) fn record(map: &Map<String, Value>) -> Result<String, String> {
    let mut out = String::from("Record(");
    for (index, field) in RECORD_FIELDS.iter().enumerate() {
        if index > 0 {
            out.push_str(", ");
        }
        out.push_str(field);
        out.push('=');
        let item = map
            .get(*field)
            .ok_or_else(|| format!("a record has no {field}"))?;
        if *field == "evidence_class" {
            let class = item.as_str().ok_or("evidence_class is not a text")?;
            out.push_str(&format!("<EvidenceClass.{class}: "));
            string(class, &mut out);
            out.push('>');
        } else {
            value(item, &mut out)?;
        }
    }
    out.push_str(", data=");
    match map.get("data") {
        Some(Value::Object(data)) => record_data(data, &mut out)?,
        _ => return Err("a record has no data object".to_owned()),
    }
    out.push(')');
    Ok(out)
}

/// `repr` of a Python `Evidence`.
pub(crate) fn evidence(entry: &archkeel_facts::envelope::Evidence) -> String {
    let mut out = String::from("Evidence(id=");
    string(entry.id.as_str(), &mut out);
    out.push_str(", file=");
    string(&entry.file, &mut out);
    out.push_str(&format!(
        ", line={}, end_line={}, column={}, excerpt=",
        entry.line, entry.end_line, entry.column
    ));
    string(&entry.excerpt, &mut out);
    out.push(')');
    out
}

/// `stable_id(prefix, part)` of `ir/facts.py` for one part.
pub(crate) fn stable_id(prefix: &str, part: &str) -> String {
    let digest = Sha256::digest(part.as_bytes());
    let hex: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
    format!("{prefix}-{}", &hex[..16])
}

/// The id of `repr((records, evidence))`, each a tuple of written items in the caller's order.
pub(crate) fn binding_id(records: &[String], evidence: &[String]) -> String {
    let mut first = String::new();
    tuple(records, &mut first);
    let mut second = String::new();
    tuple(evidence, &mut second);
    stable_id("DEPENDENCY-PROOF", &format!("({first}, {second})"))
}

#[cfg(test)]
#[path = "pyrepr_tests.rs"]
mod tests;
