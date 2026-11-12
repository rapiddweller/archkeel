// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The doubt sources of the direction kinds (slice S5, AD-380): each test has a PASS (or the
//! verdict of the clean run) and the same run with exactly one doubt, which gives UNKNOWN with
//! its reason. `layer_order` and `complete_requires` have their own rows and receipts here.

use archkeel_facts::identity::{evidence_id, stable_id, Part as IdPart};
use archkeel_model::{Cause, Incomplete, Part, Reason};
use serde_json::{json, Value};

use crate::direction_tests::{
    both, not_complete, point, seen, set_rule, unchanged, unread, CONTRACT_PATH, LOCAL, PLAIN,
    REMOTE, SOURCED,
};

/// A dynamic import limit of `source` with the type-only flag `flag` (`None`: no flag).
fn dynamic(source: &'static str, flag: Option<bool>) -> impl FnOnce(&mut Value) {
    move |reply: &mut Value| {
        let mut data = json!({"reason": "dynamic", "source_module": source});
        if let Some(flag) = flag {
            data["under_type_checking"] = json!(flag);
        }
        let limit = json!({
            "id": "UNKNOWN-00000000000000bb", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "dynamic_import_limit", "title": "dynamic", "subjects": [],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [], "data": data
        });
        reply["facts"]["sections"][1]["records"] = json!([limit]);
    }
}

fn word(found: Option<(String, Option<Reason>, Vec<String>)>) -> Option<(String, Option<Reason>)> {
    found.map(|(word, reason, _)| (word, reason))
}

fn pass() -> Option<(String, Option<Reason>)> {
    Some(("PASS".to_owned(), None))
}

fn unknown(reason: Option<Reason>) -> Option<(String, Option<Reason>)> {
    Some(("UNKNOWN".to_owned(), reason))
}

const DOMAIN_INDEX: &str = "shop.src.domain.index_x2e_ts";

#[test]
fn a_dynamic_import_of_a_forbidden_source_holds_the_rule_back() {
    let found = seen(
        "DOMAIN-NO-DATA",
        unchanged,
        dynamic(DOMAIN_INDEX, Some(false)),
        PLAIN,
    );
    assert_eq!(word(found), unknown(not_complete(Cause::DynamicImport)));
    // A limit outside the source does not reach the rule.
    let outside = dynamic("shop.src.data.local_x2e_ts", Some(false));
    assert_eq!(
        word(seen("DOMAIN-NO-DATA", unchanged, outside, PLAIN)),
        pass()
    );
    // An exact allowed source does not reach the rule.
    let allowed = set_rule("DOMAIN-NO-DATA", "allowed_sources", json!([DOMAIN_INDEX]));
    let found = seen(
        "DOMAIN-NO-DATA",
        allowed,
        dynamic(DOMAIN_INDEX, Some(false)),
        PLAIN,
    );
    assert_eq!(word(found), pass());
}

#[test]
fn a_type_only_dynamic_import_reaches_only_a_rule_that_includes_type_only_imports() {
    let value_only = set_rule("DOMAIN-NO-DATA", "include_type_checking", json!(false));
    let found = seen(
        "DOMAIN-NO-DATA",
        value_only,
        dynamic(DOMAIN_INDEX, Some(true)),
        PLAIN,
    );
    assert_eq!(word(found), pass());
    let found = seen(
        "DOMAIN-NO-DATA",
        unchanged,
        dynamic(DOMAIN_INDEX, Some(true)),
        PLAIN,
    );
    assert_eq!(word(found), unknown(not_complete(Cause::DynamicImport)));
    // A limit without the flag stops the reference engine: it reaches the rule (fail closed).
    let value_only = set_rule("DOMAIN-NO-DATA", "include_type_checking", json!(false));
    let found = seen(
        "DOMAIN-NO-DATA",
        value_only,
        dynamic(DOMAIN_INDEX, None),
        PLAIN,
    );
    assert_eq!(word(found), unknown(not_complete(Cause::DynamicImport)));
}

