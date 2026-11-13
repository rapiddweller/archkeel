// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The dependency scope proof of `complete_requires` (AD-418).
//!
//! The host can accept a coverage gap of a `complete_requires` rule when the receipt carries its
//! dependency scope proof (`ir/decisions.py` `_scoped_dependency_receipt`). It accepts the proof
//! only from a reply whose runtime can carry it (`_native_scope_runtime_valid`). For any other
//! runtime the gap is a fact: the rule is UNKNOWN and names the gap. For that runtime the core
//! cannot replay the proof, so the rule stays a named part.

use archkeel_model::{Cause, Incomplete, Part, Reason, Settings, Unsupported};
use serde_json::{json, Value};

use crate::direction_tests::{both, unchanged, MAIN};
use crate::gap_scope_tests::{failed, gap, rooted, run, word, Run, LOCAL, PAGE};
use crate::tests::shop_settings;

/// The reply as the reply of the runtime that can carry the proof.
fn proving(reply: &mut Value) {
    reply["facts"]["runtime"]["name"] = json!("python");
}

fn requires(found: &Run) -> (String, Option<Reason>) {
    found
        .0
        .get("REQUIRES")
        .cloned()
        .unwrap_or_else(|| ("no verdict".to_owned(), None))
}

fn kept(found: &Run, count: usize) -> bool {
    let (word, why) = requires(found);
    word == "UNKNOWN"
        && matches!(why, Some(Reason::NotComplete(Cause::PairGaps(held))) if held.count() == count)
}

fn part() -> Option<Reason> {
    Some(Reason::Unsupported(Unsupported::ScopeProof(
        Part::ScopedRequires,
    )))
}

/// A gap that names no source module: no contract can drop it.
fn coverage_gap(reply: &mut Value) {
    let gap = json!({
        "id": "UNKNOWN-00000000000000cc", "evidence_class": "UNKNOWN", "area": "source",
        "kind": "collection_gap", "title": "gap", "subjects": [LOCAL],
        "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
        "data": {"reason": "gap", "module": LOCAL}
    });
    reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
    reply["facts"]["coverage"]["gaps"] = json!([gap]);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

#[test]
fn a_kept_gap_of_a_runtime_without_the_proof_is_a_fact_for_complete_requires() {
    // Out of scope of the proof: the host never accepts it from this runtime.
    let found = run(unchanged, gap(PAGE, MAIN.0), rooted()).unwrap_or_else(failed);
    assert!(kept(&found, 1), "{:?}", requires(&found));
}

#[test]
fn a_kept_gap_of_the_runtime_with_the_proof_stays_a_named_part() {
    // In scope of the proof: the host can accept the gap, the core cannot replay the proof.
    let found = run(unchanged, both(proving, gap(PAGE, MAIN.0)), rooted()).unwrap_or_else(failed);
    assert_eq!(requires(&found), ("UNKNOWN".to_owned(), part()));
    // The same facts without the gap: the verdict of the host.
    let clean = run(unchanged, proving, rooted()).unwrap_or_else(failed);
    assert_eq!(requires(&clean), ("PASS".to_owned(), None));
}

#[test]
fn a_coverage_gap_follows_the_runtime_too() {
    let found = run(unchanged, coverage_gap, rooted()).unwrap_or_else(failed);
    let fact = Some(Reason::Incomplete(Incomplete::CoverageGaps(1)));
    assert_eq!(requires(&found), ("UNKNOWN".to_owned(), fact));
    let proved = run(unchanged, both(proving, coverage_gap), rooted()).unwrap_or_else(failed);
    assert_eq!(requires(&proved), ("UNKNOWN".to_owned(), part()));
}

#[test]
fn a_kept_gap_without_the_scan_roots_comes_before_the_missing_receipt() {
    // No roots: the receipt of the rule is missing (`Part::ScanRoots`). The gap is a fact for
    // this runtime, and a fact comes before a part.
    let unrooted: Settings = shop_settings();
    let found = run(unchanged, gap(PAGE, MAIN.0), unrooted.clone()).unwrap_or_else(failed);
    assert!(kept(&found, 1), "{:?}", requires(&found));
    let clean = run(unchanged, unchanged, unrooted).unwrap_or_else(failed);
    let missing = Some(Reason::Unsupported(Unsupported::ScopeProof(
        Part::ScanRoots,
    )));
    assert_eq!(requires(&clean), ("UNKNOWN".to_owned(), missing));
    assert_eq!(word(&clean, "ASSIGNMENT"), "PASS");
}
