// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scope proof of slice S4 (AD-378) over the frozen H-typescript reply and its contract.
//!
//! The clean run passes each decided rule. Each test changes exactly one input and checks that
//! the four decided kinds turn to UNKNOWN with the reason of that cause: a fact of the reference
//! engine (`Reason::NotComplete`, `Reason::Incomplete`, `Reason::NoSubjects`) or a part that the
//! core cannot read (`Unsupported::ScopeProof`), never PASS.

use archkeel_model::{Cause, Model, Part, Producer, Reason, Settings, Unsupported, Verdict};
use serde_json::{json, Value};

use crate::evaluate;
use crate::tests::{contract, reply, shop_profile, shop_settings};

/// The four decided rules of the H-typescript contract.
const DECIDED: [&str; 4] = ["ASSIGNMENT", "LAYOUT", "EXTERNAL-COMPLETE", "EXTERNAL-SHOP"];

/// The verdict word and the reason of each decided rule after the changes, or `None` when the
/// contract or the reply does not load.
fn decided(
    contract_change: impl FnOnce(&mut Value),
    reply_change: impl FnOnce(&mut Value),
    settings: Settings,
) -> Option<Vec<(String, Option<Reason>)>> {
    let contract = contract(contract_change)?;
    let reply = reply(reply_change)?;
    let model = Model::derive(&contract, &reply, settings).ok()?;
    let outcomes = evaluate(&contract, &model);
    let found = DECIDED
        .iter()
        .filter_map(|rule| outcomes.iter().find(|o| o.rule() == *rule))
        .map(|outcome| {
            let decision = outcome.decision();
            let word = match decision.verdict() {
                Verdict::Pass(_) => "PASS",
                Verdict::Fail => "FAIL",
                Verdict::Unknown => "UNKNOWN",
            };
            (word.to_owned(), decision.reason().cloned())
        })
        .collect();
    Some(found)
}

fn unchanged(_: &mut Value) {}

/// Each decided rule is UNKNOWN with `reason`.
fn all_unknown(found: Option<Vec<(String, Option<Reason>)>>, reason: &Reason) {
    let found = found.unwrap_or_default();
    assert_eq!(found.len(), 4, "the four decided rules load");
    for (word, why) in found {
        assert_eq!((word.as_str(), why.as_ref()), ("UNKNOWN", Some(reason)));
    }
}

fn not_complete(cause: Cause) -> Reason {
    Reason::NotComplete(cause)
}

fn unread(part: Part) -> Reason {
    Reason::Unsupported(Unsupported::ScopeProof(part))
}

fn add_rule(contract: &mut Value, rule: Value) {
    if let Some(rules) = contract["rules"].as_array_mut() {
        rules.push(rule);
    }
}

fn head(id: &str, kind: &str) -> Value {
    json!({"id": id, "kind": kind, "rationale": "r", "provenance": ["p"],
           "decided_by": "architect"})
}

fn with(mut value: Value, fields: Value) -> Value {
    if let (Some(target), Some(source)) = (value.as_object_mut(), fields.as_object()) {
        for (key, field) in source {
            target.insert(key.clone(), field.clone());
        }
    }
    value
}