#[test]
fn a_dynamic_import_of_a_member_holds_the_sibling_rule_back() {
    let member = "shop.src.data.local_x2e_ts";
    let found = seen("DATA-PEERS", unchanged, dynamic(member, Some(true)), PLAIN);
    assert_eq!(word(found), unknown(not_complete(Cause::DynamicImport)));
    let value_only = set_rule("DATA-PEERS", "include_type_checking", json!(false));
    let found = seen("DATA-PEERS", value_only, dynamic(member, Some(true)), PLAIN);
    assert_eq!(word(found), pass());
    let found = seen(
        "DATA-PEERS",
        unchanged,
        dynamic(DOMAIN_INDEX, Some(false)),
        PLAIN,
    );
    assert_eq!(word(found), pass());
}

/// The component `label` plans the module `planned` (a subject without a module of the reply).
fn planned(
    label: &'static str,
    planned: &'static [&'static str],
) -> impl FnOnce(&mut Value) + Clone {
    move |c: &mut Value| {
        let index = c["components"]
            .as_array()
            .and_then(|all| all.iter().position(|x| x["label"] == label));
        if let Some(index) = index {
            c["components"][index]["planned"] = json!(planned);
        }
    }
}

#[test]
fn a_side_that_only_a_planned_module_matches_gives_no_receipt() {
    let plan = planned("domain", &["shop.later.thing", "shop.next.thing"]);
    let source = set_rule("DOMAIN-NO-DATA", "source", json!("shop.later"));
    let found = seen(
        "DOMAIN-NO-DATA",
        both(plan.clone(), source),
        unchanged,
        PLAIN,
    );
    assert_eq!(word(found), unknown(Some(Reason::NoSubjects)));
    let members = set_rule("DATA-PEERS", "members", json!(["shop.later", "shop.next"]));
    let found = seen("DATA-PEERS", both(plan, members), unchanged, PLAIN);
    assert_eq!(word(found), unknown(Some(Reason::NoSubjects)));
}

#[test]
fn a_module_in_two_selectors_is_judged_by_each_rule() {
    // `shop.src` holds `shop.src.domain`: the edges inside `domain` are in both sides.
    let source = set_rule("DOMAIN-NO-DATA", "source", json!("shop.src"));
    let target = set_rule("DOMAIN-NO-DATA", "target", json!("shop.src.domain"));
    let found = seen("DOMAIN-NO-DATA", both(source, target), unchanged, PLAIN);
    let violations = found.map(|(_, _, ids)| ids.len());
    assert_eq!(violations, Some(6));
}

/// The H-typescript contract with layers and a `layer_order` rule over `layers`.
fn layered(layers: Value) -> impl FnOnce(&mut Value) + Clone {
    move |c: &mut Value| {
        c["schema_version"] = json!("2.3.0");
        let names = [
            ("app", "app"),
            ("presentation", "presentation"),
            ("data", "data"),
        ];
        if let Some(components) = c["components"].as_array_mut() {
            for component in components.iter_mut() {
                let label = component["label"].as_str().unwrap_or("").to_owned();
                let layer = names
                    .iter()
                    .find(|(l, _)| *l == label)
                    .map_or("domain", |(_, layer)| layer);
                component["layer"] = json!(layer);
            }
        }
        if let Some(rules) = c["rules"].as_array_mut() {
            rules.push(
                json!({"id": "LAYERS", "kind": "layer_order", "rationale": "r",
                "provenance": ["p"], "decided_by": "architect", "layers": layers}),
            );
        }
    }
}

#[test]
fn a_layer_order_passes_with_the_contract_source_and_names_it_without() {
    let order = layered(json!(["domain", "data", "presentation", "app"]));
    assert_eq!(
        word(seen("LAYERS", order.clone(), unchanged, SOURCED)),
        pass()
    );
    let found = seen("LAYERS", order, unchanged, PLAIN);
    assert_eq!(word(found), unknown(unread(Part::ContractSource)));
}

#[test]
fn a_layer_order_fails_each_requires_entry_to_an_outer_layer_and_cites_the_contract() {
    let order = layered(json!(["app", "presentation", "data", "domain"]));
    let found = seen("LAYERS", order.clone(), unchanged, SOURCED);
    let mut expected = vec![
        "app -> data".to_owned(),
        "app -> presentation".to_owned(),
        "data -> domain".to_owned(),
        "presentation -> domain".to_owned(),
    ];
    let (word_found, reason, mut ids) = found.unwrap_or_default();
    ids.sort();
    expected.sort();
    assert_eq!((word_found.as_str(), reason, ids), ("FAIL", None, expected));
    // Without the source the rows cannot cite the contract: the reference engine drops them.
    let found = seen("LAYERS", order, unchanged, PLAIN);
    assert_eq!(word(found), unknown(unread(Part::ContractSource)));
}

