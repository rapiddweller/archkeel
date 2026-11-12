// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules of a contract tree (AD-379, AD-385). Each contract of the tree has a model of its
//! own with the source domain of its mount; a coverage failure of any mount holds back each PASS
//! of the run; a tree whose models do not hold every mount never passes (the second line).

use std::collections::BTreeMap;

use serde_json::{json, Value};

use archkeel_model::{Producer, Reason, Settings, Unsupported};

use super::{answer, names_a_part, ContractState, ReplyCheck, RuleReasons};
use crate::engine::tests::{golden_profile, golden_reply};
use crate::engine::{Answer, Engine};
use crate::request::Request;
use crate::rules::Tree;

/// The contract of the H-typescript fixture: its decided rules pass on the frozen reply.
const CONTRACT: &str = include_str!("../../../fixtures/H-typescript/architecture-contract.json");
const LEAF: &[u8] = br#"{"schema_version": "2.2.0", "components": [], "rules": []}"#;
const DOMAIN: &str = "shop.src.domain";

fn hex_of(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The fixture contract, with `inside` on the component `domain` when `mount` is set.
fn contract(mount: bool) -> String {
    let mut value: Value = serde_json::from_str(CONTRACT).unwrap_or(Value::Null);
    if mount {
        if let Some(components) = value["components"].as_array_mut() {
            for item in components
                .iter_mut()
                .filter(|item| item["label"] == "domain")
            {
                item["inside"] = json!("a.json");
            }
        }
    }
    value.to_string()
}

/// An inside contract: one component per package, and one `complete_assignment` rule `IN`.
fn inside(packages: &[&str]) -> Vec<u8> {
    let components: Vec<Value> = packages
        .iter()
        .enumerate()
        .map(|(index, package)| {
            json!({"id": format!("C-{index}"), "label": format!("c{index}"), "role": "component",
                   "packages": [package], "responsibilities": ["Own it."],
                   "forbidden_responsibilities": [], "provenance": ["docs/a.md"]})
        })
        .collect();
    let rule = json!({"id": "IN", "kind": "complete_assignment", "source": DOMAIN,
                      "rationale": "r", "provenance": ["docs/a.md"], "decided_by": "architect"});
    json!({"schema_version": "2.2.0", "components": components, "rules": [rule]})
        .to_string()
        .into_bytes()
}

fn request(leaf: Option<&[u8]>) -> Value {
    let insides = match leaf {
        Some(bytes) => json!([{"reference": "a.json", "identity": "a.json", "hex": hex_of(bytes)}]),
        None => json!([]),
    };
    json!({
        "protocol": "archkeel-dual-run-4", "case": "c", "root": "/r", "config": "archkeel.toml",
        "baseline": null, "collector_argv": null, "pinned": false,
        "contracts": {"architecture-contract.json": contract(leaf.is_some())},
        "reply": {"hex": hex_of(&golden_reply())}, "sections": [], "namespace": "shop",
        "profile": golden_profile(), "standard_library": [], "insides": insides, "roots": [],
    })
}

fn frame(value: &Value) -> Value {
    let bytes = answer(value.to_string().as_bytes()).map_or(Vec::new(), |answered| answered.frame);
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn statuses(got: &Value) -> BTreeMap<String, String> {
    let rules = got["rules"].as_object().cloned().unwrap_or_default();
    let status = |value: &Value| value[1].as_str().unwrap_or_default().to_owned();
    rules
        .iter()
        .map(|(id, value)| (id.clone(), status(value)))
        .collect()
}

#[test]
fn a_mount_without_rules_and_claims_leaves_each_root_verdict_as_without_the_mount() {
    let plain = frame(&request(None));
    let mounted = frame(&request(Some(LEAF)));
    assert!(statuses(&plain).values().any(|status| status == "PASS"));
    assert_eq!(statuses(&mounted), statuses(&plain), "{mounted}");
    assert_eq!(mounted["status"], plain["status"]);
    assert_eq!(mounted["scope"], plain["scope"]);
}

#[test]
fn a_rule_of_a_mount_passes_with_the_proof_of_its_own_model_under_its_scoped_id() {
    let leaf = inside(&[
        "shop.src.domain.index_x2e_ts",
        "shop.src.domain.order_x2e_ts",
        "shop.src.domain.repository_x2e_ts",
    ]);
    let got = frame(&request(Some(&leaf)));
    assert_eq!(
        statuses(&got).get("domain:IN").map(String::as_str),
        Some("PASS"),
        "{got}"
    );
    assert_eq!(
        statuses(&got).get("ASSIGNMENT").map(String::as_str),
        Some("PASS")
    );
}

#[test]
fn a_module_of_the_domain_without_an_owner_in_the_mount_fails_the_inside_rule_only() {
    let leaf = inside(&["shop.src.domain.order_x2e_ts"]);
    let got = frame(&request(Some(&leaf)));
    assert_eq!(
        statuses(&got).get("domain:IN").map(String::as_str),
        Some("FAIL"),
        "{got}"
    );
    // The two modules of the domain that the inside contract does not own.
    assert_eq!(got["violations"]["domain:IN"], 2);
    assert_eq!(
        statuses(&got).get("ASSIGNMENT").map(String::as_str),
        Some("PASS")
    );
}

#[test]
fn a_claim_outside_the_parent_holds_back_each_pass_of_the_tree() {
    let leaf = inside(&[
        "shop.src.domain.index_x2e_ts",
        "shop.src.domain.order_x2e_ts",
        "shop.src.domain.repository_x2e_ts",
        "shop.src.data",
    ]);
    let got = frame(&request(Some(&leaf)));
    let found = statuses(&got);
    assert!(found.values().all(|status| status != "PASS"), "{got}");
    assert_eq!(found.get("ASSIGNMENT").map(String::as_str), Some("UNKNOWN"));
    assert_eq!(found.get("domain:IN").map(String::as_str), Some("UNKNOWN"));
    let why = got["explained"]["domain:IN"].as_str().unwrap_or_default();
    assert!(why.contains("a component inside domain claims a module outside its parent"));
    assert_ne!(got["status"], "PASS");
}

/// The engine with the fixture contract mounting `leaf`, and the frozen reply of a trusted
/// collector.
fn engine(leaf: &[u8]) -> Engine {
    let mut engine = Engine::default();
    let settings = Settings::new("shop".to_owned(), golden_profile(), Vec::new())
        .with_producer(Producer::Trusted);
    let _ = engine.answer(Request::Settings(settings));
    let mut input = crate::contract::ContractInput::root(contract(true).into_bytes());
    input.insides.push(crate::contract::InsideFile {
        reference: "a.json".to_owned(),
        identity: "a.json".to_owned(),
        bytes: leaf.to_vec(),
    });
    let _ = engine.answer(Request::Contract(input));
    let _ = engine.answer(Request::Ingest {
        reply: golden_reply(),
        inflate_limit: 1 << 30,
    });
    engine
}

#[test]
fn the_second_line_names_a_pass_of_a_tree_whose_models_do_not_hold_every_mount() {
    let mut engine = engine(LEAF);
    let Answer::Rules(whole) = engine.answer(Request::Rules) else {
        assert_eq!("no rules answer", "a rules answer");
        return;
    };
    assert_eq!(whole.decided["ASSIGNMENT"][1], "PASS");
    let (contract, derived) = engine.derived();
    // The tree has one mount; a count of two is a tree that the models do not hold.
    let found = crate::rules::answer(contract, derived.models(), Some(Tree::new(Vec::new(), 2)));
    let scope = Reason::Unsupported(Unsupported::TreeScope);
    assert_eq!(found.reasons.get("ASSIGNMENT"), Some(&scope));
    assert!(found.decided.values().all(|[_, status]| status != "PASS"));
}

#[test]
fn a_named_inside_rule_keeps_the_status_of_a_complete_run_from_pass() {
    let only_inside = RuleReasons::Each(BTreeMap::from([(
        "a:M".to_owned(),
        Reason::Unsupported(Unsupported::InsideRule).to_string(),
    )]));
    let parsed = ContractState::Parsed(BTreeMap::new());
    let named = names_a_part(&only_inside, &ReplyCheck::Files(1), &parsed);
    assert!(named);
    let decided = BTreeMap::from([("R".to_owned(), ["k".to_owned(), "PASS".to_owned()])]);
    assert_eq!(crate::status::status(&decided, named, true), "UNKNOWN");
    let none = RuleReasons::Each(BTreeMap::new());
    assert!(!names_a_part(&none, &ReplyCheck::Files(1), &parsed));
}
