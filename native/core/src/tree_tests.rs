// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A root rule of a mounted tree never passes, and the status of a tree is never PASS (AD-379).
//! The reference engine reads the mounts for the root verdicts, so a PASS there can be false.
//! The proof names the tree (`Part::MountedTree`); the `TreeScope` arm is the second line.

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
const MOUNTED: &str =
    "unsupported: the scope proof: the contract mounts inside contracts; the core does not read \
     their coverage";

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

fn request(mount: bool) -> Value {
    let insides = if mount {
        json!([{"reference": "a.json", "identity": "a.json", "hex": hex_of(LEAF)}])
    } else {
        json!([])
    };
    json!({
        "protocol": "archkeel-dual-run-4", "case": "c", "root": "/r", "config": "archkeel.toml",
        "baseline": null, "collector_argv": null, "pinned": false,
        "contracts": {"architecture-contract.json": contract(mount)},
        "reply": {"hex": hex_of(&golden_reply())}, "sections": [], "namespace": "shop",
        "profile": golden_profile(), "standard_library": [], "insides": insides, "roots": [],
    })
}

fn frame(value: &Value) -> Value {
    let bytes = answer(value.to_string().as_bytes()).map_or(Vec::new(), |answered| answered.frame);
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn passes(got: &Value) -> Vec<String> {
    let rules = got["rules"].as_object().cloned().unwrap_or_default();
    let pass = rules.into_iter().filter(|(_, value)| value[1] == "PASS");
    pass.map(|(id, _)| id).collect()
}

#[test]
fn a_root_rule_that_passes_without_a_mount_is_named_with_one_mount_and_the_status_is_not_pass() {
    let plain = frame(&request(false));
    let passed = passes(&plain);
    assert!(passed.contains(&"ASSIGNMENT".to_owned()), "{plain}");
    // AD-380: the direction kinds pass without a mount and are named with one.
    for rule in ["DOMAIN-NO-DATA", "DATA-PEERS"] {
        assert!(passed.contains(&rule.to_owned()), "{rule}: {plain}");
    }
    let mounted = frame(&request(true));
    assert!(passes(&mounted).is_empty(), "{mounted}");
    assert_ne!(mounted["status"], "PASS");
    assert_eq!(
        mounted["self_test"]["contract"]["rules"]["ASSIGNMENT"],
        "complete_assignment"
    );
    for rule in &passed {
        assert_eq!(mounted["unsupported"]["rules"][rule], MOUNTED, "{rule}");
    }
    assert!(!mounted["rules"].to_string().contains("PASS"));
}

/// The engine with the plain fixture contract and the frozen reply of a trusted collector.
fn engine() -> Engine {
    let mut engine = Engine::default();
    let settings = Settings::new("shop".to_owned(), golden_profile(), Vec::new())
        .with_producer(Producer::Trusted);
    let _ = engine.answer(Request::Settings(settings));
    let input = crate::contract::ContractInput::root(contract(false).into_bytes());
    let _ = engine.answer(Request::Contract(input));
    let _ = engine.answer(Request::Ingest {
        reply: golden_reply(),
        inflate_limit: 1 << 30,
    });
    engine
}

#[test]
fn the_tree_scope_arm_names_a_pass_of_a_mounted_tree_also_when_the_proof_is_complete() {
    let mut engine = engine();
    let Answer::Rules(plain) = engine.answer(Request::Rules) else {
        assert_eq!("no rules answer", "a rules answer");
        return;
    };
    assert_eq!(plain.decided["ASSIGNMENT"][1], "PASS");
    let (contract, derived) = engine.derived();
    let tree = Tree::new(Vec::new(), true);
    let found = crate::rules::answer(contract, derived.model(), Some(tree));
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
