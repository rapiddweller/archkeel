// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Recorded construct facts against the Python matching oracle. Only the Python test starts this.

use std::collections::BTreeSet;

use archkeel_contract::{ParsedContract, Rule};
use archkeel_facts::envelope::Facts;
use serde_json::Value;

use crate::{Graph, Model, ModelTree, Producer, Settings};

#[test]
#[ignore = "the Python test supplies the frozen facts and reference rows"]
fn replay_frozen_construct_matching() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::var("ARCHKEEL_CONSTRUCT_REPLAY")?;
    let cases: Vec<Value> = serde_json::from_slice(&std::fs::read(path)?)?;
    let mut count = 0;
    for case in cases {
        let contract = match archkeel_contract::parse(case["contract"].to_string().as_bytes())? {
            ParsedContract::Complete(c) => c,
            _ => return Err("partial replay contract".into()),
        };
        let facts: Facts = serde_json::from_value(case["facts"].clone())?;
        let namespace = case["namespace"].as_str().ok_or("no namespace")?;
        let settings = Settings::new(
            namespace.to_owned(),
            facts.profile.as_str().to_owned(),
            vec![],
        )
        .with_producer(Producer::Trusted);
        let graph = Graph::recorded(&facts, settings).map_err(|r| r.to_string())?;
        let model = Model::of(&contract, graph).map_err(|r| r.1.to_string())?;
        let rule = contract.rules().first().ok_or("no replay rule")?;
        let Rule::ForbiddenConstruct(rule) = rule else {
            return Err("wrong rule".into());
        };
        let matches = model
            .graph()
            .constructs()
            .matches(&model, rule)
            .map_err(|r| r.to_string())?;
        let actual: BTreeSet<&str> = matches
            .iter()
            .filter(|m| m.known)
            .map(|m| m.site.id.as_str())
            .collect();
        let expected: BTreeSet<&str> = case["expected"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|r| r["evidence_class"] == "VIOLATION")
            .flat_map(|r| r["fact_ids"].as_array().into_iter().flatten())
            .filter_map(Value::as_str)
            .collect();
        assert_eq!(actual, expected, "{}", case["name"]);
        count += 1;
    }
    assert!(count >= 16, "the replay must cover each construct");
    println!("frozen construct matching: {count} cases equal Python");
    Ok(())
}

#[test]
#[ignore = "the bounded corpus measurement supplies original replies and Python verdicts"]
fn replay_corpus_construct_verdicts() -> Result<(), Box<dyn std::error::Error>> {
    use std::io::BufReader;
    let path = std::env::var("ARCHKEEL_CONSTRUCT_CORPUS")?;
    let input = BufReader::new(std::fs::File::open(path)?);
    let stream = serde_json::Deserializer::from_reader(input).into_iter::<Value>();
    let mut counts = std::collections::BTreeMap::<String, usize>::new();
    for case in stream {
        corpus_case(case?, &mut counts)?;
    }
    println!(
        "construct corpus verdicts: {}",
        serde_json::to_string(&counts)?
    );
    assert!(counts.values().sum::<usize>() >= 1_400);
    Ok(())
}

fn corpus_case(
    case: Value,
    counts: &mut std::collections::BTreeMap<String, usize>,
) -> Result<(), Box<dyn std::error::Error>> {
    let expected_rules = case["expected_rules"]
        .as_object()
        .ok_or("no expected rules")?;
    let models = corpus_model(&case);
    let models = match models {
        Ok(model) => model,
        Err(error) => {
            *counts.entry(format!("unproved: {error}")).or_default() += expected_rules.len();
            println!("unproved {}: {error}", case["name"]);
            return Ok(());
        }
    };
    let mut proved = 0;
    for model in models.models() {
        for rule in model.contract().rules() {
            let Rule::ForbiddenConstruct(construct) = rule else {
                continue;
            };
            let id = construct.head().id().as_text();
            let Some(expected) = expected_rules.get(id).and_then(Value::as_str) else {
                continue;
            };
            let matches = model
                .graph()
                .constructs()
                .matches(model, construct)
                .map_err(|r| r.to_string())?;
            let actual: BTreeSet<&str> = matches
                .iter()
                .filter(|m| m.known)
                .map(|m| m.site.id.as_str())
                .collect();
            let expected_facts: BTreeSet<&str> = case["expected_rows"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|r| {
                    r["rule_ids"]
                        .as_array()
                        .is_some_and(|ids| ids.iter().any(|r| r == id))
                })
                .flat_map(|r| r["fact_ids"].as_array().into_iter().flatten())
                .filter_map(Value::as_str)
                .collect();
            assert_eq!(actual, expected_facts, "{} {id}", case["name"]);
            let (verdict, reason) = if !actual.is_empty() {
                ("FAIL", None)
            } else {
                absence(model, rule, id)
            };
            assert!(
                verdict == expected || (verdict == "UNKNOWN" && expected == "PASS"),
                "{} {id}: {expected}/{verdict} {reason:?}",
                case["name"]
            );
            let key = if verdict == expected {
                format!("{expected}/{verdict}")
            } else {
                format!(
                    "{expected}/{verdict}: {}",
                    reason.ok_or("stricter verdict without reason")?
                )
            };
            *counts.entry(key).or_default() += 1;
            proved += 1;
        }
    }
    *counts
        .entry("unproved: mounted rule".to_owned())
        .or_default() += expected_rules.len().saturating_sub(proved);
    Ok(())
}

fn absence(model: &Model, rule: &Rule, id: &str) -> (&'static str, Option<String>) {
    model.scope(|scope| match scope.complete(rule) {
        Ok(proof) => {
            let decision = scope.pass(proof);
            assert!(decision.passes(model, id));
            ("PASS", None)
        }
        Err(reason) => ("UNKNOWN", Some(reason.to_string())),
    })
}

fn corpus_model(case: &Value) -> Result<ModelTree, String> {
    let contract = archkeel_contract::parse(case["contract"].to_string().as_bytes())
        .map_err(|e| e.to_string())?;
    let insides: Vec<(&str, &str, &[u8])> = case["insides"]
        .as_object()
        .into_iter()
        .flatten()
        .filter_map(|(path, text)| {
            text.as_str()
                .map(|text| (path.as_str(), path.as_str(), text.as_bytes()))
        })
        .collect();
    let root = case["contract_path"].as_str().ok_or("no root path")?;
    let tree = archkeel_contract::policy::assemble_tree(root, contract, &insides)
        .map_err(|e| e.to_string())?;
    let facts: Facts = serde_json::from_value(case["facts"].clone()).map_err(|e| e.to_string())?;
    let namespace = case["namespace"].as_str().ok_or("no namespace")?;
    let settings = Settings::new(
        namespace.to_owned(),
        facts.profile.as_str().to_owned(),
        vec![],
    )
    .with_producer(Producer::Trusted);
    let graph = Graph::recorded(&facts, settings).map_err(|e| e.to_string())?;
    ModelTree::tree(&tree, graph).map_err(|e| e.1.to_string())
}
