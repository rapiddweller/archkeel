// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a dropped pair gap holds (AD-418), over the H-typescript reply as a reply of
//! the profile whose host drops an allowed pair gap.
//!
//! The drop rule reads selector texts, not the sides of a rule. So a gap that it drops can still
//! lie on a whole-component side of a `forbidden_dependency` rule, or end in a module that can
//! re-export an external package (`archkeel_model` `dropped_gaps_tests.rs`). Such a gap holds the rule (UNKNOWN, named), where the
//! reference engine forgets it. A dropped gap that no reading sees changes no rule and not the
//! run, as in the reference engine. The assertions read the text of the reason, so they say the
//! same on a core that names the gap by another type.

use serde_json::{json, Value};

use crate::direction_tests::{both, unchanged, MAIN};
use crate::gap_scope_tests::{
    dropping, dropping_settings, failed, gap, held, run, word, Run, LOCAL, ORDER, PAGE,
};

const ALLOWS: &str =
    "gaps between two modules that the contract allows and that can change the rule";

/// The text that names `shown` as the dropped gaps that hold a rule or the run.
fn named(shown: &[&str]) -> String {
    format!("{} {ALLOWS}: {}", shown.len(), shown.join(", "))
}

/// True when the rule is UNKNOWN because the dropped gaps `shown` hold it.
fn dropped_held(found: &Run, rule: &str, shown: &[&str]) -> bool {
    match found.0.get(rule) {
        Some((word, Some(why))) => word == "UNKNOWN" && why.to_string().ends_with(&named(shown)),
        _ => false,
    }
}

/// True when the run names the dropped gaps `shown`.
fn run_dropped(found: &Run, shown: &[&str]) -> bool {
    matches!(&found.1, Err(why) if why.to_string().ends_with(&named(shown)))
}

fn without(ids: &'static [&'static str]) -> impl FnOnce(&mut Value) + Clone {
    move |contract: &mut Value| {
        if let Some(rules) = contract["rules"].as_array_mut() {
            rules.retain(|rule| !ids.iter().any(|id| rule["id"] == *id));
        }
    }
}

/// The two rules that name a module by its selector text keep every gap that they name.
const NAMING: &[&str] = &["DOMAIN-NO-DATA", "DATA-PEERS"];

