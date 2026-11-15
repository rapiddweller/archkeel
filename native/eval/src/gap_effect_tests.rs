// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a gap with a stated effect holds (AD-564), over the frozen H-typescript reply
//! with its scan root `src`. Each planted gap names the rules that it MUST hold and the rules
//! that it must not hold. A gap whose effect meets what a rule reads keeps the rule UNKNOWN: the
//! edge that the gap hides can be the violation. The run stays UNKNOWN with each such gap.

use archkeel_model::{Cause, Doubt, Incomplete, Reason};
use serde_json::{json, Value};

use crate::direction_tests::{both, point, unchanged, LOCAL, MAIN, PAGE_IMPORT};
use crate::gap_scope_tests::{failed, rooted, run, word, Run, INDEX, ORDER, PAGE};

const ID: &str = "UNKNOWN-00000000000000ee";

/// The rules of the fixture contract that read no edge and no code of a module.
const FILES_ONLY: [&str; 2] = ["LAYOUT", "ASSIGNMENT"];
/// The rules of the fixture contract that read the edges of each owned module.
const EVERY_EDGE: [&str; 3] = ["COMPONENT-CYCLES", "MODULE-CYCLES", "REQUIRES"];

/// A gap of `module` with the fields `fields` of its data, in the coverage and the unknowns.
fn gap(module: &'static str, fields: Value) -> impl FnOnce(&mut Value) + Clone {
    move |reply: &mut Value| {
        let mut gap = json!({
            "id": ID, "evidence_class": "UNKNOWN", "area": "source",
            "kind": "source_resolution_gap", "title": "site", "subjects": [module],
            "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"reason": "site", "module": module, "resolution_dimension": "imports"}
        });
        for (key, value) in fields.as_object().into_iter().flatten() {
            gap["data"][key] = value.clone();
        }
        reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
        reply["facts"]["coverage"]["gaps"] = json!([gap]);
        reply["facts"]["coverage"]["full_scope"] = json!(false);
    }
}

fn edges(module: &'static str) -> impl FnOnce(&mut Value) + Clone {
    gap(module, json!({"effect": {"edges": {"sources": [module]}}}))
}

fn code(module: &'static str) -> impl FnOnce(&mut Value) + Clone {
    gap(module, json!({"effect": {"modules": {"modules": [module]}}}))
}

fn every_module(module: &'static str) -> impl FnOnce(&mut Value) + Clone {
    gap(module, json!({"effect": "every_module"}))
}

/// The doubts of the gaps that hold the rule, when the rule is UNKNOWN because of them.
fn doubts(found: &Run, rule: &str) -> Option<Vec<Doubt>> {
    match found.0.get(rule) {
        Some((word, Some(Reason::NotComplete(Cause::ScopedGaps(scoped))))) => {
            assert_eq!(word, "UNKNOWN", "{rule}");
            assert_eq!(scoped.ids(), [ID], "{rule}");
            Some(scoped.doubts().to_vec())
        }
        _ => None,
    }
}

/// Each rule of `held` is UNKNOWN because of `doubt`; each rule of `decided` passes; the run is
/// UNKNOWN because of the gap.
fn assert_scope(found: &Run, doubt: &Doubt, held: &[&str], decided: &[&str]) {
    assert_eq!(found.0.len(), 9, "each rule has a verdict");
    assert_eq!(held.len() + decided.len(), 9, "the test names each rule");
    for rule in held {
        let expected = Some(vec![doubt.clone()]);
        assert_eq!(doubts(found, rule), expected, "{rule}: {:?}", found.0.get(*rule));
    }
    for rule in decided {
        assert_eq!(word(found, rule), "PASS", "{rule}: {:?}", found.0.get(*rule));
    }
    assert!(
        matches!(&found.1, Err(Reason::NotComplete(Cause::ScopedGaps(all))) if all.ids() == [ID]),
        "{:?}",
        found.1
    );
}

