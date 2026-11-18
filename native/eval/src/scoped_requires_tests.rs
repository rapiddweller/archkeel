// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The dependency scope proof of `complete_requires` (AD-418).
//!
//! The host can accept a coverage gap of a `complete_requires` rule when the receipt carries its
//! dependency scope proof (`ir/decisions.py` `_scoped_dependency_receipt`). It accepts the proof
//! only from a reply whose runtime can carry it (`_native_scope_runtime_valid`). The core cannot
//! replay it. A coverage gap gives an UNKNOWN row; a kept pair gap stays a named part.

use archkeel_model::{Cause, Incomplete, Part, Reason, Settings, Unsupported};
use serde_json::{json, Value};

use crate::direction_tests::{both, unchanged, MAIN};
use crate::gap_scope_tests::{failed, gap, rooted, run, word, Run, INDEX, LOCAL, ORDER, PAGE};
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
fn an_observed_pair_that_cannot_violate_requires_does_not_hold_its_receipt() {
    for (source, target) in [(INDEX, ORDER), (PAGE, INDEX)] {
        let found = run(unchanged, gap(source, target), rooted()).unwrap_or_else(failed);
        assert_eq!(
            requires(&found),
            ("PASS".to_owned(), None),
            "{source} -> {target}"
        );
        assert!(found.1.is_err(), "the run still has a pair gap");
    }
}

#[test]
fn an_unrestricted_declared_target_does_not_hold_the_receipt() {
    let found = run(unchanged, gap(PAGE, INDEX), rooted()).unwrap_or_else(failed);
    assert_eq!(requires(&found), ("PASS".to_owned(), None));
}

#[test]
fn a_module_port_covers_known_and_possible_edges_but_a_symbol_port_does_not_cover_a_pair() {
    for port in ["shop.src.domain", INDEX] {
        let contract = |value: &mut Value| {
            value["components"][1]["requires"][0]["through"] = json!([port]);
        };
        let possible = run(contract, gap(PAGE, INDEX), rooted()).unwrap_or_else(failed);
        let known = run(contract, unchanged, rooted()).unwrap_or_else(failed);
        assert_eq!(requires(&possible), ("PASS".to_owned(), None), "{port}");
        assert_eq!(requires(&known), ("PASS".to_owned(), None), "{port}");
        assert!(possible.1.is_err());
    }
    for port in ["shop.src.domain.other".to_owned(), format!("{ORDER}:Item")] {
        let contract = |value: &mut Value| {
            value["components"][1]["requires"][0]["through"] = json!([INDEX, port]);
        };
        let possible = run(contract, gap(PAGE, ORDER), rooted()).unwrap_or_else(failed);
        assert!(kept(&possible, 1), "{port}: {:?}", requires(&possible));
    }
    let contract = |value: &mut Value| {
        value["components"][1]["requires"][0]["through"] = json!(["shop.src.domain"]);
    };
    for (source, target) in [
        (PAGE, "shop.src.domain.unseen"),
        ("shop.src.presentation.unseen", INDEX),
    ] {
        let possible = run(contract, gap(source, target), rooted()).unwrap_or_else(failed);
        assert!(kept(&possible, 1), "{source} -> {target}");
    }
}

#[test]
fn a_through_port_and_an_unseen_target_keep_the_receipt_open() {
    let restricted = |contract: &mut Value| {
        contract["components"][1]["requires"][0]["through"] = json!([INDEX]);
    };
    let found = run(restricted, gap(PAGE, ORDER), rooted()).unwrap_or_else(failed);
    assert!(kept(&found, 1), "{:?}", requires(&found));
    let unseen = run(unchanged, gap(PAGE, "shop.unseen"), rooted()).unwrap_or_else(failed);
    assert!(kept(&unseen, 1), "{:?}", requires(&unseen));
}

#[test]
fn an_ambiguous_owner_cannot_release_a_pair() {
    let overlap = |contract: &mut Value| {
        contract["components"][0]["packages"] = json!(["shop.src", "shop.src.main_x2e_ts"]);
    };
    let found = run(overlap, gap(INDEX, ORDER), rooted()).unwrap_or_else(failed);
    assert_eq!(word(&found, "REQUIRES"), "UNKNOWN");
}

#[test]
fn an_observed_undeclared_crossing_fails_even_with_an_allowed_pair_gap() {
    let found = run(
        unchanged,
        both(
            crate::direction_tests::point(7, MAIN.0, MAIN.1, false),
            gap(INDEX, ORDER),
        ),
        rooted(),
    )
    .unwrap_or_else(failed);
    assert_eq!(word(&found, "REQUIRES"), "FAIL");
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
    let fact = Some(Reason::Incomplete(Incomplete::CoverageGaps {
        whole: 1,
        reported: 1,
    }));
    assert_eq!(requires(&found), ("UNKNOWN".to_owned(), fact));
    let proved = run(unchanged, both(proving, coverage_gap), rooted()).unwrap_or_else(failed);
    let (status, reason) = requires(&proved);
    assert_eq!(status, "UNKNOWN");
    assert_eq!(
        reason.map(|value| value.to_string()).as_deref(),
        Some("incomplete scope: the core cannot prove the dependency scope with a coverage gap")
    );
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
