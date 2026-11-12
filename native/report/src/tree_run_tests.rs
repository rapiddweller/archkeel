// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The report of a contract tree (AD-385): each rule row is checked against the model whose
//! contract holds its rule, and a run PASS needs the run proof of each model of the tree.

use archkeel_contract::policy::{assemble_tree, ContractTree};
use archkeel_contract::ParsedContract;
use archkeel_eval::{evaluate_tree, Outcome};
use archkeel_model::{Graph, ModelTree, Producer, RunGap, Settings};
use serde_json::{json, Value};

use crate::run_tests::{frame, read_json, reply, rows, text};
use crate::{build, BuildError, RuleDecision, RuleOutcome, Status};

const ORDER: &str = "shop.src.domain.order_x2e_ts";
const REPO: &str = "shop.src.domain.repository_x2e_ts";
const INDEX: &str = "shop.src.domain.index_x2e_ts";

fn component(id: &str, packages: &[&str]) -> Value {
    json!({"id": id, "label": id.to_lowercase(), "role": "component", "packages": packages,
        "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"]})
}

fn rule(id: &str, kind: &str, fields: Value) -> Value {
    let mut item = json!({"id": id, "kind": kind, "rationale": "r", "provenance": ["docs/a.md"],
                          "decided_by": "architect"});
    if let (Some(target), Some(source)) = (item.as_object_mut(), fields.as_object()) {
        target.extend(source.clone());
    }
    item
}

fn assign(id: &str, source: &str) -> Value {
    rule(id, "complete_assignment", json!({"source": source}))
}

/// The H-typescript contract with only `ASSIGNMENT`, and `domain` and `data` each mounting a
/// contract with the given rules.
fn tree(domain: Vec<Value>, data: Vec<Value>) -> Option<ContractTree> {
    let mut root = read_json("fixtures/H-typescript/architecture-contract.json");
    root["rules"] = json!([assign("ASSIGNMENT", "shop")]);
    for item in root["components"].as_array_mut()? {
        match item["label"].as_str() {
            Some("domain") => item["inside"] = json!("a.json"),
            Some("data") => item["inside"] = json!("b.json"),
            _ => {}
        }
    }
    let file = |components: Vec<Value>, rules: Vec<Value>| {
        json!({"schema_version": "2.3.0", "components": components, "rules": rules}).to_string()
    };
    let a = file(
        vec![
            component("ORDER", &[ORDER]),
            component("REPO", &[REPO]),
            component("INDEX", &[INDEX]),
        ],
        domain,
    );
    let b = file(vec![component("DATA", &["shop.src.data"])], data);
    let parsed = archkeel_contract::parse(root.to_string().as_bytes()).ok()?;
    let ParsedContract::NeedsTree(_) = &parsed else {
        return None;
    };
    let files = [
        ("a.json", "a.json", a.as_bytes()),
        ("b.json", "b.json", b.as_bytes()),
    ];
    assemble_tree("architecture-contract.json", parsed, &files).ok()
}

fn models(tree: &ContractTree) -> Option<ModelTree> {
    let reply = reply();
    let profile = reply.reply().facts.profile.as_str().to_owned();
    let settings =
        Settings::new("shop".to_owned(), profile, Vec::new()).with_producer(Producer::Trusted);
    ModelTree::tree(tree, Graph::derive(&reply, settings).ok()?).ok()
}

/// The models and the outcomes of a tree with these mount rules.
fn decided(domain: Vec<Value>, data: Vec<Value>) -> Option<(ModelTree, Vec<Outcome>)> {
    let models = models(&tree(domain, data)?)?;
    let outcomes = evaluate_tree(&models);
    Some((models, outcomes))
}

fn find<'a>(outcomes: &'a [Outcome], id: &str) -> Option<&'a Outcome> {
    outcomes.iter().find(|outcome| outcome.rule() == id)
}

