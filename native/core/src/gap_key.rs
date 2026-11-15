// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The stable key of each UNKNOWN entry of a run (AD-546).
//!
//! A baseline accepts an UNKNOWN by WHAT it is: kind, subject and reason. This module builds the
//! key from the typed values of the run, never from a display text. Four things move with an
//! unrelated edit and stay out of every key: a line, a pointer into the contract, an evidence id
//! and a sum of other entries. Two equal keys are two sites of the same kind in one subject, so
//! the key set is a multiset: each key has a count.
//!
//! Sources of keys:
//! - each rule that has no decision: the typed `Reason` of the rule (`Reason::stable`);
//! - each gap of the collector: its kind, its module or file, and its reason code.
//!
//! A part that no key can name is not acceptable (a refused contract, a refused reply, a section
//! or the report that no slice ports). It is in `unacceptable`, and a baseline never covers it.

use std::collections::BTreeMap;

use archkeel_facts::{FactData, GapFact, Record};
use archkeel_report::{RuleReasons, Ruling};
use archkeel_store::Ingested;

/// What an UNKNOWN is: its kind, its subject and its reason.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Key {
    pub(crate) kind: String,
    pub(crate) subject: String,
    pub(crate) reason: String,
}

/// The UNKNOWN entries of a run with their counts, and the parts that no baseline can accept.
#[derive(Debug, Default)]
pub(crate) struct Gaps {
    pub(crate) keys: BTreeMap<Key, u64>,
    pub(crate) unacceptable: Vec<String>,
}

impl Gaps {
    fn add(&mut self, key: Key, count: u64) {
        let total = self.keys.entry(key).or_default();
        *total = total.saturating_add(count);
    }
}

/// The keys of a ruling and of the gaps of the collector reply.
pub(crate) fn of_run(ruling: &Ruling, reply: Option<&Ingested>) -> Gaps {
    let mut gaps = Gaps::default();
    if let RuleReasons::All(text) = ruling.unsupported() {
        gaps.unacceptable.push(format!("the whole contract: {text}"));
    }
    for (rule, reason) in ruling.causes() {
        for entry in archkeel_model::stable(reason) {
            let key = Key {
                kind: entry.kind,
                subject: entry.subject.unwrap_or_else(|| rule.clone()),
                reason: entry.reason,
            };
            gaps.add(key, entry.count);
        }
    }
    let records = reply.into_iter().flat_map(|reply| &reply.reply().facts.coverage.gaps);
    for record in records {
        gaps.add(collector(record), 1);
    }
    gaps
}

/// The key of one gap of the collector. The module names the subject, else the file, else the
/// first subject of the record. The reason is the code that the collector wrote, else the kind.
/// The line and the message of the parser are not in the key: an edit above the site moves them.
fn collector(record: &Record<GapFact>) -> Key {
    let data = record.data.data();
    let kind = record.data.wire_kind().to_owned();
    let subject = data
        .module
        .as_ref()
        .map(|module| module.as_str().to_owned())
        .filter(|name| !name.is_empty())
        .or_else(|| data.file.clone().filter(|file| !file.is_empty()))
        .or_else(|| record.subjects.first().map(|name| strip_line(name).to_owned()))
        .unwrap_or_default();
    let reason = data
        .reason
        .as_deref()
        .filter(|text| !text.is_empty())
        .map_or_else(|| kind.clone(), |text| strip_line(text).to_owned());
    Key {
        kind,
        subject,
        reason,
    }
}

/// A reason that ends in `at line <n>`, or a subject that ends in `:<n>`, holds a position. The
/// collectors that write one are the TypeScript parser gap and the Dart file gap; the key keeps
/// the text before the position.
fn strip_line(text: &str) -> &str {
    let digits = text.len() - text.trim_end_matches(|c: char| c.is_ascii_digit()).len();
    if digits == 0 {
        return text;
    }
    let head = &text[..text.len() - digits];
    head.strip_suffix(" at line ")
        .or_else(|| head.strip_suffix(':'))
        .unwrap_or(text)
}

#[cfg(test)]
#[path = "gap_key_tests.rs"]
mod tests;