#[test]
fn a_layer_row_cites_the_receipt_and_the_first_line_of_the_contract() {
    let order = layered(json!(["app", "presentation", "data", "domain"]));
    let (Some(contract), Some(reply)) = (
        crate::tests::contract(order.clone()),
        crate::tests::reply(unchanged),
    ) else {
        return assert_eq!("the inputs load", "");
    };
    let settings = crate::direction_tests::sourced(order);
    let Ok(model) = archkeel_model::Model::derive(&contract, &reply, settings) else {
        return assert_eq!("the model derives", "");
    };
    let outcomes = crate::evaluate(&contract, &model);
    let Some(crate::Violation::OuterLayer(row)) = outcomes
        .iter()
        .find(|o| o.rule() == "LAYERS")
        .and_then(|o| o.violations().first())
    else {
        return assert_eq!("a layer row", "");
    };
    assert_eq!(row.evidence, evidence_id(CONTRACT_PATH, 1, 1, 0));
    let receipt = stable_id(
        "RULE-EVALUATION",
        &[IdPart::Text("root"), IdPart::Text("LAYERS")],
    );
    assert_eq!(row.receipt, receipt);
    let mut sorted = row.provenance.clone();
    sorted.sort();
    assert!(!row.provenance.is_empty());
    assert_eq!(row.provenance, sorted);
}

#[test]
fn a_contract_source_of_other_bytes_is_no_source() {
    let order = layered(json!(["domain", "data", "presentation", "app"]));
    let (Some(contract), Some(reply)) = (
        crate::tests::contract(order),
        crate::tests::reply(unchanged),
    ) else {
        return assert_eq!("the inputs load", "");
    };
    let other = crate::tests::shop_settings().with_contract_source(CONTRACT_PATH, b"{}");
    let Ok(model) = archkeel_model::Model::derive(&contract, &reply, other) else {
        return assert_eq!("the model derives", "");
    };
    let outcomes = crate::evaluate(&contract, &model);
    let reason = outcomes
        .iter()
        .find(|o| o.rule() == "LAYERS")
        .and_then(|o| o.decision()?.reason().cloned());
    assert_eq!(reason, unread(Part::ContractSource));
}

#[test]
fn a_dynamic_import_does_not_reach_a_layer_order() {
    let order = layered(json!(["domain", "data", "presentation", "app"]));
    let found = seen("LAYERS", order, dynamic(DOMAIN_INDEX, Some(false)), SOURCED);
    assert_eq!(word(found), pass());
}

#[test]
fn a_complete_requires_rule_names_its_scan_roots_and_fails_an_import_without_requires() {
    assert_eq!(
        word(seen("REQUIRES", unchanged, unchanged, PLAIN)),
        unknown(unread(Part::ScanRoots))
    );
    // `data` requires only `domain`: an import of `data.remote` from `data.local` stays inside
    // `data`, an import of `main` from `data.local` crosses to `app`.
    let inside = point(0, REMOTE.0, REMOTE.1, false);
    assert_eq!(
        word(seen("REQUIRES", unchanged, inside, PLAIN)),
        unknown(unread(Part::ScanRoots))
    );
    let crossing = point(
        0,
        crate::direction_tests::MAIN.0,
        crate::direction_tests::MAIN.1,
        true,
    );
    let found = seen("REQUIRES", unchanged, crossing.clone(), PLAIN);
    let edge = "shop.src.data.local_x2e_ts -> shop.src.main_x2e_ts".to_owned();
    assert_eq!(found, Some(("FAIL".to_owned(), None, vec![edge])));
    // A type-only import is out of a rule that leaves out type-only imports.
    let value_only = set_rule("REQUIRES", "include_type_checking", json!(false));
    let found = seen("REQUIRES", value_only, crossing, PLAIN);
    assert_eq!(word(found), unknown(unread(Part::ScanRoots)));
}

/// The `requires` entry of `data` for `domain` gets `through`.
fn through(ports: Value) -> impl FnOnce(&mut Value) + Clone {
    move |c: &mut Value| {
        let index = c["components"]
            .as_array()
            .and_then(|all| all.iter().position(|x| x["label"] == "data"));
        if let Some(index) = index {
            c["components"][index]["requires"][0]["through"] = ports;
        }
    }
}

