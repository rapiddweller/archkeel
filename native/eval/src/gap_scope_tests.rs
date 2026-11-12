// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a kept pair gap holds (slice S7, AD-384 point 4), over the frozen H-typescript
//! reply with its scan root `src`. Each planted gap names the rules that it MUST hold and the
//! rules that it must not hold. The run stays UNKNOWN and names each kept gap.

use std::collections::BTreeMap;

use archkeel_model::{Cause, Model, Part, Reason, Settings, Unsupported, Verdict};
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
    let rules = evaluate(&contract, &model)
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
        let gap = json!({
            "id": "UNKNOWN-00000000000000aa", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "collection_gap", "title": "pair", "subjects": [module],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"reason": "pair", "module": module, "source_module": source}
        });
        reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
        reply["facts"]["coverage"]["gaps"] = json!([gap]);
        reply["facts"]["coverage"]["full_scope"] = json!(false);
    }
}

/// A run that did not load: no rule, so every assertion on a rule fails.
pub(crate) fn failed() -> Run {
    (BTreeMap::new(), Err(Reason::NoSubjects))
}

const PAGE: &str = "shop.src.presentation.page_x2e_ts";
const ORDER: &str = "shop.src.domain.order_x2e_ts";
const INDEX: &str = "shop.src.domain.index_x2e_ts";
const LOCAL: &str = "shop.src.data.local_x2e_ts";

fn word(found: &Run, rule: &str) -> String {
    found
        .0
        .get(rule)
        .map(|(word, _)| word.clone())
        .unwrap_or_default()
}

/// True when the rule is UNKNOWN because the gaps `shown` hold it.
fn held(found: &Run, rule: &str, shown: &[&str]) -> bool {
    match found.0.get(rule) {
        Some((word, Some(Reason::NotComplete(Cause::PairGaps(gaps))))) => {
            word == "UNKNOWN" && gaps.shown() == shown && gaps.count() == shown.len()
        }
        _ => false,
    }
}

/// The run names the kept gaps.
fn run_held(found: &Run, shown: &[&str]) -> bool {
    matches!(&found.1, Err(Reason::NotComplete(Cause::PairGaps(gaps))) if gaps.shown() == shown)
}

/// `complete_requires` accepts a coverage gap with its dependency scope proof in the host, so a
/// gap that holds it is a named part (AD-380 point 3).
fn scoped(found: &Run) -> bool {
    found.0.get("REQUIRES").and_then(|(_, why)| why.clone())
        == Some(Reason::Unsupported(Unsupported::ScopeProof(
            Part::ScopedRequires,
        )))
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
fn a_kept_gap_outside_every_selection_holds_only_the_rules_that_read_every_edge() {
    // presentation does not require app: the drop rule keeps the gap.
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
    assert!(scoped(&found));
    assert!(run_held(&found, &shown));
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
    assert!(scoped(&found));
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
fn a_gap_that_the_drop_rule_drops_holds_no_rule_and_the_run_names_it() {
    // app requires presentation without `through`, no rule names either end, and no cycle
    // closes: the host drops the gap for one profile.
    let found = run(unchanged, gap(MAIN.0, PAGE), rooted()).unwrap_or_else(failed);
    for (rule, (word, why)) in &found.0 {
        assert_eq!((word.as_str(), why), ("PASS", &None), "{rule}");
    }
    assert_eq!(
        found.1,
        Err(Reason::Unsupported(Unsupported::ScopeProof(
            Part::AllowedPairGap
        )))
    );
}

/// The contract without the two rules that name modules, so the drop rule reaches its cycle part.
fn unnamed(contract: &mut Value) {
    if let Some(rules) = contract["rules"].as_array_mut() {
        rules.retain(|rule| rule["id"] != "DOMAIN-NO-DATA" && rule["id"] != "DATA-PEERS");
    }
}

#[test]
fn a_gap_inside_one_component_that_closes_a_module_cycle_is_kept() {
    // `domain.index -> domain.order` exists, so `order -> index` closes a module cycle.
    let shown = [format!("{ORDER} -> {INDEX}")];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(unnamed, gap(ORDER, INDEX), rooted()).unwrap_or_else(failed);
    assert!(held(&found, "MODULE-CYCLES", &shown));
    assert_eq!(word(&found, "LAYOUT"), "PASS");
    assert!(run_held(&found, &shown));
    // Without a module cycle rule the drop rule drops the gap: no rule is held.
    let without = both(unnamed, |contract: &mut Value| {
        if let Some(rules) = contract["rules"].as_array_mut() {
            rules.retain(|rule| rule["id"] != "MODULE-CYCLES");
        }
    });
    let dropped = run(without, gap(ORDER, INDEX), rooted()).unwrap_or_else(failed);
    assert!(
        dropped.0.values().all(|(word, _)| word == "PASS"),
        "{:?}",
        dropped.0
    );
}

#[test]
fn a_gap_along_a_requires_that_closes_a_component_cycle_is_kept() {
    // domain requires presentation, and presentation reaches domain: `order -> page` closes a
    // component cycle, so the drop rule keeps it.
    let requires = both(unnamed, |contract: &mut Value| {
        contract["components"][3]["requires"] =
            json!([{"component": "presentation", "rationale": "A test."}]);
    });
    let shown = [format!("{ORDER} -> {PAGE}")];
    let shown: Vec<&str> = shown.iter().map(String::as_str).collect();
    let found = run(requires, gap(ORDER, PAGE), rooted()).unwrap_or_else(failed);
    assert!(
        held(&found, "COMPONENT-CYCLES", &shown),
        "{:?}",
        found.0.get("COMPONENT-CYCLES")
    );
    assert!(run_held(&found, &shown));
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