/// Two components of two packages each: `front` (presentation and data) requires `back` (domain
/// and `main`) and `back` requires `front`, both without `through`. `F` forbids the edges from the
/// whole of `front` to the whole of `back`: its sides name one package of each, so the drop rule
/// does not see a gap between the other two packages. No cycle rule: the components form one.
fn nested(contract: &mut Value) {
    let component = |id: &str, label: &str, packages: [&str; 2], requires: &str| {
        json!({"id": id, "label": label, "role": "component", "packages": packages,
               "public": packages, "responsibilities": ["A test."],
               "forbidden_responsibilities": [], "provenance": ["docs/architecture/shop.md"],
               "requires": [{"component": requires, "rationale": "A test."}],
               "decided_by": "architect"})
    };
    // The UML declarations name the four components of the fixture.
    if let Some(object) = contract.as_object_mut() {
        object.remove("declarations");
    }
    contract["components"] = json!([
        component(
            "COMP-FRONT",
            "front",
            ["shop.src.presentation", "shop.src.data"],
            "back"
        ),
        component(
            "COMP-BACK",
            "back",
            ["shop.src.domain", "shop.src.main_x2e_ts"],
            "front"
        ),
    ]);
    if let Some(rules) = contract["rules"].as_array_mut() {
        rules.retain(|rule| {
            ![
                "DOMAIN-NO-DATA",
                "DATA-PEERS",
                "COMPONENT-CYCLES",
                "MODULE-CYCLES",
                "LAYOUT",
            ]
            .iter()
            .any(|id| rule["id"] == *id)
        });
        rules.push(json!({"id": "F", "kind": "forbidden_dependency",
            "source": "shop.src.presentation", "target": "shop.src.domain",
            "include_type_checking": false, "rationale": "A test.",
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect"}));
    }
}

/// Two gap records of one pair, with two ids.
fn twice(source: &'static str, module: &'static str) -> impl FnOnce(&mut Value) + Clone {
    move |reply: &mut Value| {
        let record = |id: &str| {
            json!({"id": id, "evidence_class": "UNKNOWN", "area": "source",
                   "kind": "collection_gap", "title": "pair", "subjects": [module],
                   "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
                   "data": {"reason": "pair", "module": module, "source_module": source}})
        };
        let gaps = json!([
            record("UNKNOWN-00000000000000aa"),
            record("UNKNOWN-00000000000000ab")
        ]);
        reply["facts"]["sections"][1]["records"] = gaps.clone();
        reply["facts"]["coverage"]["gaps"] = gaps;
        reply["facts"]["coverage"]["full_scope"] = json!(false);
    }
}

fn dropped(contract: impl FnOnce(&mut Value), reply: impl FnOnce(&mut Value) + Clone) -> Run {
    run(contract, both(dropping, reply), dropping_settings()).unwrap_or_else(failed)
}

#[test]
fn a_dropped_gap_between_two_whole_component_sides_holds_the_forbidden_rule_and_the_run() {
    // Review B1 of #1084: `front` requires `back` without `through`, and no rule names
    // `data.local` or `main`, so the host drops the gap and passes F. The edge would break F.
    let shown = [format!("{} -> {}", LOCAL, MAIN.0)];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = dropped(nested, gap(LOCAL, MAIN.0));
    assert!(dropped_held(&found, "F", &shown), "{:?}", found.0.get("F"));
    assert!(run_dropped(&found, &shown), "{:?}", found.1);
    // The module set and the requires read no such edge.
    assert_eq!(word(&found, "ASSIGNMENT"), "PASS");
    assert_eq!(word(&found, "REQUIRES"), "PASS");
    // The same facts without the gap: F passes, and so does the run.
    let clean = dropped(nested, unchanged);
    assert_eq!(word(&clean, "F"), "PASS", "{:?}", clean.0.get("F"));
    assert_eq!(clean.1, Ok(()));
}

#[test]
fn a_dropped_gap_that_no_reading_sees_changes_no_rule_and_not_the_run() {
    // The host forgets `main -> page` and passes each rule; so does the core.
    let found = dropped(unchanged, gap(MAIN.0, PAGE));
    assert_eq!(found.0.len(), 9, "{:?}", found.0);
    for (rule, (word, why)) in &found.0 {
        assert_eq!((word.as_str(), why), ("PASS", &None), "{rule}");
    }
    assert_eq!(found.1, Ok(()));
}

#[test]
fn a_duplicate_dropped_gap_names_each_record() {
    let shown = [format!("{} -> {}", LOCAL, MAIN.0)];
    let shown = [shown[0].as_str(), shown[0].as_str()];
    let found = dropped(nested, twice(LOCAL, MAIN.0));
    assert!(dropped_held(&found, "F", &shown), "{:?}", found.0);
    assert!(run_dropped(&found, &shown), "{:?}", found.1);
    let quiet = dropped(unchanged, twice(MAIN.0, PAGE));
    assert_eq!(quiet.1, Ok(()), "{:?}", quiet.0);
}

#[test]
fn a_dropped_gap_to_a_module_that_the_scan_did_not_see_holds_every_rule() {
    // `data` owns the unseen module by its package, so the drop rule drops the gap; the unseen
    // end can stand for imports that no reach saw, so it holds each rule, the cycles too.
    let ghost = "shop.src.data.ghost_x2e_ts";
    let shown = [format!("{} -> {ghost}", MAIN.0)];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = dropped(without(NAMING), gap(MAIN.0, ghost));
    assert_eq!(found.0.len(), 7, "{:?}", found.0);
    for rule in found.0.keys() {
        assert!(
            dropped_held(&found, rule, &shown),
            "{rule}: {:?}",
            found.0.get(rule)
        );
    }
}

#[test]
fn a_gap_on_a_forbidden_pair_is_kept_and_never_passes() {
    // domain does not require data: the drop rule keeps `order -> local`.
    let shown = [format!("{ORDER} -> {LOCAL}")];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = dropped(unchanged, gap(ORDER, LOCAL));
    assert!(held(&found, "DOMAIN-NO-DATA", &shown), "{:?}", found.0);
    assert_ne!(word(&found, "DOMAIN-NO-DATA"), "PASS");
}
