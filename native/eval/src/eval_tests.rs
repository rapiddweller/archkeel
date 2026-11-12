// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The S1 rule kinds over the frozen H-typescript reply (AD-343) and its contract.

use std::io::{Read, Write};

use archkeel_contract::{Contract, ParsedContract};
use archkeel_model::{
    Cause, Decision, Incomplete, Model, Producer, Reason, Settings, Unsupported, Verdict,
};
use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use crate::{evaluate, Outcome, Violation};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

fn read_json(path: &str) -> Value {
    let mut text = String::new();
    let full = format!("{ROOT}/{path}");
    if path.ends_with(".gz") {
        if let Ok(file) = std::fs::File::open(&full) {
            let _ = GzDecoder::new(file).read_to_string(&mut text);
        }
    } else {
        text = std::fs::read_to_string(&full).unwrap_or_default();
    }
    serde_json::from_str(&text).unwrap_or(Value::Null)
}

/// The contract of H-typescript after `change`.
pub(crate) fn contract(change: impl FnOnce(&mut Value)) -> Option<Contract> {
    let mut value = read_json("fixtures/H-typescript/architecture-contract.json");
    change(&mut value);
    match archkeel_contract::parse(value.to_string().as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        _ => None,
    }
}

/// The H-typescript reply after `change`, as the store accepts it.
pub(crate) fn reply(change: impl FnOnce(&mut Value)) -> Option<archkeel_store::Ingested> {
    reply_or_refusal(change).ok()
}

/// The H-typescript reply after `change`, or the refusal of the store.
pub(crate) fn reply_or_refusal(
    change: impl FnOnce(&mut Value),
) -> Result<archkeel_store::Ingested, String> {
    let mut value = read_json("tests/golden/typescript/h-typescript.json.gz");
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": ">=1.88",
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    change(&mut value);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    let _ = encoder.write_all(value.to_string().as_bytes());
    let bytes = encoder.finish().unwrap_or_default();
    archkeel_store::ingest_reply(&bytes, 1 << 30)
}

/// The outcomes of the rules `ASSIGNMENT` and `LAYOUT`.
pub(crate) fn run(
    contract_change: impl FnOnce(&mut Value),
    reply_change: impl FnOnce(&mut Value),
) -> Vec<Outcome> {
    let (Some(contract), Some(reply)) = (contract(contract_change), reply(reply_change)) else {
        return Vec::new();
    };
    let Ok(model) = Model::derive(&contract, &reply, shop_settings()) else {
        return Vec::new();
    };
    evaluate(&contract, &model)
        .into_iter()
        .filter(|outcome| matches!(outcome.rule(), "ASSIGNMENT" | "LAYOUT"))
        .collect()
}

fn outcome<'a>(outcomes: &'a [Outcome], rule: &str) -> Option<&'a Outcome> {
    outcomes.iter().find(|outcome| outcome.rule() == rule)
}

pub(crate) fn decision(outcomes: &[Outcome], rule: &str) -> Option<Decision> {
    outcome(outcomes, rule).map(|outcome| outcome.decision().clone())
}

fn names(outcomes: &[Outcome], rule: &str) -> Vec<String> {
    outcome(outcomes, rule)
        .map(|outcome| outcome.violations().iter().map(name).collect())
        .unwrap_or_default()
}

fn name(violation: &Violation) -> String {
    match violation {
        Violation::Unassigned { name, .. } => name.clone(),
        Violation::NotAllowedChild { child, .. } => child.clone(),
        Violation::OutsideScope { cited, .. } | Violation::Undeclared { cited, .. } => {
            format!("{} -> {}", cited.source_module, cited.target_module)
        }
    }
}

fn component(value: &mut Value, id: &str) -> Option<usize> {
    value["components"]
        .as_array()?
        .iter()
        .position(|item| item["id"] == id)
}

pub(crate) fn set_component(value: &mut Value, id: &str, key: &str, field: Value) {
    if let Some(index) = component(value, id) {
        value["components"][index][key] = field;
    }
}

pub(crate) fn set_rule(value: &mut Value, id: &str, key: &str, field: Value) {
    let index = value["rules"]
        .as_array()
        .and_then(|rules| rules.iter().position(|rule| rule["id"] == id));
    if let Some(index) = index {
        value["rules"][index][key] = field;
    }
}

