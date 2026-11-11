// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One test for each check of the tree (AD-366). The parity test in `tests/` compares the whole
//! tree with Python; these tests fail when one check is removed.

use serde_json::{json, Value};

use crate::contract::parse;
use crate::document::ParsedContract;
use crate::error::ErrorKind;
use crate::policy::{assemble_tree, ContractTree, IssueKind, SourceProblem, TreeError, TreeIssue};

const ROOT: &str = "architecture-contract.json";

fn component(label: &str, inside: Option<&str>) -> Value {
    let mut item = json!({
        "id": format!("C-{label}"),
        "label": label,
        "role": "component",
        "packages": [format!("p.{label}")],
        "responsibilities": ["Own it."],
        "forbidden_responsibilities": [],
        "provenance": [format!("docs/{label}.md")],
    });
    if let (Some(path), Some(map)) = (inside, item.as_object_mut()) {
        map.insert("inside".to_owned(), json!(path));
    }
    item
}

fn contract(components: Vec<Value>) -> Value {
    json!({"schema_version": "3.14.0", "components": components, "rules": []})
}

fn bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap()
}

fn run(root: &Value, insides: &[(&str, Value)]) -> Result<ContractTree, TreeError> {
    let encoded: Vec<(&str, Vec<u8>)> = insides.iter().map(|(p, v)| (*p, bytes(v))).collect();
    let pairs: Vec<(&str, &str, &[u8])> = encoded
        .iter()
        .map(|(p, b)| (*p, *p, b.as_slice()))
        .collect();
    assemble_tree(ROOT, parse(&bytes(root)).unwrap(), &pairs)
}

fn issues(result: Result<ContractTree, TreeError>) -> Vec<TreeIssue> {
    let error = result.err();
    let found = match error.clone() {
        Some(TreeError::Issues(issues)) => Some(issues),
        _ => None,
    };
    assert!(found.is_some(), "expected issues, got {error:?}");
    found.unwrap()
}

fn kinds(result: Result<ContractTree, TreeError>) -> Vec<IssueKind> {
    issues(result).iter().map(|i| *i.kind()).collect()
}

fn one_mount(path: &str) -> Value {
    contract(vec![component("a", Some(path))])
}

fn leaf(label: &str) -> Value {
    let mut leaf = contract(vec![component(label, None)]);
    leaf["rules"] = json!([{
        "id": format!("R-{label}"),
        "kind": "complete_requires",
        "rationale": "Every import is declared.",
        "provenance": ["docs/rule.md"],
        "decided_by": "architect",
    }]);
    leaf
}

#[test]
fn a_tree_scopes_the_ids_of_a_mount_and_binds_both_digests() {
    let tree = run(&one_mount("a/inside.json"), &[("a/inside.json", leaf("x"))]).unwrap();
    let mount = &tree.mounts()[0];
    assert_eq!(mount.parent_id(), "a");
    assert_eq!(mount.pointer(), "/components/0/inside");
    assert_eq!(mount.contract().components()[0].id().as_text(), "a:C-x");
    assert_eq!(
        crate::head_of(&tree.comparison().rules()[0]).id().as_text(),
        "a:R-x"
    );
    assert_eq!(tree.comparison().components().len(), 2);
    assert_ne!(tree.comparison_digest(), tree.digest());
    assert!(tree.paths().contains(&"docs/x.md".to_owned()));
}

#[test]
fn a_tree_without_mounts_has_the_digests_of_its_root() {
    let tree = run(&leaf("a"), &[]).unwrap();
    assert_eq!(tree.digest(), tree.root().digest());
    assert_eq!(
        tree.comparison_digest(),
        &crate::canonical_digest(tree.root())
    );
}

#[test]
fn an_unsafe_reference_is_an_issue() {
    for path in ["a/../b.json", "/b.json", "b\\c.json", "b:c.json", "./", "."] {
        let insides = [("b.json", leaf("x"))];
        let found = kinds(run(&one_mount(path), &insides));
        assert_eq!(found, vec![IssueKind::UnsafePath], "{path}");
    }
}

#[test]
fn a_reference_without_bytes_is_missing() {
    assert_eq!(
        kinds(run(&one_mount("a.json"), &[])),
        vec![IssueKind::Missing]
    );
}

#[test]
fn a_reference_to_the_root_or_above_is_a_cycle() {
    assert_eq!(kinds(run(&one_mount(ROOT), &[])), vec![IssueKind::Cycle]);
    let insides = [("a.json", one_mount("a.json"))];
    assert_eq!(
        kinds(run(&one_mount("a.json"), &insides)),
        vec![IssueKind::Cycle]
    );
}

#[test]
fn a_second_reference_to_one_path_is_a_duplicate_mount() {
    let root = contract(vec![
        component("a", Some("a.json")),
        component("b", Some("./a.json")),
    ]);
    let found = kinds(run(&root, &[("a.json", leaf("x"))]));
    assert_eq!(found, vec![IssueKind::DuplicateMount]);
}

#[test]
fn an_invalid_inside_contract_is_an_issue_with_its_parse_kind() {
    let found = kinds(run(&one_mount("a.json"), &[("a.json", json!([]))]));
    assert_eq!(found, vec![IssueKind::Contract(ErrorKind::Invalid)]);
}

