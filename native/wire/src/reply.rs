// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compressed reply of protocols 8.0.0 and 9.0.0: zlib level 1 over the plain JSON facts.

use serde_json::{json, Map, Value};

use archkeel_facts::envelope::Target;
use archkeel_facts::envelope::{Evidence, FileFact, Input, Provenance};

/// One source record. `subjects` and `evidence_ids` must be sorted, as `classified` sorts them.
/// `fact_ids` keep the order of the Python collector, which sets them after `classified` and does
/// not sort them: a later port must not sort them either. The five source sections of the inner-UML capability (`imports`, `symbols`,
/// `calls`, `references`, `bindings`) and `constructs` all carry this one shape: a section is a
/// name and a list of records, so a later phase fills a section without a change to this crate.
#[derive(Clone, Debug, PartialEq)]
pub struct Record {
    pub id: String,
    pub evidence_class: &'static str,
    pub area: &'static str,
    pub kind: &'static str,
    pub title: String,
    pub subjects: Vec<String>,
    pub evidence_ids: Vec<String>,
    pub fact_ids: Vec<String>,
    pub data: Map<String, Value>,
}

/// One section of the reply. A typed section holds the records of archkeel-facts (AD-345), and its
/// wire is written by those types. The imports section is typed; the other sections follow.
#[derive(Clone, Debug, PartialEq)]
pub enum ReplySection {
    Typed(archkeel_facts::Section),
    Records(&'static str, Vec<Record>),
}

impl ReplySection {
    pub fn name(&self) -> &'static str {
        match self {
            ReplySection::Typed(section) => section.name(),
            ReplySection::Records(name, _) => name,
        }
    }

    /// The count of records.
    pub fn len(&self) -> usize {
        match self {
            ReplySection::Typed(section) => section.len(),
            ReplySection::Records(_, records) => records.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// The facts of one collection, in the order the reply writes them.
#[derive(Clone, Debug, PartialEq)]
pub struct Facts {
    pub provenance: Provenance,
    pub git_head: String,
    pub dirty: Value,
    pub scope: Vec<String>,
    pub sections: Vec<ReplySection>,
    pub features: Vec<&'static str>,
    /// The construct capabilities: `(name, status)`, for example `("string_literal_compare", "partial")`.
    pub constructs: Vec<(&'static str, &'static str)>,
    pub inputs: Vec<Input>,
    pub files: Vec<FileFact>,
    /// The resolved target of each import record, in the order of the walk.
    pub imports: Vec<Target>,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    /// Coverage gaps. The collection is complete only when there is none.
    pub gaps: Vec<archkeel_facts::Record<archkeel_facts::GapFact>>,
    pub evidence: Vec<Evidence>,
}

pub fn target_value(target: &Target) -> Value {
    // A derived enum of texts always serializes; `Null` is not reachable.
    serde_json::to_value(target).unwrap_or(Value::Null)
}

pub fn record_value(record: &Record) -> Value {
    json!({
        "id": record.id,
        "evidence_class": record.evidence_class,
        "area": record.area,
        "kind": record.kind,
        "title": record.title,
        "subjects": record.subjects,
        "evidence_ids": record.evidence_ids,
        "rule_ids": [],
        "fact_ids": record.fact_ids,
        "provenance": [],
        "data": record.data,
    })
}

#[cfg(test)]
#[path = "reply_tests.rs"]
mod tests;