fn unchanged(_: &mut Value) {}

/// The reason of a run whose rule `rule` selects no module of the reply (AD-378).
fn no_subjects(rule: &str) -> Reason {
    Reason::NotComplete(Cause::NoRuleSubjects(rule.to_owned()))
}

#[test]
fn a_clean_run_passes_with_the_scope_proof() {
    let outcomes = run(unchanged, unchanged);
    assert_eq!(outcomes.len(), 2);
    for outcome in &outcomes {
        assert!(matches!(outcome.decision().verdict(), Verdict::Pass(_)));
        assert_eq!(outcome.decision().reason(), None);
        assert!(outcome.violations().is_empty());
    }
}

#[test]
fn a_module_without_an_owner_fails_with_the_ids_of_python() {
    let outcomes = run(
        |c| set_component(c, "COMP-DATA", "packages", json!(["shop.src.store"])),
        unchanged,
    );
    assert_eq!(decision(&outcomes, "ASSIGNMENT"), Some(Decision::fail()));
    let local = outcome(&outcomes, "ASSIGNMENT").and_then(|o| {
        o.violations()
            .iter()
            .find(|v| name(v) == "shop.src.data.local_x2e_ts")
    });
    let Some(Violation::Unassigned {
        id,
        fact_id,
        source,
        ..
    }) = local
    else {
        fail("one unassigned violation expected");
        return;
    };
    // `stable_id("VIO", "ASSIGNMENT", stable_id("MOD", "shop.src.data.local_x2e_ts"))`.
    assert_eq!(id, "VIO-671ede9c9771d825");
    assert_eq!(fact_id, "MOD-18a1182dc796d79c");
    assert_eq!(source, "shop");
    let mut found = names(&outcomes, "ASSIGNMENT");
    found.sort();
    assert_eq!(
        found,
        ["shop.src.data.local_x2e_ts", "shop.src.data.remote_x2e_ts"]
    );
}

#[test]
fn a_nested_package_of_two_components_owns_nothing() {
    let outcomes = run(
        |c| set_component(c, "COMP-APP", "packages", json!(["shop.src"])),
        unchanged,
    );
    assert_eq!(decision(&outcomes, "ASSIGNMENT"), Some(Decision::fail()));
    // Each module below shop.src has two claimants, except the module of `app` itself.
    let found = names(&outcomes, "ASSIGNMENT");
    assert_eq!(found.len(), 6);
    assert!(!found.contains(&"shop.src.main_x2e_ts".to_owned()));
}

#[test]
fn a_module_named_by_two_components_owns_nothing() {
    let outcomes = run(
        |c| {
            set_component(
                c,
                "COMP-APP",
                "exact_modules",
                json!(["shop.src.domain.order_x2e_ts"]),
            )
        },
        unchanged,
    );
    assert_eq!(
        names(&outcomes, "ASSIGNMENT"),
        ["shop.src.domain.order_x2e_ts"]
    );
}

#[test]
fn a_module_outside_the_rule_source_is_not_counted() {
    let outcomes = run(
        |c| {
            set_component(c, "COMP-DATA", "packages", json!(["shop.src.store"]));
            set_rule(c, "ASSIGNMENT", "source", json!("shop.src.domain"));
        },
        unchanged,
    );
    assert!(names(&outcomes, "ASSIGNMENT").is_empty());
    assert!(
        decision(&outcomes, "ASSIGNMENT").is_some_and(|d| matches!(d.verdict(), Verdict::Pass(_)))
    );
}

#[test]
fn a_blank_module_without_an_owner_is_exempt() {
    let outcomes = run(
        |c| {
            set_component(
                c,
                "COMP-DATA",
                "packages",
                json!(["shop.src.data.remote_x2e_ts"]),
            )
        },
        |r| r["facts"]["files"][0]["blank"] = json!(true),
    );
    assert_eq!(outcomes.len(), 2, "the store accepts a blank file");
    assert!(names(&outcomes, "ASSIGNMENT").is_empty());
}

