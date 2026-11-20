// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a kept pair gap holds (slice S7, AD-384 point 4), over the frozen H-typescript
//! reply with its scan root `src`. Each planted gap names the rules that it MUST hold and the
//! rules that it must not hold. The run stays UNKNOWN and names each kept gap.

use std::collections::BTreeMap;

use archkeel_model::{Cause, Model, Reason, Settings, Verdict};
use serde_json::{json, Value};

use crate::direction_tests::{both, point, unchanged, MAIN, PAGE_IMPORT};
use crate::evaluate;
use crate::tests::{contract, reply, shop_settings};

/// The shop settings with the scan root of `fixtures/H-typescript/archkeel.toml`.
pub(crate) fn rooted() -> Settings {
    shop_settings().with_roots(vec!["src".to_owned()])
}

/// The verdict word and the reason of each rule, and the reason of the run.
pub(crate) type Run = (
    BTreeMap<String, (String, Option<Reason>)>,
    Result<(), Reason>,
);

pub(crate) fn run(
    contract_change: impl FnOnce(&mut Value),
    reply_change: impl FnOnce(&mut Value),
    settings: Settings,
) -> Option<Run> {
    let contract = contract(contract_change)?;
    let reply = reply(reply_change)?;
    let model = Model::derive(&contract, &reply, settings).ok()?;
    let rules = evaluate(&model)
        .iter()
        .filter_map(|outcome| {
            let decision = outcome.decision()?;
            let word = match decision.verdict() {
                Verdict::Pass(_) => "PASS",
                Verdict::Fail => "FAIL",
                Verdict::Unknown => "UNKNOWN",
            };
            let found = (word.to_owned(), decision.reason().cloned());
            Some((outcome.rule().to_owned(), found))
        })
        .collect();
    Some((rules, model.scope(|scope| scope.run())))
}

/// A gap `source -> module` in the coverage and the unknowns of the reply.
pub(crate) fn gap(source: &'static str, module: &'static str) -> impl FnOnce(&mut Value) + Clone {
    move |reply: &mut Value| {
        let gaps = reply["facts"]["coverage"]["gaps"].as_array_mut().unwrap();
        let id = format!("UNKNOWN-{:016x}", 0xaa + gaps.len());
        let gap = json!({
            "id": id, "evidence_class": "UNKNOWN", "area": "source",
            "kind": "collection_gap", "title": "pair", "subjects": [module],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"reason": "pair", "module": module, "source_module": source}
        });
        gaps.push(gap);
        reply["facts"]["sections"][1]["records"] = json!(gaps);
        reply["facts"]["coverage"]["full_scope"] = json!(false);
    }
}

/// A run that did not load: no rule, so every assertion on a rule fails.
pub(crate) fn failed() -> Run {
    (BTreeMap::new(), Err(Reason::NoSubjects))
}

pub(crate) const PAGE: &str = "shop.src.presentation.page_x2e_ts";
pub(crate) const ORDER: &str = "shop.src.domain.order_x2e_ts";
pub(crate) const INDEX: &str = "shop.src.domain.index_x2e_ts";
pub(crate) const LOCAL: &str = "shop.src.data.local_x2e_ts";

pub(crate) fn word(found: &Run, rule: &str) -> String {
    found
        .0
        .get(rule)
        .map(|(word, _)| word.clone())
        .unwrap_or_default()
}

/// True when the rule is UNKNOWN because the gaps `shown` hold it.
pub(crate) fn held(found: &Run, rule: &str, shown: &[&str]) -> bool {
    match found.0.get(rule) {
        Some((word, Some(Reason::NotComplete(Cause::PairGaps(gaps))))) => {
            word == "UNKNOWN" && gaps.shown() == shown && gaps.count() == shown.len()
        }
        _ => false,
    }
}

/// The run names the kept gaps.
pub(crate) fn run_held(found: &Run, shown: &[&str]) -> bool {
    matches!(&found.1, Err(Reason::NotComplete(Cause::PairGaps(gaps))) if gaps.shown() == shown)
}

/// The host accepts a coverage gap of `complete_requires` with its dependency scope proof only
/// from a runtime that can carry it (AD-380 point 3, AD-418). This reply's runtime cannot, so a
/// kept gap holds the rule as a fact.
pub(crate) fn requires_held(found: &Run) -> bool {
    matches!(
        found.0.get("REQUIRES"),
        Some((word, Some(Reason::NotComplete(Cause::PairGaps(_))))) if word == "UNKNOWN"
    )
}