/// A gap of the reply between two modules, in the coverage and in the `unknowns` section.
fn pair_gap(source: &str, module: &str) -> impl FnOnce(&mut Value) {
    let (source, module) = (source.to_owned(), module.to_owned());
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

#[test]
fn the_clean_run_passes_each_decided_rule() {
    let found = decided(unchanged, unchanged, shop_settings()).unwrap_or_default();
    assert_eq!(found.len(), 4);
    assert!(found
        .iter()
        .all(|(word, why)| word == "PASS" && why.is_none()));
}

#[test]
fn a_pair_gap_that_an_unowned_end_keeps_is_a_fact() {
    let found = decided(
        unchanged,
        pair_gap("shop.src.main_x2e_ts", "shop.nowhere"),
        shop_settings(),
    );
    all_unknown(found, &not_complete(Cause::PairGaps(1)));
}

#[test]
fn a_pair_gap_that_a_rule_names_is_kept() {
    // DOMAIN-NO-DATA names `shop.src.domain`, so the host keeps the gap of the pair.
    let gap = pair_gap(
        "shop.src.domain.order_x2e_ts",
        "shop.src.domain.repository_x2e_ts",
    );
    all_unknown(
        decided(unchanged, gap, shop_settings()),
        &not_complete(Cause::PairGaps(1)),
    );
}

#[test]
fn a_pair_gap_across_components_without_a_requires_is_kept() {
    let gap = pair_gap("shop.src.presentation.page_x2e_ts", "shop.src.main_x2e_ts");
    all_unknown(
        decided(unchanged, gap, shop_settings()),
        &not_complete(Cause::PairGaps(1)),
    );
}

#[test]
fn a_pair_gap_that_the_contract_allows_is_a_named_gap() {
    // `app` requires `presentation` without `through`, and no rule names either end: the host
    // drops the gap for one profile only, so the core cannot read it.
    let gap = pair_gap("shop.src.main_x2e_ts", "shop.src.presentation.page_x2e_ts");
    all_unknown(
        decided(unchanged, gap, shop_settings()),
        &unread(Part::AllowedPairGap),
    );
}

#[test]
fn a_work_tree_that_the_host_could_not_read_is_a_fact() {
    let reason = not_complete(Cause::WorkTree);
    let head = |r: &mut Value| r["facts"]["source"]["git_head"] = json!("unknown");
    all_unknown(decided(unchanged, head, shop_settings()), &reason);
    let dirty = |r: &mut Value| r["facts"]["source"]["dirty"] = json!("unknown");
    all_unknown(decided(unchanged, dirty, shop_settings()), &reason);
}

fn runtime(required: Value, state: &str) -> impl FnOnce(&mut Value) {
    let state = state.to_owned();
    move |reply: &mut Value| {
        reply["facts"]["runtime"]["required"] = required;
        reply["facts"]["runtime"]["requirement_state"] = json!(state);
    }
}

#[test]
fn a_runtime_outside_its_requirement_is_a_fact() {
    let reason = not_complete(Cause::Runtime);
    for required in [json!(">=1.89"), json!(">=2"), json!(null)] {
        let found = decided(unchanged, runtime(required, "declared"), shop_settings());
        all_unknown(found, &reason);
    }
}

#[test]
fn a_runtime_requirement_that_the_core_does_not_read_is_a_named_gap() {
    let reason = unread(Part::RuntimeRequirement);
    let cases = [
        (json!("~=1.88"), "declared"),
        (json!(">=1.88,<2"), "declared"),
        (json!(">=1.80 || >=2"), "declared"),
        (json!(">=1.88"), "metadata_missing"),
    ];
    for (required, state) in cases {
        let found = decided(unchanged, runtime(required, state), shop_settings());
        all_unknown(found, &reason);
    }
}

#[test]
fn a_runtime_at_or_above_its_bound_passes() {
    for required in [
        json!(">=1.88"),
        json!(">= 1.88.0"),
        json!(">=1"),
        json!(">=01.9"),
    ] {
        let found = decided(unchanged, runtime(required, "declared"), shop_settings());
        let found = found.unwrap_or_default();
        assert!(found.iter().all(|(word, _)| word == "PASS"), "{found:?}");
    }
}

#[test]
fn a_reply_of_an_external_collector_is_a_fact() {
    let external = Settings::new("shop".to_owned(), shop_profile(), Vec::new());
    all_unknown(
        decided(unchanged, unchanged, external.clone()),
        &not_complete(Cause::Producer),
    );
    let pinned = external.with_producer(Producer::Trusted);
    let found = decided(unchanged, unchanged, pinned).unwrap_or_default();
    assert!(found.iter().all(|(word, _)| word == "PASS"));
}

#[test]
fn a_rule_kind_that_no_store_profile_decides_is_a_fact() {
    let rule = with(
        head("TYPES", "boundary_types"),
        json!({"source": "shop.src.domain"}),
    );
    let change = |c: &mut Value| {
        c["schema_version"] = json!("2.3.0");
        add_rule(c, rule);
    };
    let found = decided(change, unchanged, shop_settings());
    all_unknown(
        found,
        &not_complete(Cause::ProfileLimit("TYPES".to_owned())),
    );
}

#[test]
fn a_declaration_that_no_store_profile_measures_is_a_fact() {
    let roots = |c: &mut Value| c["declarations"]["context_roots"] = json!(["shop.src"]);
    let found = decided(roots, unchanged, shop_settings());
    let subject = "declarations.context_roots".to_owned();
    all_unknown(found, &not_complete(Cause::ProfileLimit(subject)));
}

#[test]
fn an_interface_boundary_is_a_limit_of_one_profile_and_a_named_gap() {
    let rule = with(
        head("BOUNDARY", "interface_boundary"),
        json!({"include_type_checking": false}),
    );
    let found = decided(|c| add_rule(c, rule), unchanged, shop_settings());
    all_unknown(found, &unread(Part::ProfileLimit("BOUNDARY".to_owned())));
}

fn symbol_rule(contract: &mut Value) {
    let rule = with(
        head("SYMBOL", "forbidden_dependency"),
        json!({"source": "shop.src.presentation", "target": "shop.src.domain",
               "target_symbol": "Order", "include_type_checking": false,
               "allowed_sources": []}),
    );
    add_rule(contract, rule);
}

#[test]
fn a_symbol_selector_is_a_fact_without_the_symbol_feature() {
    let without = |r: &mut Value| {
        if let Some(features) = r["facts"]["capabilities"]["resolution_features"].as_array_mut() {
            features.retain(|feature| feature != "script-globals-v1");
        }
    };
    let found = decided(symbol_rule, without, shop_settings());
    all_unknown(
        found,
        &not_complete(Cause::ProfileLimit("SYMBOL".to_owned())),
    );
    let found = decided(symbol_rule, unchanged, shop_settings());
    all_unknown(found, &unread(Part::ProfileLimit("SYMBOL".to_owned())));
}

fn construct_rule(source: &str, constructs: Value) -> impl FnOnce(&mut Value) {
    let rule = with(
        head("CONSTRUCT", "forbidden_construct"),
        json!({"source": source, "constructs": constructs, "allowed_sources": [],
               "exact_sources": []}),
    );
    move |contract: &mut Value| add_rule(contract, rule)
}

#[test]
fn a_construct_that_the_collector_does_not_examine_is_a_fact() {
    let found = decided(
        construct_rule("shop", json!(["eval"])),
        unchanged,
        shop_settings(),
    );
    all_unknown(
        found,
        &not_complete(Cause::ProfileLimit("CONSTRUCT".to_owned())),
    );
}

/// One change of a reply.
type Probe = Box<dyn FnOnce(&mut Value)>;

/// No decided rule passes: the store refuses the reply, or each rule is not PASS.
fn no_pass(reply_change: impl FnOnce(&mut Value)) -> bool {
    match decided(unchanged, reply_change, shop_settings()) {
        None => true,
        Some(found) => found.iter().all(|(word, _)| word != "PASS"),
    }
}

#[test]
fn a_capability_set_that_is_not_registered_reaches_no_pass() {
    // Lead decision L-35a: `evaluate_source` refuses each of these replies
    // (`evaluate.py:1006-1056`). The store refuses them today; this test also holds if a later
    // store change accepts one, because then no decided rule may pass.
    let features = |r: &mut Value| -> Option<Vec<Value>> {
        r["facts"]["capabilities"]["resolution_features"]
            .as_array()
            .cloned()
    };
    let probes: Vec<Probe> = vec![
        Box::new(|r| {
            r["facts"]["capabilities"]["constructs"] =
                json!([{"name": "string_literal_compare", "status": "unsupported"}]);
        }),
        Box::new(|r| r["facts"]["capabilities"]["constructs"] = json!([])),
        Box::new(move |r| {
            let kept: Vec<Value> = features(r)
                .unwrap_or_default()
                .into_iter()
                .filter(|f| f != "literal-imports")
                .collect();
            r["facts"]["capabilities"]["resolution_features"] = json!(kept);
        }),
        Box::new(|r| {
            r["facts"]["capabilities"]["resolution_features"] = json!(["static-imports"]);
        }),
    ];
    for probe in probes {
        assert!(no_pass(probe));
    }
    assert!(reply(|r| r["facts"]["capabilities"]["constructs"] = json!([])).is_none());
}

#[test]
fn a_construct_selector_is_a_fact_for_every_store_profile() {
    let rule = with(
        head("SELECTOR", "forbidden_construct"),
        json!({"source": "shop", "constructs": ["string_literal_compare"],
               "allowed_sources": [], "exact_sources": [],
               "selector": {"receiver": "Order", "member": "id", "role": "read"}}),
    );
    let change = |c: &mut Value| {
        c["schema_version"] = json!("3.11.0");
        add_rule(c, rule);
    };
    let found = decided(change, unchanged, shop_settings());
    all_unknown(
        found,
        &not_complete(Cause::ProfileLimit("SELECTOR".to_owned())),
    );
}

#[test]
fn the_settings_name_an_external_producer_until_the_shell_names_another() {
    let fresh = Settings::new("shop".to_owned(), shop_profile(), Vec::new());
    assert_eq!(fresh.producer(), Producer::External);
    assert_eq!(Settings::default().producer(), Producer::External);
    assert_eq!(
        fresh.with_producer(Producer::Trusted).producer(),
        Producer::Trusted
    );
}

#[test]
fn a_construct_rule_without_a_module_subject_is_a_named_gap() {
    let found = decided(
        construct_rule("shop.absent", json!(["string_literal_compare"])),
        unchanged,
        shop_settings(),
    );
    all_unknown(
        found,
        &unread(Part::ConstructSubjects("CONSTRUCT".to_owned())),
    );
}

#[test]
fn a_layer_order_with_a_component_without_its_layer_is_a_fact() {
    let rule = with(head("LAYERS", "layer_order"), json!({"layers": ["base"]}));
    let change = |c: &mut Value| {
        c["schema_version"] = json!("2.3.0");
        add_rule(c, rule);
    };
    let found = decided(change, unchanged, shop_settings());
    all_unknown(
        found,
        &not_complete(Cause::LayerMetadata("LAYERS".to_owned())),
    );
}

#[test]
fn another_rule_that_selects_no_module_is_a_fact_for_each_rule() {
    let absent = |c: &mut Value| {
        if let Some(rules) = c["rules"].as_array_mut() {
            for rule in rules
                .iter_mut()
                .filter(|rule| rule["id"] == "DOMAIN-NO-DATA")
            {
                rule["source"] = json!("shop.absent");
            }
        }
    };
    let found = decided(absent, unchanged, shop_settings());
    all_unknown(
        found,
        &not_complete(Cause::NoRuleSubjects("DOMAIN-NO-DATA".to_owned())),
    );
}

fn dynamic_import(source: Option<&str>) -> impl FnOnce(&mut Value) {
    let data = match source {
        Some(source) => json!({"reason": "dynamic", "source_module": source}),
        None => json!({"reason": "dynamic"}),
    };
    move |reply: &mut Value| {
        let limit = json!({
            "id": "UNKNOWN-00000000000000bb", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "dynamic_import_limit", "title": "dynamic", "subjects": [],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [], "data": data
        });
        reply["facts"]["sections"][1]["records"] = json!([limit]);
    }
}

#[test]
fn a_dynamic_import_holds_back_only_the_rules_that_it_reaches() {
    let found = decided(
        unchanged,
        dynamic_import(Some("shop.src.presentation.page_x2e_ts")),
        shop_settings(),
    )
    .unwrap_or_default();
    let words: Vec<&str> = found.iter().map(|(word, _)| word.as_str()).collect();
    // ASSIGNMENT and LAYOUT do not read imports; both external rules see the source.
    assert_eq!(words, ["PASS", "PASS", "UNKNOWN", "UNKNOWN"]);
    let reason = not_complete(Cause::DynamicImport);
    assert!(found[2..]
        .iter()
        .all(|(_, why)| why.as_ref() == Some(&reason)));
    // An allowed source of EXTERNAL-SHOP is not held back.
    let allowed = decided(
        unchanged,
        dynamic_import(Some("shop.src.data.local_x2e_ts")),
        shop_settings(),
    )
    .unwrap_or_default();
    let words: Vec<&str> = allowed.iter().map(|(word, _)| word.as_str()).collect();
    assert_eq!(words, ["PASS", "PASS", "UNKNOWN", "PASS"]);
}

#[test]
fn a_dynamic_import_without_a_source_module_holds_back_each_rule() {
    let found = decided(unchanged, dynamic_import(None), shop_settings());
    all_unknown(found, &not_complete(Cause::DynamicImport));
}
