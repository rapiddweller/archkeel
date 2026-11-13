// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules of an inside-contract tree over the frozen H-typescript reply (AD-385).
//!
//! The domain of the component `domain` holds `index`, `order` and `repository`; the modules of
//! `data` import `repository` too. A rule of a mount must read only the imports and the modules
//! of its domain, the owners of its clipped contract, and the proof of its own model.

use archkeel_contract::policy::{assemble_tree, ContractTree};
use archkeel_contract::ParsedContract;
use archkeel_model::{Cause, Graph, ModelTree, Reason, Verdict};
use serde_json::{json, Value};

use crate::tests::{reply, shop_settings};
use crate::{evaluate_tree, Outcome, Violation};

pub(crate) const D: &str = "shop.src.domain";
pub(crate) const ORDER: &str = "shop.src.domain.order_x2e_ts";
pub(crate) const REPO: &str = "shop.src.domain.repository_x2e_ts";
pub(crate) const INDEX: &str = "shop.src.domain.index_x2e_ts";
const ROOT: &str = include_str!("../../../fixtures/H-typescript/architecture-contract.json");

pub(crate) fn component(id: &str, packages: &[&str], inside: Option<&str>) -> Value {
    let mut item = json!({"id": id, "label": id.to_lowercase(), "role": "component",
        "packages": packages, "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"]});
    if let Some(path) = inside {
        item["inside"] = json!(path);
    }
    item
}

pub(crate) fn rule(id: &str, kind: &str, fields: Value) -> Value {
    let mut item = json!({"id": id, "kind": kind, "rationale": "r", "provenance": ["docs/a.md"],
                          "decided_by": "architect"});
    if let (Some(target), Some(source)) = (item.as_object_mut(), fields.as_object()) {
        target.extend(source.clone());
    }
    item
}

pub(crate) fn inside(components: Vec<Value>, rules: Vec<Value>) -> Value {
    json!({"schema_version": "2.3.0", "components": components, "rules": rules})
}

/// The three components of the domain: each owns one module.
pub(crate) fn three() -> Vec<Value> {
    vec![
        component("ORDER", &[ORDER], None),
        component("REPO", &[REPO], None),
        component("INDEX", &[INDEX], None),
    ]
}

/// The fixture contract with each `(label, path)` mounted, assembled with the files.
pub(crate) fn tree(mounts: &[(&str, &str)], files: &[(&str, Value)]) -> Option<ContractTree> {
    let mut root: Value = serde_json::from_str(ROOT).ok()?;
    for item in root["components"].as_array_mut()? {
        if let Some((_, path)) = mounts.iter().find(|(label, _)| item["label"] == *label) {
            item["inside"] = json!(path);
        }
    }
    let parsed = archkeel_contract::parse(root.to_string().as_bytes());
    assert!(parsed.is_ok(), "{parsed:?}");
    let parsed = parsed.ok()?;
    let bytes: Vec<(String, Vec<u8>)> = files
        .iter()
        .map(|(path, value)| ((*path).to_owned(), value.to_string().into_bytes()))
        .collect();
    let inputs: Vec<(&str, &str, &[u8])> = bytes
        .iter()
        .map(|(path, value)| (path.as_str(), path.as_str(), value.as_slice()))
        .collect();
    match parsed {
        ParsedContract::NeedsTree(_) => {
            let assembled = assemble_tree("architecture-contract.json", parsed, &inputs);
            assert!(assembled.is_ok(), "{assembled:?}");
            assembled.ok()
        }
        ParsedContract::Complete(_) => None,
    }
}

/// The models of the tree over the reply after `change`.
pub(crate) fn models(tree: &ContractTree, change: impl FnOnce(&mut Value)) -> Option<ModelTree> {
    let graph = Graph::derive(&reply(change)?, shop_settings()).ok()?;
    let made = ModelTree::tree(tree, graph);
    assert!(made.is_ok(), "{:?}", made.as_ref().err().map(|e| &e.1));
    made.ok()
}

/// The outcomes of a domain mount with these rules and components, over the plain reply.
pub(crate) fn domain(components: Vec<Value>, rules: Vec<Value>) -> Vec<Outcome> {
    let file = inside(components, rules);
    tree(&[("domain", "a.json")], &[("a.json", file)])
        .and_then(|tree| models(&tree, |_| {}))
        .map(|models| evaluate_tree(&models))
        .unwrap_or_default()
}

pub(crate) fn find<'a>(outcomes: &'a [Outcome], rule: &str) -> Option<&'a Outcome> {
    outcomes.iter().find(|outcome| outcome.rule() == rule)
}

/// The verdict word and the reason of a rule.
pub(crate) fn verdict(outcomes: &[Outcome], rule: &str) -> (String, Option<Reason>) {
    let decision = find(outcomes, rule).and_then(Outcome::decision);
    let word = decision.map_or("NONE", |d| match d.verdict() {
        Verdict::Pass(_) => "PASS",
        Verdict::Fail => "FAIL",
        Verdict::Unknown => "UNKNOWN",
    });
    (word.to_owned(), decision.and_then(|d| d.reason().cloned()))
}