#[test]
fn the_edges_of_a_source_module_hold_the_rules_that_read_them_and_no_other_rule() {
    // `domain.index` is a source of DOMAIN-NO-DATA, no data member and no allowed source of
    // `@shop/transport`: the edge that the gap hides can break each rule but DATA-PEERS.
    let found = run(unchanged, edges(INDEX), rooted()).unwrap_or_else(failed);
    let held = [&EVERY_EDGE[..], &["EXTERNAL-COMPLETE", "EXTERNAL-SHOP", "DOMAIN-NO-DATA"]].concat();
    let decided = [&FILES_ONLY[..], &["DATA-PEERS"]].concat();
    assert_scope(&found, &Doubt::Edges(INDEX.to_owned()), &held, &decided);
}

#[test]
fn the_edges_of_a_member_hold_the_sibling_rule_and_not_the_rules_that_exempt_the_module() {
    // `data.local` is a member of DATA-PEERS, an allowed source of `@shop/transport`, and owned
    // by a component that is not on the source side of DOMAIN-NO-DATA.
    let found = run(unchanged, edges(LOCAL.0), rooted()).unwrap_or_else(failed);
    let held = [&EVERY_EDGE[..], &["EXTERNAL-COMPLETE", "DATA-PEERS"]].concat();
    let decided = [&FILES_ONLY[..], &["EXTERNAL-SHOP", "DOMAIN-NO-DATA"]].concat();
    assert_scope(&found, &Doubt::Edges(LOCAL.0.to_owned()), &held, &decided);
}

#[test]
fn the_code_of_a_module_holds_each_rule_that_reads_its_edges() {
    let found = run(unchanged, code(PAGE), rooted()).unwrap_or_else(failed);
    let held = [&EVERY_EDGE[..], &["EXTERNAL-COMPLETE", "EXTERNAL-SHOP"]].concat();
    let decided = [&FILES_ONLY[..], &["DOMAIN-NO-DATA", "DATA-PEERS"]].concat();
    assert_scope(&found, &Doubt::Code(PAGE.to_owned()), &held, &decided);
}

#[test]
fn the_code_of_every_module_holds_each_rule_but_the_rules_of_the_files() {
    let found = run(unchanged, every_module(ORDER), rooted()).unwrap_or_else(failed);
    let held = [
        &EVERY_EDGE[..],
        &["EXTERNAL-COMPLETE", "EXTERNAL-SHOP", "DOMAIN-NO-DATA", "DATA-PEERS"],
    ]
    .concat();
    assert_scope(&found, &Doubt::EveryModule, &held, &FILES_ONLY);
}

#[test]
fn an_unowned_module_can_be_a_source_of_the_forbidden_rule() {
    // `main` loses its owner, so its hidden edge can be on the source side of DOMAIN-NO-DATA.
    let unowned = |contract: &mut Value| {
        contract["components"][0]["packages"] = json!(["shop.elsewhere"]);
        contract["components"][0]["public"] = json!(["shop.elsewhere"]);
    };
    let found = run(unowned, edges(MAIN.0), rooted()).unwrap_or_else(failed);
    let expected = Some(vec![Doubt::Edges(MAIN.0.to_owned())]);
    assert_eq!(doubts(&found, "DOMAIN-NO-DATA"), expected);
    // The twin: the owned `main` is not a source, so the rule is decided.
    let owned = run(unchanged, edges(MAIN.0), rooted()).unwrap_or_else(failed);
    assert_eq!(word(&owned, "DOMAIN-NO-DATA"), "PASS");
}

