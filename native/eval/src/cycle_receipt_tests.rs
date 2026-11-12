// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cycle receipts and the receipt of `complete_requires` (slice S7, AD-384) over the frozen
//! H-typescript reply: each test removes one part of the proof and expects UNKNOWN, never PASS.

use archkeel_model::{Cause, Model, Reason};
use serde_json::{json, Value};

use crate::direction_tests::unchanged;
use crate::gap_scope_tests::{failed, rooted, run, Run};
use crate::tests::{contract, reply, shop_settings};

fn reason(found: &Run, rule: &str) -> Option<Reason> {
    found
        .0
        .get(rule)
        .and_then(|(word, why)| (word == "UNKNOWN").then(|| why.clone()).flatten())
}

fn receipt(why: &'static str) -> Option<Reason> {
    Some(Reason::NotComplete(Cause::Receipt(why)))
}

const PLANNED: &str = "the contract has a planned component";
const OUTSIDE: &str = "a component is planned or lies outside the scan roots";

#[test]
fn roots_that_are_not_the_scope_of_the_reply_refuse_the_settings() {
    let (Some(contract), Some(reply)) = (contract(unchanged), reply(unchanged)) else {
        return assert_eq!("the H-typescript contract and reply load", "");
    };
    for roots in [vec!["."], vec!["src", "lib"], vec!["sr"]] {
        let settings = shop_settings().with_roots(roots.iter().map(|r| (*r).to_owned()).collect());
        let found = Model::derive(&contract, &reply, settings).err();
        let refused = matches!(
            found,
            Some(Reason::Refused(archkeel_model::Refusal::ScanRoots))
        );
        assert!(refused, "{roots:?}: {found:?}");
    }
}

#[test]
fn a_narrow_scan_scope_withholds_the_cycle_receipts_and_the_receipt_of_requires() {
    // The collector scanned only `src/domain`: the other files lie outside the roots.
    let narrow = |reply: &mut Value| reply["facts"]["source"]["scope"] = json!(["src/domain/**"]);
    let settings = shop_settings().with_roots(vec!["src/domain".to_owned()]);
    let found = run(unchanged, narrow, settings).unwrap_or_else(failed);
    assert_eq!(reason(&found, "COMPONENT-CYCLES"), receipt(OUTSIDE));
    let outside = "a module lies outside the namespace or the scan roots";
    assert_eq!(reason(&found, "MODULE-CYCLES"), receipt(outside));
    let domain = "a component domain lies outside the scan roots";
    assert_eq!(reason(&found, "REQUIRES"), receipt(domain));
    assert_eq!(
        found.0.get("LAYOUT").map(|(word, _)| word.as_str()),
        Some("PASS")
    );
}

#[test]
fn a_planned_component_withholds_the_cycle_receipts_and_the_receipt_of_requires() {
    let planned = |contract: &mut Value| {
        contract["schema_version"] = json!("2.4.0");
        let mut component = contract["components"][3].clone();
        component["id"] = json!("COMP-PLAN");
        component["label"] = json!("plan");
        component["packages"] = json!([]);
        component["public"] = json!([]);
        component["lifecycle"] = json!("planned");
        if let Some(components) = contract["components"].as_array_mut() {
            components.push(component);
        }
    };
    let found = run(planned, unchanged, rooted()).unwrap_or_else(failed);
    assert_eq!(
        reason(&found, "COMPONENT-CYCLES"),
        receipt(OUTSIDE),
        "{:?}",
        found.0
    );
    assert_eq!(reason(&found, "MODULE-CYCLES"), receipt(PLANNED));
}

#[test]
fn an_unowned_module_withholds_the_receipt_of_requires() {
    // presentation claims `main` too: the module has two owners.
    let unowned = |contract: &mut Value| {
        contract["components"][1]["packages"] =
            json!(["shop.src.presentation", "shop.src.main_x2e_ts"]);
    };
    let found = run(unowned, unchanged, rooted()).unwrap_or_else(failed);
    assert_eq!(
        reason(&found, "REQUIRES"),
        receipt("a module has not exactly one owner")
    );
}

#[test]
fn a_dynamic_import_reaches_a_module_cycle_rule_from_any_module() {
    let limit = |source: &'static str| {
        move |reply: &mut Value| {
            let limit = json!({
                "id": "UNKNOWN-00000000000000bb", "evidence_class": "UNKNOWN", "area": "source",
                "kind": "dynamic_import_limit", "title": "dynamic", "subjects": [],
                "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
                "data": {"reason": "dynamic", "source_module": source}
            });
            reply["facts"]["sections"][1]["records"] = json!([limit]);
        }
    };
    let dynamic = Some(Reason::NotComplete(Cause::DynamicImport));
    let owned = run(unchanged, limit("shop.src.main_x2e_ts"), rooted()).unwrap_or_else(failed);
    assert_eq!(reason(&owned, "COMPONENT-CYCLES"), dynamic);
    assert_eq!(reason(&owned, "MODULE-CYCLES"), dynamic);
    let unowned = run(unchanged, limit("shop.nowhere"), rooted()).unwrap_or_else(failed);
    assert_eq!(reason(&unowned, "MODULE-CYCLES"), dynamic);
    // A component cycle closes only through an owned module.
    let word = unowned
        .0
        .get("COMPONENT-CYCLES")
        .map(|(word, _)| word.as_str());
    assert_eq!(word, Some("PASS"));
}