#[test]
fn a_source_without_modules_fails_the_subject_check_and_is_unknown() {
    let outcomes = run(
        |c| set_rule(c, "ASSIGNMENT", "source", json!("shop.absent")),
        unchanged,
    );
    let expected = Decision::unknown(no_subjects("ASSIGNMENT"));
    assert_eq!(decision(&outcomes, "ASSIGNMENT"), Some(expected));
}

#[test]
fn a_package_child_that_is_not_allowed_cites_the_first_module_of_the_package() {
    let outcomes = run(
        |c| {
            let allowed = json!([
                "shop.src.domain",
                "shop.src.presentation",
                "shop.src.main_x2e_ts"
            ]);
            set_rule(c, "LAYOUT", "allowed_children", allowed);
        },
        unchanged,
    );
    assert_eq!(decision(&outcomes, "LAYOUT"), Some(Decision::fail()));
    let Some(Violation::NotAllowedChild {
        id,
        fact_id,
        allowed,
        ..
    }) = outcome(&outcomes, "LAYOUT").and_then(|o| o.violations().first())
    else {
        fail("one layout violation expected");
        return;
    };
    assert_eq!(id, "VIO-bbf16d08d43f196c");
    assert_eq!(fact_id, "MOD-18a1182dc796d79c");
    assert_eq!(
        allowed,
        &[
            "shop.src.domain",
            "shop.src.main_x2e_ts",
            "shop.src.presentation"
        ]
    );
}

#[test]
fn a_module_child_and_a_child_of_a_shallow_root_are_violations() {
    let module_child = run(
        |c| {
            let allowed = json!(["shop.src.domain", "shop.src.data", "shop.src.presentation"]);
            set_rule(c, "LAYOUT", "allowed_children", allowed);
        },
        unchanged,
    );
    assert_eq!(names(&module_child, "LAYOUT"), ["shop.src.main_x2e_ts"]);
    let shallow = run(
        |c| {
            set_rule(c, "LAYOUT", "root", json!("shop"));
            set_rule(c, "LAYOUT", "allowed_children", json!([]));
        },
        unchanged,
    );
    assert_eq!(names(&shallow, "LAYOUT"), ["shop.src"]);
}

#[test]
fn a_root_without_modules_is_unknown() {
    let outcomes = run(
        |c| {
            set_rule(c, "LAYOUT", "root", json!("shop.absent"));
            set_rule(c, "LAYOUT", "allowed_children", json!([]));
        },
        unchanged,
    );
    let expected = Decision::unknown(no_subjects("LAYOUT"));
    assert_eq!(decision(&outcomes, "LAYOUT"), Some(expected));
}

