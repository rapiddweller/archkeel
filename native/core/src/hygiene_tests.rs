// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The hygiene of a run (AD-458): a refusal for an unread document, a named row for each defect
//! and for each family that applies and is not ported, and nothing for a clean contract.

use std::collections::BTreeSet;

use archkeel_contract::{parse, Contract, ParsedContract};
use archkeel_model::{Input, Reason, Unsupported};
use serde_json::{json, Value};

use super::check;
use crate::contract::{answer, ContractInput};
use crate::hygiene_pairs::{closed_world, permitted};
use crate::provenance::Documents;

const PAGE: &str = "# Page\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n```\n";

fn component(label: &str, requires: &[&str]) -> Value {
    let entries: Vec<Value> = requires
        .iter()
        .map(|target| json!({"component": target, "rationale": "Load the orders.", "through": []}))
        .collect();
    json!({"id": format!("C-{label}"), "label": label, "role": "component",
           "packages": [format!("app.{label}")], "responsibilities": ["Own it."],
           "forbidden_responsibilities": [], "provenance": ["d.md"], "decided_by": "architect",
           "requires": entries})
}

fn rule(id: &str, kind: &str, extra: Value) -> Value {
    let mut item = json!({"id": id, "kind": kind, "rationale": "Keep the layers apart.",
                          "provenance": ["d.md"], "decided_by": "architect"});
    if let (Some(map), Value::Object(more)) = (item.as_object_mut(), extra) {
        map.extend(more);
    }
    item
}

fn bytes(components: Vec<Value>, rules: Vec<Value>, declarations: Option<Value>) -> Vec<u8> {
    let mut value = json!({"schema_version": "3.14.0", "components": components, "rules": rules});
    if let (Some(map), Some(declarations)) = (value.as_object_mut(), declarations) {
        map.insert("declarations".to_owned(), declarations);
    }
    serde_json::to_vec(&value).unwrap_or_default()
}

fn contract(components: Vec<Value>, rules: Vec<Value>) -> Contract {
    let parsed = parse(&bytes(components, rules, None)).ok();
    let complete = parsed.and_then(|parsed| match parsed {
        ParsedContract::Complete(contract) => Some(contract),
        ParsedContract::NeedsTree(_) => None,
    });
    complete.expect("a complete contract")
}

fn hygiene(bytes: Vec<u8>, documents: &Documents) -> super::Found {
    let usable = answer(ContractInput::root(bytes)).1;
    let missing = Reason::MissingInput(Input::Reply);
    check(
        documents,
        usable.as_ref(),
        Err(missing),
        "app",
        "architecture-contract.json",
    )
}

fn forbid(id: &str, source: &str, target: &str) -> Value {
    rule(
        id,
        "forbidden_dependency",
        json!({"source": source, "target": target, "include_type_checking": true,
                "allowed_sources": []}),
    )
}

fn allow(id: &str, source: &str, target: &str) -> Value {
    rule(
        id,
        "allowed_dependency",
        json!({"source": source, "target": target}),
    )
}

#[test]
fn a_clean_contract_adds_nothing() {
    let documents = Documents::of(&[("d.md", Some(PAGE))]);
    let rules = vec![rule("R", "complete_requires", json!({}))];
    let found = hygiene(bytes(vec![component("a", &[])], rules, None), &documents);
    assert!(
        found.refusal.is_none() && found.rules.is_empty(),
        "{found:?}"
    );
}

#[test]
fn an_unread_document_refuses_the_whole_contract() {
    let documents = Documents::of(&[("d.md", None)]);
    let found = hygiene(
        bytes(vec![component("a", &[])], Vec::new(), None),
        &documents,
    );
    let refusal = found.refusal.unwrap_or_default();
    assert!(
        refusal.contains("reference.provenance") && refusal.contains("d.md"),
        "{refusal}"
    );
}

#[test]
fn an_interface_rule_and_a_compat_declaration_name_their_families() {
    let documents = Documents::of(&[("d.md", Some(PAGE))]);
    let rules = vec![
        rule("R", "complete_requires", json!({})),
        rule("I", "interface_boundary", json!({})),
    ];
    let compat = json!({"compat": [{"module": "app.a.old", "target": "app.a.new",
                                    "lifetime": "migration"}]});
    let found = hygiene(
        bytes(vec![component("a", &[])], rules, Some(compat)),
        &documents,
    );
    let gaps: BTreeSet<&str> = found.rules.keys().map(String::as_str).collect();
    assert!(
        gaps.contains("hygiene:interface:architecture-contract.json"),
        "{gaps:?}"
    );
    assert!(
        gaps.contains("hygiene:compatibility:architecture-contract.json"),
        "{gaps:?}"
    );
    assert!(found
        .rules
        .values()
        .all(|reason| matches!(reason, Reason::Unsupported(Unsupported::Hygiene(_)))));
}

#[test]
fn whole_package_rules_decide_pairs_and_name_the_closed_world_defects() {
    let components = vec![component("a", &["b"]), component("b", &[])];
    let rules = vec![
        forbid("F1", "app.b", "app.a"),
        forbid("F2", "app.b", "app.a"),
        forbid("PART", "app.a.x", "app.b"),
        allow("A1", "app.b", "app.a"),
    ];
    let contract = contract(components, rules);
    let observed: BTreeSet<(String, String)> = [("b".to_owned(), "a".to_owned())].into();
    let found: Vec<String> = closed_world(&contract, &observed)
        .into_iter()
        .map(|(code, subject, _)| format!("{code} {subject}"))
        .collect();
    assert_eq!(
        found,
        [
            "decision.open 1 open dependency decision",
            "closed_world.observed_forbidden b -> a",
            "closed_world.duplicate b -> a",
            "decision.conflict b -> a",
        ]
    );
    let expected: BTreeSet<(String, String)> = [
        ("a".to_owned(), "b".to_owned()),
        ("b".to_owned(), "a".to_owned()),
    ]
    .into();
    assert_eq!(permitted(&contract), expected);
}

#[test]
fn complete_requires_leaves_no_pair_open() {
    let components = vec![component("a", &[]), component("b", &[])];
    let contract = contract(components, vec![rule("R", "complete_requires", json!({}))]);
    assert!(closed_world(&contract, &BTreeSet::new()).is_empty());
}
