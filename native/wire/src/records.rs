// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records that every native collector writes the same way: an UNKNOWN gap and the evidence
//! of a source line (`collect._gap` and `source_records.file_evidence` of the Python collectors).

use serde_json::{Map, Value};

use crate::identity::{evidence_id, stable_id, Part};
use crate::reply::{Evidence, Record};

/// The kind of an UNKNOWN record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GapKind {
    Collection,
    Resolution,
}

/// One UNKNOWN record; the same reason, evidence and module give the same record.
pub fn gap_record(reason: &str, evidence: Option<&str>, module: &str, kind: GapKind) -> Record {
    let mut parts = vec![Part::Text(reason)];
    parts.extend(evidence.map(Part::Text));
    parts.push(Part::Text(module));
    let id = stable_id("UNKNOWN", &parts);
    let mut data = Map::new();
    data.insert("reason".to_owned(), Value::from(reason));
    data.insert("module".to_owned(), Value::from(module));
    let kind = match kind {
        GapKind::Collection => "collection_gap",
        GapKind::Resolution => {
            data.insert("resolution_dimension".to_owned(), Value::from("imports"));
            "source_resolution_gap"
        }
    };
    Record {
        id,
        evidence_class: "UNKNOWN",
        area: "source",
        kind,
        title: reason.to_owned(),
        subjects: [module]
            .into_iter()
            .filter(|module| !module.is_empty())
            .map(str::to_owned)
            .collect(),
        evidence_ids: evidence.into_iter().map(str::to_owned).collect(),
        data,
    }
}

/// The evidence of one source location, with the text of its first line.
pub fn evidence_at(
    rel_path: &str,
    line: i64,
    end_line: i64,
    column: i64,
    excerpt: &str,
) -> Evidence {
    Evidence {
        id: evidence_id(rel_path, line, end_line, column),
        file: rel_path.to_owned(),
        line,
        end_line,
        column,
        excerpt: excerpt.to_owned(),
    }
}

#[cfg(test)]
#[path = "records_tests.rs"]
mod tests;
