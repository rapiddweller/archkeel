// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-1275: a collector gap whose text changed, and whose kind, subject and count did not, is no drift. Each
// test names the difference that it plants. Without `reworded` in `unknowns`, the first two fail.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_contract::policy::parse_baseline;
use serde_json::{json, Value};

use super::{compare, Observed};
use crate::gap_key::{Gaps, Key};

fn file(unknowns: Value) -> archkeel_contract::policy::ValidationBaseline {
    let document = json!({
        "schema_version": "1.4.0", "violations": [], "budgets": {}, "unknowns": unknowns,
    });
    parse_baseline(document.to_string().as_bytes()).expect("a checked baseline")
}

fn entry(kind: &str, subject: &str, reason: &str, count: u64) -> Value {
    let mut value = json!({"kind": kind, "subject": subject, "reason": reason});
    if count > 1 {
        value["count"] = json!(count);
    }
    value
}

/// A run of the keys `(kind, subject, reason, count)`; `reworded` says which keys are collector text.
fn run(keys: &[(&str, &str, &str, u64)], reworded: bool) -> Observed {
    let key = |(kind, subject, reason, _): &(&str, &str, &str, u64)| Key {
        kind: (*kind).to_owned(),
        subject: (*subject).to_owned(),
        reason: (*reason).to_owned(),
    };
    let counts: BTreeMap<Key, u64> = keys.iter().map(|item| (key(item), item.3)).collect();
    let marked: BTreeSet<Key> = if reworded {
        counts.keys().cloned().collect()
    } else {
        BTreeSet::new()
    };
    Observed {
        unknown_status: true,
        gaps: Gaps {
            keys: counts,
            reworded: marked,
            ..Gaps::default()
        },
        ..Observed::default()
    }
}

const GAP: &str = "collection_gap";

#[test]
fn a_reworded_collector_gap_with_the_same_kind_subject_and_count_is_current() {
    let accepted = file(json!([entry(
        GAP,
        "pkg.a",
        "A method call may reach the method f",
        2
    )]));
    let now = run(
        &[(
            GAP,
            "pkg.a",
            "A call may reach the method f of a type in its file",
            2,
        )],
        true,
    );
    let found = compare(&accepted, &now);
    assert_eq!((found.new.len(), found.gone.len()), (0, 0), "{found:?}");
    assert_eq!(found.state.exit_code(), 2);
    assert_eq!(found.accepted_unknowns, 2);
}

#[test]
fn a_reworded_gap_that_the_run_has_more_of_is_new_for_the_surplus_only() {
    let accepted = file(json!([entry(GAP, "pkg.a", "old text", 2)]));
    let found = compare(&accepted, &run(&[(GAP, "pkg.a", "new text", 3)], true));
    assert_eq!((found.new.len(), found.gone.len()), (1, 0));
    assert_eq!((found.new[0].run, found.new[0].file), (3, 2));
    let fewer = compare(&accepted, &run(&[(GAP, "pkg.a", "new text", 1)], true));
    assert_eq!((fewer.new.len(), fewer.gone.len()), (0, 1));
    assert_eq!((fewer.gone[0].run, fewer.gone[0].file), (1, 2));
}

#[test]
fn another_subject_or_another_kind_is_never_paired() {
    let accepted = file(json!([entry(GAP, "pkg.a", "old text", 1)]));
    let subject = compare(&accepted, &run(&[(GAP, "pkg.b", "new text", 1)], true));
    assert_eq!((subject.new.len(), subject.gone.len()), (1, 1));
    let kind = compare(
        &accepted,
        &run(&[("other_gap", "pkg.a", "new text", 1)], true),
    );
    assert_eq!((kind.new.len(), kind.gone.len()), (1, 1));
}

#[test]
fn a_typed_reason_is_matched_exactly() {
    let accepted = file(json!([entry("pair_gap", "rule", "a -> b", 1)]));
    let found = compare(&accepted, &run(&[("pair_gap", "rule", "a -> c", 1)], false));
    assert_eq!((found.new.len(), found.gone.len()), (1, 1));
}

#[test]
fn a_swap_inside_one_kind_and_subject_is_the_known_limit() {
    // One gap replaced by another of the same kind in the same module, count equal: the text is the only
    // difference, and a changed text cannot be told from a reworded one. A count that moves is red.
    let accepted = file(json!([entry(GAP, "pkg.a", "dynamic_import: pickle", 1)]));
    let swapped = compare(
        &accepted,
        &run(&[(GAP, "pkg.a", "dynamic_import: eval", 1)], true),
    );
    assert_eq!((swapped.new.len(), swapped.gone.len()), (0, 0));
}

#[test]
fn an_exact_match_is_taken_before_any_pairing() {
    let accepted = file(json!([
        entry(GAP, "pkg.a", "old text", 1),
        entry(GAP, "pkg.a", "same text", 1),
    ]));
    let now = run(
        &[
            (GAP, "pkg.a", "same text", 1),
            (GAP, "pkg.a", "new text", 2),
        ],
        true,
    );
    let found = compare(&accepted, &now);
    assert_eq!((found.new.len(), found.gone.len()), (1, 0), "{found:?}");
    assert_eq!(
        (found.new[0].reason.as_str(), found.new[0].run),
        ("new text", 2)
    );
    assert_eq!(found.new[0].file, 1);
}