#[test]
fn a_symbol_rule_reads_the_code_of_each_module_and_the_edges_of_its_sources() {
    // The source of SYMBOL is `presentation`: `data.local` is no source, but a binding on the
    // way to the symbol can lie in it.
    let symbol = |contract: &mut Value| {
        if let Some(rules) = contract["rules"].as_array_mut() {
            rules.push(json!({"id": "SYMBOL", "kind": "forbidden_dependency",
                "rationale": "r", "provenance": ["p"], "decided_by": "architect",
                "source": "shop.src.presentation", "target": "shop.src.domain",
                "target_symbol": "Order", "include_type_checking": false,
                "allowed_sources": []}));
        }
    };
    let found = run(symbol, code(LOCAL.0), rooted()).unwrap_or_else(failed);
    let expected = Some(vec![Doubt::Code(LOCAL.0.to_owned())]);
    assert_eq!(doubts(&found, "SYMBOL"), expected);
    // The twin: the edges of a module that is no source are not in the read set of the rule.
    let found = run(symbol, edges(LOCAL.0), rooted()).unwrap_or_else(failed);
    assert_eq!(doubts(&found, "SYMBOL"), None, "{:?}", found.0.get("SYMBOL"));
    let found = run(symbol, edges(PAGE), rooted()).unwrap_or_else(failed);
    let expected = Some(vec![Doubt::Edges(PAGE.to_owned())]);
    assert_eq!(doubts(&found, "SYMBOL"), expected);
}

#[test]
fn a_violation_behind_a_gap_never_passes() {
    // Seen: `domain.index -> data.local` is a violation, and a FAIL is a fact also with a gap.
    let seen = point(2, LOCAL.0, LOCAL.1, false);
    let found = run(unchanged, both(seen, edges(INDEX)), rooted()).unwrap_or_else(failed);
    assert_eq!(word(&found, "DOMAIN-NO-DATA"), "FAIL");
    // Hidden: the reply has no such edge, and the gap says that an edge of `domain.index` can be
    // absent. The rule is UNKNOWN for each effect that covers the edge, and never PASS.
    for hidden in [
        gap(INDEX, json!({"effect": {"edges": {"sources": [INDEX]}}})),
        gap(INDEX, json!({"effect": {"modules": {"modules": [INDEX]}}})),
        gap(INDEX, json!({"effect": "every_module"})),
        gap(INDEX, json!({})),
    ] {
        let found = run(unchanged, hidden, rooted()).unwrap_or_else(failed);
        assert_eq!(word(&found, "DOMAIN-NO-DATA"), "UNKNOWN");
    }
    // A cycle that the reply shows fails both levels over a gap of every module.
    let cycle = point(PAGE_IMPORT, MAIN.0, MAIN.1, false);
    let found = run(unchanged, both(cycle, every_module(ORDER)), rooted()).unwrap_or_else(failed);
    assert_eq!(word(&found, "COMPONENT-CYCLES"), "FAIL");
    assert_eq!(word(&found, "MODULE-CYCLES"), "FAIL");
}

#[test]
fn a_gap_without_a_usable_effect_holds_every_rule() {
    let whole = Some(Reason::Incomplete(Incomplete::CoverageGaps(1)));
    for (name, fields) in [
        ("no effect", json!({})),
        ("no source", json!({"effect": {"edges": {"sources": []}}})),
        ("no module", json!({"effect": {"modules": {"modules": []}}})),
        (
            "a module that the reply does not have",
            json!({"effect": {"edges": {"sources": [INDEX, "shop.nowhere"]}}}),
        ),
        (
            "a module that the reply does not have",
            json!({"effect": {"modules": {"modules": ["shop.nowhere"]}}}),
        ),
    ] {
        let found = run(unchanged, gap(INDEX, fields), rooted()).unwrap_or_else(failed);
        assert_eq!(found.0.len(), 9, "{name}");
        for (rule, (word, why)) in &found.0 {
            assert_eq!((word.as_str(), why), ("UNKNOWN", &whole), "{name}: {rule}");
        }
        assert_eq!(found.1, Err(Reason::Incomplete(Incomplete::CoverageGaps(1))));
    }
}

#[test]
fn a_gap_between_two_modules_with_an_effect_holds_every_rule() {
    // The form of AD-357 and a stated effect are two statements: the wider one stands.
    let fields = json!({"source_module": ORDER, "effect": {"edges": {"sources": [ORDER]}}});
    let found = run(unchanged, gap(INDEX, fields), rooted()).unwrap_or_else(failed);
    for (rule, (word, why)) in &found.0 {
        let whole = Some(Reason::Incomplete(Incomplete::CoverageGaps(1)));
        assert_eq!((word.as_str(), why), ("UNKNOWN", &whole), "{rule}");
    }
}