/// A collection gap of the reply that no contract can drop.
fn with_gap(reply: &mut Value) {
    let gap = json!({
        "id": "UNKNOWN-0123456789abcdef",
        "evidence_class": "UNKNOWN",
        "area": "source",
        "kind": "collection_gap",
        "title": "unreadable",
        "subjects": ["shop.src.main_x2e_ts"],
        "evidence_ids": [],
        "fact_ids": [],
        "rule_ids": [],
        "provenance": [],
        "data": {"reason": "unreadable", "module": "shop.src.main_x2e_ts"}
    });
    // The coverage gap and its UNKNOWN record in the `unknowns` section (index 1).
    reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
    reply["facts"]["coverage"]["gaps"] = json!([gap]);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

#[test]
fn a_gap_of_the_reply_gives_unknown_and_a_violation_still_fails() {
    let refusal = reply_or_refusal(with_gap).err();
    assert_eq!(refusal, None, "the store accepts a reply with a gap");
    let clean = run(unchanged, with_gap);
    let expected = Decision::unknown(Reason::Incomplete(Incomplete::CoverageGaps(1)));
    assert_eq!(decision(&clean, "ASSIGNMENT"), Some(expected.clone()));
    assert_eq!(decision(&clean, "LAYOUT"), Some(expected));
    let failed = run(
        |c| set_component(c, "COMP-DATA", "packages", json!(["shop.src.store"])),
        with_gap,
    );
    assert_eq!(decision(&failed, "ASSIGNMENT"), Some(Decision::fail()));
}

#[test]
fn a_rule_kind_without_a_slice_names_its_kind() {
    let (Some(contract), Some(reply)) = (contract(unchanged), reply(unchanged)) else {
        fail("the H-typescript contract and reply load");
        return;
    };
    let Ok(model) = Model::derive(&contract, &reply, shop_settings()) else {
        fail("the model derives");
        return;
    };
    let outcomes = evaluate(&contract, &model);
    let cycles = outcomes
        .iter()
        .find(|outcome| outcome.rule() == "MODULE-CYCLES");
    let reason = cycles.and_then(|outcome| outcome.decision().reason().cloned());
    assert!(matches!(
        reason,
        Some(Reason::Unsupported(Unsupported::Rule(_)))
    ));
}

#[test]
fn an_allowed_child_matches_by_its_whole_name_not_by_a_prefix() {
    let outcomes = run(
        |c| {
            let allowed = json!([
                "shop.src.dat",
                "shop.src.domain",
                "shop.src.presentation",
                "shop.src.main_x2e_ts"
            ]);
            set_rule(c, "LAYOUT", "allowed_children", allowed);
        },
        unchanged,
    );
    assert_eq!(names(&outcomes, "LAYOUT"), ["shop.src.data"]);
}

#[test]
fn a_child_without_a_record_is_unknown_by_name() {
    let records = crate::layout::child_records([(7_usize, "a.b.m", "a.b")]);
    assert_eq!(crate::layout::cite("a.b", &records), Ok(7));
    assert_eq!(
        crate::layout::cite("a.c", &records),
        Err(Reason::UncitedChild("a.c".to_owned()))
    );
}

#[test]
fn a_module_of_the_same_name_as_a_package_is_the_cited_record() {
    // The first module of package `a.b` comes first; the module named `a.b` still wins.
    let records = crate::layout::child_records([
        (1_usize, "a.b.x", "a.b"),
        (2, "a.b.y", "a.b"),
        (3, "a.b", "a"),
    ]);
    assert_eq!(records.get("a.b"), Some(&3));
    let first = crate::layout::child_records([(1_usize, "a.b.x", "a.b"), (2, "a.b.y", "a.b")]);
    assert_eq!(first.get("a.b"), Some(&1));
}

#[test]
fn the_receipt_comes_from_the_component_that_declares_the_source() {
    // `shop.src.none` has no module, but it is a package of `data`: the receipt holds the modules
    // of `data`, so the rule is not `NoSubjects` (it waits for the scope proof).
    let outcomes = run(
        |c| {
            set_component(
                c,
                "COMP-DATA",
                "packages",
                json!(["shop.src.data", "shop.src.none"]),
            );
            set_rule(c, "ASSIGNMENT", "source", json!("shop.src.none"));
        },
        unchanged,
    );
    assert_eq!(
        decision(&outcomes, "ASSIGNMENT"),
        Some(Decision::unknown(no_subjects("ASSIGNMENT")))
    );
}

#[test]
fn a_violation_cites_the_evidence_of_the_module_not_its_record_id() {
    let golden = read_json("tests/golden/typescript/h-typescript.json.gz");
    let expected = golden["facts"]["files"][0]["evidence_id"]
        .as_str()
        .map(str::to_owned);
    let outcomes = run(
        |c| set_component(c, "COMP-DATA", "packages", json!(["shop.src.store"])),
        unchanged,
    );
    let found = outcome(&outcomes, "ASSIGNMENT").and_then(|o| {
        o.violations().iter().find_map(|v| match v {
            Violation::Unassigned { name, evidence, .. }
                if name == "shop.src.data.local_x2e_ts" =>
            {
                Some(evidence.clone())
            }
            _ => None,
        })
    });
    assert!(expected.as_deref().is_some_and(|id| id.starts_with("EVD-")));
    assert_eq!(found, expected);
}

/// Fail the test with a message (clippy refuses `panic!` in this workspace).
fn fail(message: &str) {
    assert_eq!(message, "", "the test setup failed");
}

/// The settings that the shell sends for H-typescript: its namespace, and no standard library.
pub(crate) fn shop_settings() -> Settings {
    Settings::new("shop".to_owned(), shop_profile(), Vec::new()).with_producer(Producer::Trusted)
}

/// The profile of the frozen reply, read from the reply (the sources name no language).
pub(crate) fn shop_profile() -> String {
    reply(|_| {}).map_or_else(String::new, |r| r.reply().facts.profile.as_str().to_owned())
}