#[test]
fn root_only_declarations_in_an_inside_are_an_issue() {
    let mut inside = leaf("x");
    inside["declarations"] =
        json!({"context_roots": ["src"], "context_roots_provenance": ["d.md"]});
    let issues = issues(run(&one_mount("a.json"), &[("a.json", inside)]));
    assert_eq!(*issues[0].kind(), IssueKind::UnsupportedDeclarations);
    let reason = "unsupported non-empty declarations: context_roots, context_roots_provenance";
    assert_eq!(issues[0].reason(), reason);
}

#[test]
fn a_scoped_id_that_the_tree_holds_is_a_collision() {
    let mut root = one_mount("a.json");
    root["components"][0]["id"] = json!("a:C-x");
    let found = kinds(run(&root, &[("a.json", leaf("x"))]));
    assert_eq!(found, vec![IssueKind::DeclarationIdCollision]);
}

#[test]
fn a_nested_parent_key_that_is_a_root_label_is_a_collision() {
    let root = contract(vec![component("a", Some("a.json")), component("a:x", None)]);
    let insides = [
        ("a.json", contract(vec![component("x", Some("b.json"))])),
        ("b.json", leaf("y")),
    ];
    assert_eq!(
        kinds(run(&root, &insides)),
        vec![IssueKind::ParentIdCollision]
    );
}

#[test]
fn one_parent_key_at_two_places_is_a_collision() {
    // `a` + `x:y` and `a:x` + `y` give one key, `a:x:y`.
    let inner = contract(vec![
        component("x", Some("x.json")),
        component("x:y", Some("c.json")),
    ]);
    let insides = [
        ("a.json", inner),
        ("x.json", contract(vec![component("y", Some("d.json"))])),
        ("c.json", leaf("q")),
        ("d.json", leaf("r")),
    ];
    let issues = issues(run(&one_mount("a.json"), &insides));
    assert_eq!(issues.len(), 1);
    assert_eq!(*issues[0].kind(), IssueKind::ParentIdCollision);
    assert_eq!(
        issues[0].pointer(),
        "/components/0/inside/components/1/inside"
    );
}

#[test]
fn one_module_target_in_two_contracts_is_an_issue() {
    let module = json!({"modules": [{"path": "src/a.py", "responsibility": "Own a."}]});
    let mut root = one_mount("a.json");
    root["declarations"] = module.clone();
    let mut inside = leaf("x");
    inside["declarations"] = module;
    let issues = issues(run(&root, &[("a.json", inside)]));
    assert_eq!(*issues[0].kind(), IssueKind::DuplicateModuleTarget);
    let reason = "duplicate module target path 'src/a.py' in 'a.json'; already declared in \
                  'architecture-contract.json'";
    assert_eq!(issues[0].reason(), reason);
}

#[test]
fn bytes_that_no_mount_reads_are_rejected() {
    let result = run(&leaf("a"), &[("b.json", leaf("x"))]);
    let expected = TreeError::Source(SourceProblem::Unmounted, vec!["b.json".to_owned()]);
    assert_eq!(result.unwrap_err(), expected);
}

#[test]
fn two_inputs_with_one_path_are_rejected() {
    let result = run(
        &one_mount("a.json"),
        &[("a.json", leaf("x")), ("./a.json", leaf("x"))],
    );
    let expected = TreeError::Source(SourceProblem::Duplicate, vec!["a.json".to_owned()]);
    assert_eq!(result.unwrap_err(), expected);
    let result = run(&leaf("a"), &[("../a.json", leaf("x"))]);
    let expected = TreeError::Source(SourceProblem::Unsafe, vec!["../a.json".to_owned()]);
    assert_eq!(result.unwrap_err(), expected);
}

#[test]
fn an_unsafe_root_path_gives_no_tree() {
    let root = parse(&bytes(&leaf("a"))).unwrap();
    let result = assemble_tree("../a.json", root, &[]);
    assert_eq!(result.unwrap_err(), TreeError::UnsafeRootPath);
}

#[test]
fn a_root_without_mounts_is_a_tree_with_its_digests() {
    let parsed = parse(&bytes(&leaf("a"))).unwrap();
    assert!(matches!(parsed, ParsedContract::Complete(_)));
    let tree = assemble_tree(ROOT, parsed, &[]).unwrap();
    assert!(tree.mounts().is_empty());
}

#[test]
fn a_root_with_mounts_needs_the_tree() {
    let parsed = parse(&bytes(&one_mount("a.json"))).unwrap();
    let mounts: Vec<&str> = match &parsed {
        ParsedContract::NeedsTree(needs) => {
            needs.mounts().iter().map(|m| m.path().as_text()).collect()
        }
        ParsedContract::Complete(_) => Vec::new(),
    };
    assert_eq!(mounts, ["a.json"]);
    let tree = assemble_tree(ROOT, parsed, &[("a.json", "a.json", &bytes(&leaf("x")))]).unwrap();
    assert_eq!(tree.mounts()[0].identity(), "a.json");
}
