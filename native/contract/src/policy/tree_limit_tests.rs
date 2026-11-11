// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The limits of the tree (review of #1047): the depth bound, a symbolic link, the serialized
//! issue kind and the paths that the shell must still send.

use serde_json::{json, Value};

use crate::contract::parse;
use crate::policy::{assemble_tree, ContractTree, IssueKind, SourceProblem, TreeError, MAX_DEPTH};

const ROOT: &str = "architecture-contract.json";

fn mounting(path: Option<&str>) -> Value {
    let mut item = json!({
        "id": "C-c", "label": "c", "role": "component", "packages": ["p.c"],
        "responsibilities": ["Own c."], "forbidden_responsibilities": [], "provenance": ["d.md"],
    });
    if let (Some(path), Some(map)) = (path, item.as_object_mut()) {
        map.insert("inside".to_owned(), json!(path));
    }
    json!({"schema_version": "3.14.0", "components": [item], "rules": []})
}

fn bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap()
}

/// Assemble a root from `(reference, identity, contract)` inputs.
fn run(root: &Value, insides: &[(&str, &str, Value)]) -> Result<ContractTree, TreeError> {
    let encoded: Vec<(&str, &str, Vec<u8>)> =
        insides.iter().map(|(p, i, v)| (*p, *i, bytes(v))).collect();
    let pairs: Vec<(&str, &str, &[u8])> = encoded
        .iter()
        .map(|(p, i, b)| (*p, *i, b.as_slice()))
        .collect();
    assemble_tree(ROOT, parse(&bytes(root)).unwrap(), &pairs)
}

/// A chain of `depth` mounts: the root mounts d/0.json, each file mounts the next one.
fn chain(depth: usize) -> Result<ContractTree, TreeError> {
    let names: Vec<String> = (0..depth).map(|level| format!("d/{level}.json")).collect();
    let files: Vec<Vec<u8>> = (0..depth)
        .map(|level| bytes(&mounting(names.get(level + 1).map(String::as_str))))
        .collect();
    let pairs: Vec<(&str, &str, &[u8])> = names
        .iter()
        .zip(&files)
        .map(|(name, file)| (name.as_str(), name.as_str(), file.as_slice()))
        .collect();
    assemble_tree(
        ROOT,
        parse(&bytes(&mounting(Some("d/0.json")))).unwrap(),
        &pairs,
    )
}

fn kinds(result: Result<ContractTree, TreeError>) -> Vec<IssueKind> {
    match result {
        Err(TreeError::Issues(issues)) => issues.iter().map(|i| *i.kind()).collect(),
        _ => Vec::new(),
    }
}

#[test]
fn a_chain_at_the_depth_bound_is_a_tree() {
    assert_eq!(MAX_DEPTH, 900);
    let tree = chain(MAX_DEPTH).unwrap();
    assert_eq!(tree.mounts().len(), MAX_DEPTH);
}

#[test]
fn a_chain_one_level_deeper_is_too_deep() {
    assert_eq!(kinds(chain(MAX_DEPTH + 1)), vec![IssueKind::TooDeep]);
}

#[test]
fn a_very_deep_chain_is_too_deep_without_an_abort() {
    assert_eq!(kinds(chain(20_000)), vec![IssueKind::TooDeep]);
}

#[test]
fn a_link_to_a_mounted_file_is_refused() {
    let root = json!({"schema_version": "3.14.0", "rules": [], "components": [
        mounting(Some("a.json"))["components"][0].clone(),
        {"id": "C-d", "label": "d", "role": "component", "packages": ["p.d"],
         "responsibilities": ["Own d."], "forbidden_responsibilities": [], "provenance": ["d.md"],
         "inside": "alias.json"},
    ]});
    let insides = [
        ("a.json", "a.json", mounting(None)),
        ("alias.json", "a.json", mounting(None)),
    ];
    assert_eq!(kinds(run(&root, &insides)), vec![IssueKind::Linked]);
}

#[test]
fn a_link_to_an_unmounted_file_is_refused() {
    let insides = [("a.json", "b.json", mounting(None))];
    assert_eq!(
        kinds(run(&mounting(Some("a.json")), &insides)),
        vec![IssueKind::Linked]
    );
}

#[test]
fn a_link_out_of_the_repository_is_refused() {
    let insides = [("a.json", "../outside.json", mounting(None))];
    let result = run(&mounting(Some("a.json")), &insides);
    let expected = TreeError::Source(SourceProblem::Unsafe, vec!["../outside.json".to_owned()]);
    assert_eq!(result.unwrap_err(), expected);
}

#[test]
fn an_issue_kind_has_a_stable_serialized_name() {
    let issues = match run(&mounting(Some("a.json")), &[]) {
        Err(TreeError::Issues(issues)) => issues,
        _ => Vec::new(),
    };
    assert_eq!(issues.len(), 1);
    let value = serde_json::to_value(&issues[0]).unwrap();
    assert_eq!(value["kind"], json!("missing"));
    assert_eq!(IssueKind::TooDeep.word(), "too_deep");
    assert_eq!(
        IssueKind::Contract(crate::error::ErrorKind::Version).word(),
        "contract_version"
    );
}

#[test]
fn the_paths_still_needed_are_given_only_when_each_issue_is_missing() {
    let root = json!({"schema_version": "3.14.0", "rules": [], "components": [
        mounting(Some("./a.json"))["components"][0].clone(),
        {"id": "C-d", "label": "d", "role": "component", "packages": ["p.d"],
         "responsibilities": ["Own d."], "forbidden_responsibilities": [], "provenance": ["d.md"],
         "inside": "b.json"},
    ]});
    let missing = run(&root, &[]).unwrap_err();
    assert_eq!(
        missing.missing_paths(),
        Some(vec!["a.json".to_owned(), "b.json".to_owned()])
    );
    let other = run(&root, &[("a.json", "a.json", json!([]))]).unwrap_err();
    assert_eq!(other.missing_paths(), None);
}
