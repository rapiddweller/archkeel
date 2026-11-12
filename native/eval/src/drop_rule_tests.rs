// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The drop rule of the pair gaps (slice S7, AD-384 point 4, review B1 and S1 of #1084).
//!
//! The host drops an allowed pair gap only for a profile whose host drops it
//! (`check/pair_gaps.py:66`); the model reads that from the typed profile fact
//! (`PairGapDrop`). A gap that the drop rule drops names each rule and the run. A gap that it
//! keeps holds the rules that it can change. The H-typescript reply keeps every gap; the
//! `dropping` form of the same reply is a reply of a profile whose host drops.

use archkeel_model::{Part, Reason, Unsupported};
use serde_json::{json, Value};

use crate::direction_tests::{both, unchanged, MAIN};
use crate::gap_scope_tests::{
    dropping, dropping_settings, failed, gap, held, rooted, run, run_held, scoped, word, Run,
    INDEX, ORDER, PAGE,
};

fn allowed() -> Reason {
    Reason::Unsupported(Unsupported::ScopeProof(Part::AllowedPairGap))
}

/// Each rule and the run name the dropped gap.
fn all_named(found: &Run) -> bool {
    !found.0.is_empty()
        && found
            .0
            .values()
            .all(|(_, why)| why.as_ref() == Some(&allowed()))
        && found.1 == Err(allowed())
}

fn texts(gaps: &[String]) -> Vec<&str> {
    gaps.iter().map(String::as_str).collect()
}

/// The H-typescript contract without the two rules that name modules.
fn unnamed(contract: &mut Value) {
    if let Some(rules) = contract["rules"].as_array_mut() {
        rules.retain(|rule| rule["id"] != "DOMAIN-NO-DATA" && rule["id"] != "DATA-PEERS");
    }
}

fn without(id: &'static str) -> impl FnOnce(&mut Value) + Clone {
    move |contract: &mut Value| {
        if let Some(rules) = contract["rules"].as_array_mut() {
            rules.retain(|rule| rule["id"] != id);
        }
    }
}

#[test]
fn a_planted_allowed_gap_on_a_profile_whose_host_keeps_it_holds_its_readings_and_the_run() {
    // Review B1: Python keeps this gap for this profile and gives UNKNOWN on each rule. The
    // core keeps it too: it holds the rules that read every edge and the run; each other rule
    // passes beyond Python and the frame lists it (`beyond`).
    let shown = [format!("{} -> {PAGE}", MAIN.0)];
    let found = run(unchanged, gap(MAIN.0, PAGE), rooted()).unwrap_or_else(failed);
    assert!(
        held(&found, "COMPONENT-CYCLES", &texts(&shown)),
        "{:?}",
        found.0
    );
    assert!(held(&found, "MODULE-CYCLES", &texts(&shown)));
    assert!(scoped(&found));
    assert!(run_held(&found, &texts(&shown)));
    for rule in [
        "LAYOUT",
        "ASSIGNMENT",
        "EXTERNAL-SHOP",
        "DOMAIN-NO-DATA",
        "DATA-PEERS",
    ] {
        assert_eq!(word(&found, rule), "PASS", "{rule}");
    }
}

#[test]
fn a_gap_that_the_drop_rule_drops_names_each_rule_and_the_run() {
    let found = run(
        unchanged,
        both(dropping, gap(MAIN.0, PAGE)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(all_named(&found), "{found:?}");
    // The same reply without the gap passes each rule: the name comes from the gap.
    let clean = run(unchanged, dropping, dropping_settings()).unwrap_or_else(failed);
    assert!(
        clean.0.values().all(|(word, _)| word == "PASS"),
        "{:?}",
        clean.0
    );
}

#[test]
fn a_gap_along_a_requires_with_through_is_kept() {
    // Review S1 (a): app requires presentation only through `page`; the drop rule keeps the gap.
    let through = |contract: &mut Value| {
        contract["components"][0]["requires"][1]["through"] = json!([PAGE]);
    };
    let shown = [format!("{} -> {PAGE}", MAIN.0)];
    let found = run(
        through,
        both(dropping, gap(MAIN.0, PAGE)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(run_held(&found, &texts(&shown)), "{:?}", found.1);
    assert!(held(&found, "COMPONENT-CYCLES", &texts(&shown)));
}

#[test]
fn a_gap_that_a_rule_names_is_kept() {
    // Review S1 (d): DOMAIN-NO-DATA names `shop.src.presentation`, an end of the gap.
    let named = |contract: &mut Value| {
        if let Some(rules) = contract["rules"].as_array_mut() {
            for rule in rules
                .iter_mut()
                .filter(|rule| rule["id"] == "DOMAIN-NO-DATA")
            {
                rule["target"] = json!("shop.src.presentation");
            }
        }
    };
    let shown = [format!("{} -> {PAGE}", MAIN.0)];
    let found = run(
        named,
        both(dropping, gap(MAIN.0, PAGE)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(run_held(&found, &texts(&shown)), "{:?}", found.1);
    // The rule reads the edges from domain; `main` is not on its source side.
    assert_eq!(word(&found, "DOMAIN-NO-DATA"), "PASS");
}

#[test]
fn a_gap_inside_one_component_that_closes_a_module_cycle_is_kept() {
    // `domain.index -> domain.order` exists, so `order -> index` closes a module cycle.
    let shown = [format!("{ORDER} -> {INDEX}")];
    let found = run(
        unnamed,
        both(dropping, gap(ORDER, INDEX)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(
        held(&found, "MODULE-CYCLES", &texts(&shown)),
        "{:?}",
        found.0
    );
    assert_eq!(word(&found, "LAYOUT"), "PASS");
    assert!(run_held(&found, &texts(&shown)));
    // Without a module cycle rule the drop rule drops the gap.
    let contract = both(unnamed, without("MODULE-CYCLES"));
    let dropped = run(
        contract,
        both(dropping, gap(ORDER, INDEX)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(all_named(&dropped), "{dropped:?}");
}

#[test]
fn a_gap_along_a_requires_that_closes_a_component_cycle_is_kept() {
    // domain requires presentation, and presentation reaches domain: `order -> page` closes a
    // component cycle. Without the module cycle rule only the component part keeps it.
    let requires = both(unnamed, |contract: &mut Value| {
        contract["components"][3]["requires"] =
            json!([{"component": "presentation", "rationale": "A test."}]);
        if let Some(rules) = contract["rules"].as_array_mut() {
            rules.retain(|rule| rule["id"] != "MODULE-CYCLES");
        }
    });
    let shown = [format!("{ORDER} -> {PAGE}")];
    let found = run(
        requires,
        both(dropping, gap(ORDER, PAGE)),
        dropping_settings(),
    )
    .unwrap_or_else(failed);
    assert!(
        held(&found, "COMPONENT-CYCLES", &texts(&shown)),
        "{:?}",
        found.0
    );
    assert!(run_held(&found, &texts(&shown)));
}

#[test]
fn a_gap_from_a_module_that_the_scan_did_not_see_holds_every_rule() {
    // Review S1 (c): the source end is outside the reply, the target end is a module of it.
    let shown = [format!("shop.nowhere -> {}", MAIN.0)];
    let found = run(unchanged, gap("shop.nowhere", MAIN.0), rooted()).unwrap_or_else(failed);
    for rule in [
        "LAYOUT",
        "ASSIGNMENT",
        "EXTERNAL-SHOP",
        "DOMAIN-NO-DATA",
        "DATA-PEERS",
    ] {
        assert!(
            held(&found, rule, &texts(&shown)),
            "{rule}: {:?}",
            found.0.get(rule)
        );
    }
}
