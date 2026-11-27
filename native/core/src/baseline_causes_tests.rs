// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-1275: a rule can have several causes. A file of schema 1.5.0 names them all; a file of 1.4.0 names the first
// one, so the compare leaves the others out and the same source stays current.

use std::collections::BTreeMap;

use archkeel_contract::policy::parse_baseline;
use serde_json::{json, Value};

use super::{compare, Observed};
use crate::gap_key::{Gaps, Key};

fn file(version: &str, keys: &[(&str, &str)]) -> archkeel_contract::policy::ValidationBaseline {
    let unknowns: Vec<Value> = keys
        .iter()
        .map(|(kind, reason)| json!({"kind": kind, "subject": "RULE", "reason": reason}))
        .collect();
    let document = json!({
        "schema_version": version, "violations": [], "budgets": {}, "unknowns": unknowns,
    });
    parse_baseline(document.to_string().as_bytes()).expect("a checked baseline")
}

fn key(kind: &str, reason: &str) -> Key {
    Key {
        kind: kind.to_owned(),
        subject: "RULE".to_owned(),
        reason: reason.to_owned(),
    }
}

/// A run with the first cause `first` and the causes beyond it `beyond` of the rule `RULE`.
fn run(first: &[(&str, &str)], beyond: &[(&str, &str)]) -> Observed {
    let mut gaps = Gaps::default();
    for (kind, reason) in first {
        gaps.keys.insert(key(kind, reason), 1);
        gaps.by_rule
            .entry("RULE".to_owned())
            .or_default()
            .push(key(kind, reason));
    }
    for (kind, reason) in beyond {
        gaps.keys.insert(key(kind, reason), 1);
        gaps.beyond = BTreeMap::from([(key(kind, reason), 1)]);
    }
    Observed {
        unknown_status: true,
        gaps,
        ..Observed::default()
    }
}

const FIRST: (&str, &str) = ("interface_gap", "unread import binding");
const NEXT: (&str, &str) = ("pair_gap", "a -> b");

#[test]
fn a_file_of_1_4_0_leaves_the_causes_beyond_the_first_out() {
    let same_source = run(&[FIRST], &[NEXT]);
    let found = compare(&file("1.4.0", &[FIRST]), &same_source);
    assert_eq!((found.new.len(), found.gone.len()), (0, 0), "{found:?}");
    assert_eq!(found.accepted_rules, vec!["RULE".to_owned()]);
}

#[test]
fn a_file_of_1_5_0_compares_every_cause() {
    let same_source = run(&[FIRST], &[NEXT]);
    let missing = compare(&file("1.5.0", &[FIRST]), &same_source);
    assert_eq!(
        (missing.new.len(), missing.gone.len()),
        (1, 0),
        "{missing:?}"
    );
    assert_eq!(missing.new[0].kind, "pair_gap");
    let all = compare(&file("1.5.0", &[FIRST, NEXT]), &same_source);
    assert_eq!((all.new.len(), all.gone.len()), (0, 0), "{all:?}");
}

#[test]
fn the_first_cause_that_a_rule_stops_showing_is_gone_and_the_next_one_is_not_new() {
    // The first cause is resolved: the row now shows the cause that the file already holds.
    let resolved = run(&[NEXT], &[]);
    let found = compare(&file("1.5.0", &[FIRST, NEXT]), &resolved);
    assert_eq!((found.new.len(), found.gone.len()), (0, 1), "{found:?}");
    assert_eq!(found.gone[0].kind, "interface_gap");
}

#[test]
fn a_first_cause_of_a_file_of_1_4_0_is_still_compared_exactly() {
    let found = compare(&file("1.4.0", &[FIRST]), &run(&[NEXT], &[]));
    assert_eq!((found.new.len(), found.gone.len()), (1, 1), "{found:?}");
}

#[test]
fn a_rule_is_accepted_on_the_counts_that_a_file_of_1_4_0_is_compared_with() {
    // The same key comes from the first cause and from a later one: the run counts it twice, the file once.
    let mut twice = run(&[FIRST], &[]);
    twice.gaps.keys.insert(key(FIRST.0, FIRST.1), 2);
    twice.gaps.beyond.insert(key(FIRST.0, FIRST.1), 1);
    let found = compare(&file("1.4.0", &[FIRST]), &twice);
    assert_eq!((found.new.len(), found.gone.len()), (0, 0), "{found:?}");
    assert_eq!(found.accepted_rules, vec!["RULE".to_owned()]);
}

#[test]
fn a_collector_gap_is_matched_by_its_exact_key_so_a_swap_or_a_reword_is_new_and_gone() {
    // The text of a gap is its identity: a gap replaced by another of the same kind and subject, with the same
    // count, is one new and one gone entry, and so is a reworded text. No pairing hides a new finding.
    let accepted = file(
        "1.5.0",
        &[("source_resolution_gap", "dynamic_import: import_module")],
    );
    let swapped = run(&[("source_resolution_gap", "dynamic_import: reload")], &[]);
    let found = compare(&accepted, &swapped);
    assert_eq!((found.new.len(), found.gone.len()), (1, 1), "{found:?}");
    assert_eq!(found.new[0].reason, "dynamic_import: reload");
}