#[test]
fn the_clean_run_with_its_root_passes_each_rule_and_the_run() {
    let found = run(unchanged, unchanged, rooted()).unwrap_or_else(failed);
    assert_eq!(found.0.len(), 9, "each rule has a verdict");
    for (rule, (word, why)) in &found.0 {
        assert_eq!((word.as_str(), why), ("PASS", &None), "{rule}");
    }
    assert_eq!(found.1, Ok(()));
}

#[test]
fn a_return_path_in_the_observed_graph_holds_both_cycle_rules() {
    // The observed main -> page edge gives the gap a return path at both levels.
    let shown = [format!("{PAGE} -> {}", MAIN.0)];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(unchanged, gap(PAGE, MAIN.0), rooted()).unwrap_or_else(failed);
    for rule in [
        "LAYOUT",
        "ASSIGNMENT",
        "EXTERNAL-COMPLETE",
        "EXTERNAL-SHOP",
        "DOMAIN-NO-DATA",
        "DATA-PEERS",
    ] {
        assert_eq!(word(&found, rule), "PASS", "{rule}");
    }
    assert!(held(&found, "COMPONENT-CYCLES", &shown));
    assert!(held(&found, "MODULE-CYCLES", &shown));
    assert!(requires_held(&found), "{:?}", found.0.get("REQUIRES"));
    assert!(run_held(&found, &shown));
}

#[test]
fn two_possible_edges_can_close_a_cycle_at_both_levels() {
    let forward = gap(LOCAL, PAGE);
    let back = gap(PAGE, LOCAL);
    let single = run(unchanged, back.clone(), rooted()).unwrap_or_else(failed);
    let cycle = run(unchanged, both(forward, back), rooted()).unwrap_or_else(failed);
    let shown = [format!("{LOCAL} -> {PAGE}"), format!("{PAGE} -> {LOCAL}")];
    let shown = shown.each_ref().map(String::as_str);
    for rule in ["COMPONENT-CYCLES", "MODULE-CYCLES"] {
        assert_eq!(word(&single, rule), "PASS", "{:?}", single.0);
        assert!(held(&cycle, rule, &shown), "{:?}", cycle.0);
    }
}