/// The import or module that each violation of a rule cites.
pub(crate) fn rows(outcomes: &[Outcome], rule: &str) -> Vec<String> {
    let cite = |violation: &Violation| match violation {
        Violation::Unassigned { name, .. } => name.clone(),
        Violation::NotAllowedChild { child, .. } => child.clone(),
        Violation::OutsideScope { cited, .. }
        | Violation::Undeclared { cited, .. }
        | Violation::Forbidden { cited, .. }
        | Violation::Peer { cited, .. }
        | Violation::Unrequired { cited, .. }
        | Violation::PrivateImport { cited, .. } => {
            format!(
                "{} -> {}",
                short(&cited.source_module),
                short(&cited.target_module)
            )
        }
        Violation::OuterLayer(layered) => layered.id.clone(),
        Violation::Cycle(..) => "cycle".to_owned(),
        Violation::Construct(row) => row.owner.clone(),
    };
    find(outcomes, rule).map_or_else(Vec::new, |o| o.violations().iter().map(cite).collect())
}

/// The last segment of a module name without its suffix (`index`).
pub(crate) fn short(name: &str) -> String {
    let last = name.rsplit('.').next().unwrap_or(name);
    last.trim_end_matches("_x2e_ts").to_owned()
}

pub(crate) fn not_complete(cause: Cause) -> Reason {
    Reason::NotComplete(cause)
}

#[test]
fn a_forbidden_rule_of_a_mount_reads_only_the_imports_of_its_domain() {
    let forbid = rule(
        "F",
        "forbidden_dependency",
        json!({"source": "shop.src", "target": REPO,
        "include_type_checking": true, "allowed_sources": []}),
    );
    let found = domain(three(), vec![forbid]);
    // `data.local` and `data.remote` import the repository too, outside the domain.
    assert_eq!(rows(&found, "domain:F"), ["index -> repository"]);
    assert_eq!(verdict(&found, "domain:F").0, "FAIL");
}

#[test]
fn a_sibling_rule_of_a_mount_reads_only_the_imports_of_its_domain() {
    let peers = rule(
        "P",
        "sibling_isolation",
        json!({"members": [ORDER, REPO, "shop.src.data"],
        "include_type_checking": true}),
    );
    let found = domain(three(), vec![peers]);
    assert_eq!(rows(&found, "domain:P"), ["repository -> order"]);
}

#[test]
fn complete_requires_of_a_mount_reads_its_domain_and_its_clipped_owners() {
    let requires = rule(
        "R",
        "complete_requires",
        json!({"include_type_checking": true}),
    );
    let found = domain(three(), vec![requires]);
    let mut got = rows(&found, "domain:R");
    got.sort();
    assert_eq!(
        got,
        [
            "index -> order",
            "index -> repository",
            "repository -> order"
        ]
    );
}

/// The reply with the first import from `source` turned into an import of an external package.
fn external_from(source: &'static str) -> impl FnOnce(&mut Value) {
    move |value: &mut Value| {
        let sections = value["facts"]["sections"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        let id = sections
            .iter()
            .filter(|section| section["name"] == "imports")
            .flat_map(|section| section["records"].as_array().cloned().unwrap_or_default())
            .find(|record| record["data"]["source_module"] == source)
            .map(|record| record["id"].clone());
        let imports = value["facts"]["imports"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        let index = imports
            .iter()
            .position(|item| Some(&item["import_id"]) == id.as_ref());
        assert!(index.is_some(), "an import from {source}");
        if let Some(index) = index {
            crate::external_tests::external(index, "@vendor/x")(value);
        }
    }
}

#[test]
fn the_external_rules_of_a_mount_read_only_the_imports_of_its_domain() {
    let scope = rule(
        "E",
        "external_dependency_scope",
        json!({"dependency": REPO, "allowed_sources": [ORDER]}),
    );
    let complete = rule("C", "complete_external_scope", json!({"source": "shop"}));
    let found = domain(three(), vec![scope.clone(), complete.clone()]);
    assert_eq!(rows(&found, "domain:E"), ["index -> repository"]);
    assert_eq!(verdict(&found, "domain:C").0, "PASS");
    // An undeclared external import of `data` fails the root rule, not the rule of the mount.
    let file = inside(three(), vec![scope, complete]);
    let found = tree(&[("domain", "a.json")], &[("a.json", file)])
        .and_then(|tree| models(&tree, external_from("shop.src.data.local_x2e_ts")))
        .map(|models| evaluate_tree(&models))
        .unwrap_or_default();
    assert_eq!(rows(&found, "EXTERNAL-COMPLETE"), ["local -> entry"]);
    assert_eq!(verdict(&found, "domain:C").0, "PASS");
}

#[test]
fn root_layout_of_a_mount_reads_the_packages_below_its_parent_and_its_modules() {
    let layout = rule(
        "L",
        "root_layout",
        json!({"root": "shop.src", "allowed_children": [D]}),
    );
    let found = domain(three(), vec![layout]);
    assert_eq!(verdict(&found, "domain:L").0, "PASS");
    assert!(rows(&found, "domain:L").is_empty());
    let narrow = rule(
        "L",
        "root_layout",
        json!({"root": D, "allowed_children": [ORDER]}),
    );
    let found = domain(three(), vec![narrow]);
    let mut got = rows(&found, "domain:L");
    got.sort();
    assert_eq!(got, [INDEX, REPO]);
}

#[test]
fn complete_assignment_of_a_mount_reads_its_domain_and_its_clipped_owners() {
    let assign = rule("A", "complete_assignment", json!({"source": "shop"}));
    let found = domain(vec![component("ORDER", &[ORDER], None)], vec![assign]);
    let mut got = rows(&found, "domain:A");
    got.sort();
    assert_eq!(got, [INDEX, REPO]);
    assert_eq!(verdict(&found, "ASSIGNMENT").0, "PASS");
}
