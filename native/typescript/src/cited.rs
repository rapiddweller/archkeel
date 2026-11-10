// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence that the records of PR 4.3a-3 cite (`collect._cite`).

use std::borrow::Borrow;
use std::cmp::Ordering;
use std::collections::BTreeSet;

use archkeel_facts::envelope::Evidence;

use crate::source::Span;

/// A piece of evidence that is ordered by its id, so the set holds the id once and not twice.
struct ById(Evidence);

impl PartialEq for ById {
    fn eq(&self, other: &Self) -> bool {
        self.0.id == other.0.id
    }
}

impl Eq for ById {}

impl PartialOrd for ById {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for ById {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0.id.cmp(&other.0.id)
    }
}

impl Borrow<str> for ById {
    fn borrow(&self) -> &str {
        self.0.id.as_str()
    }
}

/// The evidence of the whole collection, by id, and the ids that the new records cite. The last
/// citation of a location decides its excerpt, as in Python (`record_evidence` overwrites), so the
/// evidence of the reply comes first and the new records cite after it, in the order of Python.
#[derive(Default)]
pub struct Cited {
    all: BTreeSet<ById>,
    /// The ids that the records cite, kept only when asked: the dump needs them, the reply not.
    touched: Option<BTreeSet<String>>,
}

impl Cited {
    /// Take the evidence of the collection. It is moved, not copied: on the wire path the
    /// evidence is the largest list of the reply.
    pub fn owning(evidence: Vec<Evidence>, track: bool) -> Self {
        let all = evidence.into_iter().map(ById).collect();
        Self {
            all,
            touched: track.then(BTreeSet::new),
        }
    }

    /// All the evidence sorted by id, and the ids that the new records cite.
    pub fn finish(self) -> (Vec<Evidence>, Vec<String>) {
        (
            self.all.into_iter().map(|item| item.0).collect(),
            self.touched.into_iter().flatten().collect(),
        )
    }

    /// The excerpt that the evidence of an id has now (`self.evidence[id]["excerpt"]`).
    pub fn excerpt(&self, id: &str) -> String {
        self.all
            .get(id)
            .map_or_else(String::new, |item| item.0.excerpt.clone())
    }

    /// `collect._cite`.
    pub fn cite(&mut self, rel: &str, span: &Span) -> String {
        let evidence = Evidence::at(rel, span.line, span.end_line, span.column, &span.excerpt);
        let id = evidence.id.as_str().to_owned();
        if let Some(touched) = &mut self.touched {
            touched.insert(id.clone());
        }
        self.all.replace(ById(evidence));
        id
    }
}
