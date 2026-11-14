// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The causes of the UNKNOWN rules (AD-498): the rules that one hold of `explain.holds` keeps open,
//! grouped, largest first. The page copies the hold of each rule; it decides nothing.

use std::collections::BTreeMap;

use super::frame::Frame;
use super::markup::count;

/// The rules that one cause holds.
pub(super) struct Cause<'a> {
    pub(super) kind: &'a str,
    /// The reason of the core, as written, for a cause that has no typed form.
    pub(super) reason: &'a str,
    pub(super) rules: Vec<&'a str>,
    /// The number of gaps that hold each rule of the cause.
    pub(super) total: usize,
    pub(super) unnamed: usize,
}

/// The causes of the UNKNOWN rules of a frame, the cause with most rules first.
pub(super) fn grouped(frame: &Frame) -> Vec<Cause<'_>> {
    let mut causes: BTreeMap<(&str, &str, usize), Cause<'_>> = BTreeMap::new();
    for (rule, _) in frame.rules.iter().filter(|(_, row)| row.1 == "UNKNOWN") {
        let held = frame.explain.holds.rules.get(rule);
        let reason = frame.explained.get(rule).map_or("", String::as_str);
        let kind = held
            .map(|h| h.kind.as_str())
            .filter(|kind| !kind.is_empty())
            .unwrap_or("other");
        let total = held.map_or(0, |h| h.total);
        // A cause with no typed form is told apart by the text of the core.
        let text = if kind == "other" { reason } else { "" };
        causes
            .entry((kind, text, total))
            .or_insert_with(|| Cause {
                kind,
                reason,
                rules: Vec::new(),
                total,
                unnamed: held.map_or(0, |h| h.unnamed_imports),
            })
            .rules
            .push(rule);
    }
    let mut list: Vec<Cause<'_>> = causes.into_values().collect();
    list.sort_by(|a, b| b.rules.len().cmp(&a.rules.len()).then(a.kind.cmp(b.kind)));
    list
}

/// What the cause is, in one phrase.
pub(super) fn title(cause: &Cause<'_>) -> String {
    match cause.kind {
        "coverage_gaps" => format!("{} in the scan", count(cause.total, "coverage gap")),
        "pair_gaps" => format!("{} between two modules", count(cause.total, "gap")),
        "allowed_pair_gaps" => format!(
            "{} between two modules that the contract allows",
            count(cause.total, "gap")
        ),
        "unknown_imports" => format!(
            "{} that no gap names",
            count(cause.unnamed, "unresolved import")
        ),
        "no_source_files" => "the collector selected no source file".to_owned(),
        _ => cause.reason.to_owned(),
    }
}
