// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receipt guards of a mount (AD-480), read directly. Through the default CLI an earlier
//! guard fires first: a mount without a module fails the scan check of its parent before the
//! subject check, so each guard has its own test here on the frozen H-typescript reply.

use std::io::Read;

use archkeel_contract::policy::assemble_tree;
use archkeel_contract::ParsedContract;
use archkeel_facts::envelope::Reply;
use flate2::read::GzDecoder;
use serde_json::{json, Value};

use crate::reason::Reason;
use crate::{Graph, ModelTree, Producer, Settings};

const ROOT: &str = include_str!("../../../fixtures/H-typescript/architecture-contract.json");

fn component(id: &str, packages: &[&str], extra: Value) -> Value {
    let mut item = json!({"id": id, "label": id.to_lowercase(), "role": "component",
        "packages": packages, "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"]});
    if let (Some(target), Some(more)) = (item.as_object_mut(), extra.as_object()) {
        target.extend(more.clone());
    }
    item
}

/// The frozen reply with `change`, as the edits of `eval_tests.rs` make the store accept it.
fn reply(change: impl FnOnce(&mut Value)) -> Option<Reply> {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/golden/typescript/h-typescript.json.gz"
    );
    let mut text = String::new();
    GzDecoder::new(std::fs::File::open(path).ok()?)
        .read_to_string(&mut text)
        .ok()?;
    let mut value: Value = serde_json::from_str(&text).ok()?;
    let facts = &mut value["facts"];
    facts["adapter"]["version"] = json!("0");
    facts["adapter"]["code_digest"] = json!("0".repeat(64));
    facts["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": null,
        "requirement_state": "declared"});
    facts["source"]["git_head"] = json!("a");
    facts["source"]["dirty"] = json!(false);
    facts["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    change(&mut value);
    serde_json::from_value(value).ok()
}

/// The tree of the H-typescript contract with one mount on the component `label`.
fn tree(label: &str, extra_root: Option<Value>, inside: &Value) -> Option<ModelTree> {
    tree_of(label, extra_root, inside, |_| {})
}

fn tree_of(
    label: &str,
    extra_root: Option<Value>,
    inside: &Value,
    change: impl FnOnce(&mut Value),
) -> Option<ModelTree> {
    let mut root: Value = serde_json::from_str(ROOT).ok()?;
    let components = root["components"].as_array_mut()?;
    if let Some(extra) = extra_root {
        components.push(extra);
    }
    for item in components.iter_mut() {
        if item["label"] == label {
            item["inside"] = json!("inside.json");
        }
    }
    let parsed = archkeel_contract::parse(root.to_string().as_bytes()).ok()?;
    if !matches!(parsed, ParsedContract::NeedsTree(_)) {
        return None;
    }
    let bytes = inside.to_string().into_bytes();
    let files = [("inside.json", "inside.json", bytes.as_slice())];
    let assembled = assemble_tree("architecture-contract.json", parsed, &files).ok()?;
    ModelTree::tree(&assembled, graph(reply(change)?)?).ok()
}

fn graph(reply: Reply) -> Option<Graph> {
    let settings = Settings::new(
        "shop".to_owned(),
        reply.facts.profile.as_str().to_owned(),
        vec![],
    )
    .with_roots(vec!["src".to_owned()])
    .with_producer(Producer::Trusted);
    Graph::recorded(&reply.facts, settings).ok()
}

fn inside(components: Vec<Value>, version: &str) -> Value {
    let rule = json!({"id": "IN-REQ", "kind": "complete_requires", "rationale": "r",
        "provenance": ["docs/a.md"], "decided_by": "architect"});
    json!({"schema_version": version, "components": components, "rules": [rule]})
}

fn domain_components() -> Vec<Value> {
    vec![
        component("ORDER", &["shop.src.domain.order_x2e_ts"], json!({})),
        component("REPO", &["shop.src.domain.repository_x2e_ts"], json!({})),
        component("INDEX", &["shop.src.domain.index_x2e_ts"], json!({})),
    ]
}

#[test]
fn a_mount_without_a_module_has_no_subjects() {
    let ghost = component("GHOST", &["shop.src.ghost"], json!({}));
    let mounted = inside(
        vec![component("G", &["shop.src.ghost.x"], json!({}))],
        "2.3.0",
    );
    let found = tree("ghost", Some(ghost), &mounted);
    assert_eq!(found.as_ref().map(|tree| tree.mounts().len()), Some(1));
    for model in found.iter().flat_map(ModelTree::mounts) {
        assert_eq!(super::ownership(model), Err(Reason::NoSubjects));
    }
}

#[test]
fn a_mount_with_a_planned_component_has_no_ownership_receipt() {
    let mut components = domain_components();
    components.push(component("LATER", &[], json!({"lifecycle": "planned"})));
    let found = tree("domain", None, &inside(components, "2.4.0"));
    assert_eq!(found.as_ref().map(|tree| tree.mounts().len()), Some(1));
    for model in found.iter().flat_map(ModelTree::mounts) {
        let why = super::ownership(model)
            .err()
            .map(|reason| reason.to_string());
        assert!(why.is_some_and(|text| text.contains("planned component")));
    }
}

#[test]
fn a_mount_without_a_complete_inventory_has_no_requires_receipt() {
    // One selected file is read but not parsed: the inventory is not complete.
    let found = tree_of(
        "domain",
        None,
        &inside(domain_components(), "2.3.0"),
        |value| {
            value["facts"]["coverage"]["files_parsed"] = json!(6);
        },
    );
    assert_eq!(found.as_ref().map(|tree| tree.mounts().len()), Some(1));
    for model in found.iter().flat_map(ModelTree::mounts) {
        let why = model.scope(|scope| super::requires(model, scope.scan()));
        let text = why
            .err()
            .map(|reason| reason.to_string())
            .unwrap_or_default();
        assert!(
            text.contains("did not read and parse each selected file"),
            "{text}"
        );
    }
}