#[test]
fn a_scoped_cycle_can_reach_a_selected_member_that_is_not_a_gap_end() {
    let scope = |label| {
        move |contract: &mut Value| {
            for rule in contract["rules"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .filter(|rule| rule["kind"] == "no_component_cycles")
            {
                rule["components"] = json!([label]);
            }
        }
    };
    // main -> page -> index is observed. The possible index -> main reaches domain.
    let forward = gap(PAGE, MAIN.0);
    let back = gap(INDEX, MAIN.0);
    let inside = run(
        scope("domain"),
        both(forward.clone(), back.clone()),
        rooted(),
    )
    .unwrap_or_else(failed);
    let outside = run(scope("data"), both(forward, back), rooted()).unwrap_or_else(failed);
    let shown = [
        format!("{PAGE} -> {}", MAIN.0),
        format!("{INDEX} -> {}", MAIN.0),
    ];
    let shown = shown.each_ref().map(String::as_str);
    assert!(held(&inside, "MODULE-CYCLES", &shown), "{:?}", inside.0);
    assert!(held(&inside, "COMPONENT-CYCLES", &shown), "{:?}", inside.0);
    // main -> local and repository -> order join the same component cycle, but not the module cycle.
    assert!(
        held(&outside, "COMPONENT-CYCLES", &shown),
        "{:?}",
        outside.0
    );
    assert_eq!(word(&outside, "MODULE-CYCLES"), "PASS");

    let out_of_scope = run(
        scope("app"),
        both(gap(LOCAL, PAGE), gap(PAGE, LOCAL)),
        rooted(),
    )
    .unwrap_or_else(failed);
    assert_eq!(word(&out_of_scope, "COMPONENT-CYCLES"), "PASS");
    assert_eq!(word(&out_of_scope, "MODULE-CYCLES"), "PASS");
}

#[test]
fn a_gap_to_a_module_that_the_scan_did_not_see_holds_every_rule() {
    let shown = [format!("{} -> shop.nowhere", MAIN.0)];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(unchanged, gap(MAIN.0, "shop.nowhere"), rooted()).unwrap_or_else(failed);
    for rule in [
        "LAYOUT",
        "ASSIGNMENT",
        "EXTERNAL-COMPLETE",
        "EXTERNAL-SHOP",
        "DOMAIN-NO-DATA",
        "DATA-PEERS",
        "COMPONENT-CYCLES",
        "MODULE-CYCLES",
    ] {
        assert!(
            held(&found, rule, &shown),
            "{rule}: {:?}",
            found.0.get(rule)
        );
    }
    assert!(requires_held(&found), "{:?}", found.0.get("REQUIRES"));
    assert!(run_held(&found, &shown));
}

#[test]
fn a_gap_from_the_source_side_to_the_target_side_holds_the_forbidden_and_the_sibling_rule() {
    let shown = [format!("{ORDER} -> {LOCAL}")];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(unchanged, gap(ORDER, LOCAL), rooted()).unwrap_or_else(failed);
    assert!(held(&found, "DOMAIN-NO-DATA", &shown));
    assert!(held(&found, "DATA-PEERS", &shown));
    for rule in ["LAYOUT", "ASSIGNMENT", "EXTERNAL-COMPLETE", "EXTERNAL-SHOP"] {
        assert_eq!(word(&found, rule), "PASS", "{rule}");
    }
}

#[test]
fn a_gap_to_an_unowned_module_holds_the_forbidden_rule() {
    // `main` loses its owner: its gap end can be on the target side of DOMAIN-NO-DATA.
    let unowned = |contract: &mut Value| {
        contract["components"][0]["packages"] = json!(["shop.elsewhere"]);
        contract["components"][0]["public"] = json!(["shop.elsewhere"]);
    };
    let shown = [format!("{ORDER} -> {}", MAIN.0)];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(unowned, gap(ORDER, MAIN.0), rooted()).unwrap_or_else(failed);
    assert!(
        held(&found, "DOMAIN-NO-DATA", &shown),
        "{:?}",
        found.0.get("DOMAIN-NO-DATA")
    );
    // The twin: the owned `main` is not on the target side, so the gap does not hold the rule.
    let owned = run(unchanged, gap(ORDER, MAIN.0), rooted()).unwrap_or_else(failed);
    assert_eq!(word(&owned, "DOMAIN-NO-DATA"), "PASS");
}

#[test]
fn a_cycle_through_a_retargeted_import_fails_both_levels_over_a_kept_gap() {
    // `presentation.page -> main` closes `main -> page`: a FAIL is a fact also with a gap.
    let found = run(
        unchanged,
        both(point(PAGE_IMPORT, MAIN.0, MAIN.1, false), gap(ORDER, LOCAL)),
        rooted(),
    )
    .unwrap_or_else(failed);
    assert_eq!(word(&found, "COMPONENT-CYCLES"), "FAIL");
    assert_eq!(word(&found, "MODULE-CYCLES"), "FAIL");
}
/// The profile of the replies of the Rust collector, as the facts crate names it.
const RUST_PROFILE: &str = "archkeel-rust-imports";

/// The H-typescript reply as a reply of the profile whose host drops an allowed pair gap: the
/// two sections of that profile, no feature and no construct. The modules stay the same.
pub(crate) fn dropping(reply: &mut Value) {
    let keep = |name: &Value| name == "imports" || name == "unknowns";
    if let Some(sections) = reply["facts"]["sections"].as_array_mut() {
        sections.retain(|section| keep(&section["name"]));
        // The records of the dropped sections are gone, so no record cites them.
        for record in sections
            .iter_mut()
            .flat_map(|s| s["records"].as_array_mut().into_iter().flatten())
        {
            record["fact_ids"] = json!([]);
        }
    }
    reply["facts"]["capabilities"] = json!({"constructs": [], "resolution_features": [],
                                             "sections": ["imports", "unknowns"]});
    reply["facts"]["profile"] = json!(RUST_PROFILE);
    // The validation table of the Rust collector (AD-688).
    reply["facts"]["validation"] = json!({
        "registered": [{"sections": ["imports", "unknowns"], "optional_sections": ["symbols"],
                        "features": [],
                        "optional_features": ["rust-crate-edges", "rust-item-routes-v1"],
                        "constructs": []}],
        "interface": {"feature": "rust-item-routes-v1"},
        "standard_library": RUST_PROFILE,
    });
    // The collector of a profile names itself as the adapter (AD-388).
    reply["facts"]["adapter"]["name"] = json!(RUST_PROFILE);
}

/// The rooted settings of a dropping reply.
pub(crate) fn dropping_settings() -> Settings {
    Settings::new("shop".to_owned(), RUST_PROFILE.to_owned(), Vec::new())
        .with_producer(archkeel_model::Producer::Trusted)
        .with_roots(vec!["src".to_owned()])
}