#[test]
fn a_through_port_narrows_a_requires_entry() {
    // `data.*` import `domain.repository`.
    let port = through(json!(["shop.src.domain.repository_x2e_ts"]));
    let found = seen("REQUIRES", port, unchanged, PLAIN);
    assert_eq!(word(found), unknown(unread(Part::ScanRoots)));
    // A package port covers each module below it.
    let package = through(json!(["shop.src.domain"]));
    let found = seen("REQUIRES", package, unchanged, PLAIN);
    assert_eq!(word(found), unknown(unread(Part::ScanRoots)));
    let other = through(json!(["shop.src.domain.order_x2e_ts"]));
    let found = seen("REQUIRES", other, unchanged, PLAIN).map(|(w, _, ids)| (w, ids.len()));
    assert_eq!(found, Some(("FAIL".to_owned(), 2)));
    // With the symbol feature the profile judges a symbol port (`evaluate.py:1061`): the port
    // names `order`, so both imports of `repository` fail.
    let symbol = through(json!(["shop.src.domain.order_x2e_ts:Order"]));
    let found =
        seen("REQUIRES", symbol.clone(), unchanged, PLAIN).map(|(w, _, ids)| (w, ids.len()));
    assert_eq!(found, Some(("FAIL".to_owned(), 2)));
    // Without it the import is left out: no row, and the profile limit names the entry.
    let without = |r: &mut Value| {
        if let Some(features) = r["facts"]["capabilities"]["resolution_features"].as_array_mut() {
            features.retain(|feature| feature != "script-globals-v1");
        }
    };
    let found = seen("REQUIRES", symbol, without, PLAIN);
    let limit = not_complete(Cause::ProfileLimit("COMP-DATA".to_owned()));
    assert_eq!(found, Some(("UNKNOWN".to_owned(), limit, Vec::new())));
}

#[test]
fn a_dynamic_import_of_an_owned_module_holds_complete_requires_back() {
    let found = seen(
        "REQUIRES",
        unchanged,
        dynamic(DOMAIN_INDEX, Some(false)),
        PLAIN,
    );
    assert_eq!(word(found), unknown(not_complete(Cause::DynamicImport)));
    let value_only = set_rule("REQUIRES", "include_type_checking", json!(false));
    let found = seen(
        "REQUIRES",
        value_only,
        dynamic(DOMAIN_INDEX, Some(true)),
        PLAIN,
    );
    assert_eq!(word(found), unknown(unread(Part::ScanRoots)));
}

#[test]
fn a_coverage_gap_is_a_fact_for_each_kind_but_a_part_for_complete_requires() {
    let gap = |reply: &mut Value| {
        let gap = json!({
            "id": "UNKNOWN-00000000000000cc", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "collection_gap", "title": "gap", "subjects": [LOCAL.0],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"reason": "gap", "module": LOCAL.0}
        });
        reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
        reply["facts"]["coverage"]["gaps"] = json!([gap]);
        reply["facts"]["coverage"]["full_scope"] = json!(false);
    };
    let fact = Some(Reason::Incomplete(Incomplete::CoverageGaps(1)));
    assert_eq!(
        word(seen("DOMAIN-NO-DATA", unchanged, gap, PLAIN)),
        unknown(fact)
    );
    assert_eq!(
        word(seen("REQUIRES", unchanged, gap, PLAIN)),
        unknown(unread(Part::ScopedRequires))
    );
}

#[test]
fn a_layer_order_without_a_selected_component_has_no_receipt() {
    // A contract without components: the rule selects no component (`_layer_order_components`).
    let bare = |c: &mut Value| {
        c["schema_version"] = json!("2.3.0");
        c["components"] = json!([]);
        c["rules"] = json!([{"id": "LAYERS", "kind": "layer_order", "rationale": "r",
            "provenance": ["p"], "decided_by": "architect", "layers": ["domain"]}]);
        if let Some(object) = c.as_object_mut() {
            object.remove("declarations");
        }
    };
    let found = seen("LAYERS", bare, unchanged, SOURCED);
    assert_eq!(word(found), unknown(Some(Reason::NoSubjects)));
}
