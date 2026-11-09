// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence that the records of PR 4.3a-3 cite (`collect._cite`).

use std::collections::{BTreeMap, BTreeSet};

use archkeel_wire::identity::evidence_id;
use archkeel_wire::reply::Evidence;

use crate::source::Span;

/// The evidence of the whole collection, by id, and the ids that the new records cite. The last
/// citation of a location decides its excerpt, as in Python (`record_evidence` overwrites), so the
/// evidence of the reply comes first and the new records cite after it, in the order of Python.
#[derive(Default)]
pub struct Cited {
    all: BTreeMap<String, Evidence>,
    touched: BTreeSet<String>,
}

impl Cited {
    /// Take the evidence of the collection. It is moved, not copied: on the wire path the
    /// evidence is the largest list of the reply.
    pub fn owning(evidence: Vec<Evidence>) -> Self {
        let all = evidence
            .into_iter()
            .map(|item| (item.id.clone(), item))
            .collect();
        Self {
            all,
            touched: BTreeSet::new(),
        }
    }

    /// All the evidence sorted by id, and the ids that the new records cite.
    pub fn finish(self) -> (Vec<Evidence>, Vec<String>) {
        (
            self.all.into_values().collect(),
            self.touched.into_iter().collect(),
        )
    }

    /// `collect._cite`.
    pub fn cite(&mut self, rel: &str, span: &Span) -> String {
        let id = evidence_id(rel, span.line, span.end_line, span.column);
        self.touched.insert(id.clone());
        let evidence = Evidence {
            id: id.clone(),
            file: rel.to_owned(),
            line: span.line,
            end_line: span.end_line,
            column: span.column,
            excerpt: span.excerpt.clone(),
        };
        self.all.insert(id.clone(), evidence);
        id
    }
}
