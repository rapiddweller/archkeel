// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proven class records used by placement (AD-728).

use archkeel_facts::envelope::Facts;
use archkeel_facts::vocab::ClassKind;
use archkeel_facts::{Section, SymbolFact};

/// A proven class outside the permitted modules.
#[derive(Clone, Debug)]
pub struct Class {
    /// The qualified name of the class.
    pub name: String,
    /// Its defining module.
    pub module: String,
    /// The kind proven by the symbol fact.
    pub kind: ClassKind,
    /// The symbol record.
    pub fact_id: String,
    /// The source evidence.
    pub evidence: Vec<String>,
}

pub(crate) fn classes(facts: &Facts) -> Vec<Class> {
    facts
        .sections
        .iter()
        .flat_map(|section| match section {
            Section::Symbols(records) => records.as_slice(),
            _ => &[],
        })
        .filter_map(|record| {
            let SymbolFact::Class(data) = &record.data else {
                return None;
            };
            if !data.source_binding_unique || !data.class_header_static {
                return None;
            }
            Some(Class {
                name: data.qualified_name.clone(),
                module: data.module.as_str().to_owned(),
                kind: data.class_kind?,
                fact_id: record.id.as_str().to_owned(),
                evidence: record
                    .evidence_ids
                    .iter()
                    .map(|id| id.as_str().to_owned())
                    .collect(),
            })
        })
        .collect()
}
