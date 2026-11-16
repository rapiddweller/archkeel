// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A profile limit holds only what reads the part that it limits (AD-644), over the frozen
//! H-typescript reply and its contract.
//!
//! Each test adds one limited part. The rule that reads it stays UNKNOWN with the limit as its
//! reason; the four decided rules, which read no limited part, keep their PASS; a seen violation
//! stays FAIL; a declaration that no rule reads holds the run and no rule.

use std::collections::BTreeMap;

use archkeel_contract::RuleKind;
use archkeel_model::{Cause, Model, Part, Reason, RunGap, Unsupported, Verdict};
use serde_json::{json, Value};

use crate::evaluate;
use crate::scope_tests::{
    add_rule, construct_rule, head, not_complete, unchanged, unread, with, DECIDED,
};
use crate::tests::{contract, reply, shop_settings};

/// The verdict word and reason of each rule, the scope of the run and the gap of its run proof.
struct Found {
    rules: BTreeMap<String, (String, Option<Reason>)>,
    run: Result<(), Reason>,
    proof: Option<RunGap>,
}

fn found(
    contract_change: impl FnOnce(&mut Value),
    reply_change: impl FnOnce(&mut Value),
) -> Option<Found> {
    let contract = contract(contract_change)?;
    let reply = reply(reply_change)?;
    let model = Model::derive(&contract, &reply, shop_settings()).ok()?;
    let outcomes = evaluate(&model);
    let rules = outcomes
        .iter()
        .filter_map(|outcome| {
            let decision = outcome.decision()?;
            let word = match decision.verdict() {
                Verdict::Pass(_) => "PASS",
                Verdict::Fail => "FAIL",
                Verdict::Unknown => "UNKNOWN",
            };
            let row = (word.to_owned(), decision.reason().cloned());
            Some((outcome.rule().to_owned(), row))
        })
        .collect();
    let run = model.scope(|scope| scope.run());
    let passed = |d: &&archkeel_model::Decision| matches!(d.verdict(), Verdict::Pass(_));
    let decisions = outcomes.iter().filter_map(|o| o.decision()).filter(passed);
    let proof = model.scope(|scope| scope.run_complete(decisions).err());
    Some(Found { rules, run, proof })
}

/// The four decided rules pass, and `held` is UNKNOWN with `reason`.
fn holds_only(found: Option<Found>, held: &str, reason: &Reason) {
    let Some(found) = found else {
        assert_eq!("the contract and the reply load", "not loaded");
        return;
    };
    for rule in DECIDED {
        let row = found
            .rules
            .get(rule)
            .map(|(word, why)| (word.as_str(), why));
        assert_eq!(row, Some(("PASS", &None)), "{rule}");
    }
    let row = found
        .rules
        .get(held)
        .map(|(word, why)| (word.as_str(), why));
    assert_eq!(row, Some(("UNKNOWN", &Some(reason.clone()))), "{held}");
}

#[test]
fn a_kind_that_no_profile_decides_holds_only_itself() {
    let rule = with(
        head("TYPES", "boundary_types"),
        json!({"source": "shop.src.domain"}),
    );
    let change = |c: &mut Value| {
        c["schema_version"] = json!("2.3.0");
        add_rule(c, rule);
    };
    // The evaluator names the kind first; the limit holds no other rule.
    let held = Reason::Unsupported(Unsupported::Rule(RuleKind::BoundaryTypes));
    holds_only(found(change, unchanged), "TYPES", &held);
}

#[test]
fn a_construct_that_the_collector_does_not_examine_holds_only_its_rule() {
    let change = construct_rule("shop", json!(["eval"]));
    let subject = "CONSTRUCT: the collector examines no eval".to_owned();
    let held = not_complete(Cause::ProfileLimit(subject));
    let result = found(change, unchanged);
    // The scope of the run is complete, but the run has no PASS: a rule (this construct rule,
    // and the open `REQUIRES` of the fixture) has none.
    let scope = result.as_ref().map(|f| &f.run);
    assert_eq!(scope, Some(&Ok(())));
    let proof = result.as_ref().and_then(|f| f.proof.as_ref());
    assert!(matches!(proof, Some(RunGap::Rule(_))), "{proof:?}");
    holds_only(result, "CONSTRUCT", &held);
}

#[test]
fn a_construct_selector_holds_only_its_rule() {
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
    let subject = "SELECTOR: the collector reads no construct selector".to_owned();
    let held = not_complete(Cause::ProfileLimit(subject));
    holds_only(found(change, unchanged), "SELECTOR", &held);
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
fn a_symbol_selector_holds_only_its_rule() {
    let without = |r: &mut Value| {
        if let Some(features) = r["facts"]["capabilities"]["resolution_features"].as_array_mut() {
            features.retain(|feature| feature != "script-globals-v1");
        }
    };
    let held = not_complete(Cause::ProfileLimit("SYMBOL".to_owned()));
    holds_only(found(symbol_rule, without), "SYMBOL", &held);
    let named = unread(Part::ProfileLimit("SYMBOL".to_owned()));
    holds_only(found(symbol_rule, unchanged), "SYMBOL", &named);
}

#[test]
fn an_interface_boundary_without_the_feature_holds_only_itself() {
    let rule = with(
        head("BOUNDARY", "interface_boundary"),
        json!({"include_type_checking": false}),
    );
    let result = found(|c| add_rule(c, rule), unchanged);
    // Its seen crossings are FAIL rows, as before AD-644; it never passes.
    let row = result.as_ref().and_then(|f| f.rules.get("BOUNDARY"));
    assert_eq!(row.map(|(word, _)| word.as_str()), Some("FAIL"));
    for rule in DECIDED {
        let row = result.as_ref().and_then(|f| f.rules.get(rule));
        assert_eq!(row, Some(&("PASS".to_owned(), None)), "{rule}");
    }
}

#[test]
fn a_declaration_that_no_rule_reads_holds_the_run_and_no_rule() {
    let roots = |c: &mut Value| c["declarations"]["context_roots"] = json!(["shop.src"]);
    let Some(result) = found(roots, unchanged) else {
        assert_eq!("the contract and the reply load", "not loaded");
        return;
    };
    for rule in DECIDED {
        let row = result.rules.get(rule);
        assert_eq!(row, Some(&("PASS".to_owned(), None)), "{rule}");
    }
    let subject = "declarations.context_roots".to_owned();
    let held = not_complete(Cause::ProfileLimit(subject));
    assert_eq!(result.run, Err(held.clone()));
    assert_eq!(result.proof, Some(RunGap::Scope(held)));
}

#[test]
fn a_seen_violation_beside_a_limit_stays_fail() {
    let forbid = with(
        head("FORBID", "forbidden_dependency"),
        json!({"source": "shop.src.presentation", "target": "shop.src.domain",
               "include_type_checking": true, "allowed_sources": []}),
    );
    let change = |c: &mut Value| {
        construct_rule("shop", json!(["eval"]))(c);
        add_rule(c, forbid);
    };
    let result = found(change, unchanged);
    let word = |rule: &str| {
        result
            .as_ref()
            .and_then(|f| f.rules.get(rule))
            .map(|(word, _)| word.clone())
    };
    assert_eq!(word("FORBID").as_deref(), Some("FAIL"));
    assert_eq!(word("CONSTRUCT").as_deref(), Some("UNKNOWN"));
}