#[test]
fn a_tree_whose_rules_pass_has_a_run_pass_that_covers_each_model() {
    let Some((models, outcomes)) = decided(
        vec![assign("SAME", "shop.src.domain")],
        vec![assign("SAME", "shop.src.data")],
    ) else {
        assert_eq!("the tree does not load", "loaded");
        return;
    };
    assert_eq!(models.mounts().len(), 2);
    let (outcome, records) = frame(rows(&outcomes));
    let report = build(outcome, records, Some(&models)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    let pass = report.source().pass().cloned();
    // The run proof of the root alone is not the run proof of the tree, nor that of one mount.
    assert!(pass.as_ref().is_some_and(|pass| !pass.of(models.root())));
    assert!(pass.is_some_and(|pass| models.mounts().iter().all(|mount| !pass.of(mount))));
}

/// The outcome rows with the row of `id` holding the decision of the rule `from`.
fn moved(outcomes: &[Outcome], id: &str, from: &str) -> Vec<RuleOutcome> {
    let decision = find(outcomes, from).and_then(Outcome::decision).cloned();
    let mut rules = rows(outcomes);
    if let (Some(index), Some(decision)) = (rules.iter().position(|r| r.id() == id), decision) {
        let kind = "complete_assignment".to_owned();
        let decided = RuleDecision::Decided(decision);
        rules[index] = RuleOutcome::of(id.to_owned(), kind, decided, None, text());
    }
    rules
}

#[test]
fn a_rule_row_with_the_pass_of_another_model_of_the_tree_is_refused() {
    let Some((models, outcomes)) = decided(
        vec![assign("SAME", "shop.src.domain")],
        vec![assign("SAME", "shop.src.data")],
    ) else {
        assert_eq!("the tree does not load", "loaded");
        return;
    };
    // A row of mount A with the PASS of mount B, of mount A with the PASS of the root, and of the
    // root with the PASS of a mount.
    for (id, from) in [
        ("domain:SAME", "data:SAME"),
        ("domain:SAME", "ASSIGNMENT"),
        ("ASSIGNMENT", "domain:SAME"),
    ] {
        let (outcome, records) = frame(moved(&outcomes, id, from));
        let wanted = BuildError::ForeignPass {
            rule: id.to_owned(),
        };
        assert_eq!(
            build(outcome, records, Some(&models)),
            Err(wanted),
            "{id} {from}"
        );
    }
}

#[test]
fn a_run_pass_needs_the_pass_of_each_rule_of_each_mount() {
    let Some((models, outcomes)) = decided(
        vec![assign("SAME", "shop.src.domain")],
        vec![assign("SAME", "shop.src.data")],
    ) else {
        assert_eq!("the tree does not load", "loaded");
        return;
    };
    // The rows of the root and of `domain` pass; the row of `data` is left out.
    let kept: Vec<Outcome> = outcomes
        .iter()
        .filter(|outcome| outcome.rule() != "data:SAME")
        .cloned()
        .collect();
    let (outcome, records) = frame(rows(&kept));
    let wanted = BuildError::PassWithoutProof(Some(RunGap::Rule("data:SAME".to_owned())));
    assert_eq!(build(outcome, records, Some(&models)), Err(wanted));
    // Without the models of the tree no row and no run can pass.
    let (outcome, records) = frame(rows(&outcomes));
    assert!(build(outcome, records, None).is_err());
}

#[test]
fn a_tree_with_a_named_mount_rule_never_gives_a_run_pass() {
    // An inside rule of a kind that no slice decides is named: an UNKNOWN row with its reason.
    let layers = rule("LO", "no_component_cycles", json!({}));
    let Some((models, outcomes)) = decided(vec![assign("A", "shop.src.domain"), layers], vec![])
    else {
        assert_eq!("the tree does not load", "loaded");
        return;
    };
    let (outcome, records) = frame(rows(&outcomes));
    let report = build(outcome, records, Some(&models)).unwrap();
    assert_eq!(report.source().status(), Status::Unknown);
    assert!(report.source().pass().is_none());
    let passes = outcomes.iter().filter_map(Outcome::decision);
    let gap = models.pass_run(passes.filter(|d| d.reason().is_none()));
    assert_eq!(gap, Err(RunGap::Rule("domain:LO".to_owned())));
}
