// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compressed reply of protocols 8.0.0 and 9.0.0: zlib level 1 over the plain JSON facts.

use serde_json::{json, Map, Value};

#[cfg(test)]
use archkeel_facts::reply::{evidence_value, file_value, source_digest, target_value};
use archkeel_facts::reply::{Evidence, FileFact, Input, Provenance, Target};

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

#[cfg(test)]
fn facts_value(facts: &Facts) -> Value {
    let provenance = &facts.provenance;
    json!({
        "adapter": {
            "name": provenance.profile,
            "version": provenance.adapter_version,
            "code_digest": provenance.code_digest,
        },
        "candidate_evidence": [],
        "capabilities": {
            "sections": facts.sections.iter().map(ReplySection::name).collect::<Vec<_>>(),
            "resolution_features": facts.features,
            "constructs": facts.constructs.iter()
                .map(|(name, status)| json!({"name": name, "status": status}))
                .collect::<Vec<_>>(),
        },
        "coverage": {
            "selected_files": facts.selected_files,
            "files_read": facts.files_read,
            "files_parsed": facts.files.len(),
            "full_scope": facts.gaps.is_empty(),
            "gaps": facts.gaps,
        },
        "evidence": facts.evidence.iter().map(evidence_value).collect::<Vec<_>>(),
        "files": facts.files.iter().map(file_value).collect::<Vec<_>>(),
        "imports": facts.imports.iter().map(target_value).collect::<Vec<_>>(),
        "inputs": facts.inputs.iter().map(|input| json!({
            "path": input.path, "digest": input.digest, "role": input.role.as_str(),
        })).collect::<Vec<_>>(),
        "profile": provenance.profile,
        "provider_bindings": [],
        "runtime": {
            "name": provenance.runtime_name,
            "version": provenance.runtime_version,
            "required": provenance.runtime_required,
            "requirement_state": "declared",
        },
        "sections": facts.sections.iter().map(|section| match section {
            ReplySection::Typed(section) => json!(section),
            ReplySection::Records(name, records) => json!({
                "name": name, "records": records.iter().map(record_value).collect::<Vec<_>>(),
            }),
        }).collect::<Vec<_>>(),
        "source": {
            "git_head": facts.git_head,
            "dirty": facts.dirty,
            "source_digest": source_digest(&facts.inputs),
            "scope": facts.scope,
        },
        "state": {"classes": [], "functions": []},
        "type_shapes": [],
        "uncertain_reexports": [],
    })
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
