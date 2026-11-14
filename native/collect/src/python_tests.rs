// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `scan` binds a Python reply to the snapshot before the model reads it (AD-450). Each
// planted difference between the reply and the files refuses the reply.

use std::fs;

use archkeel_facts::envelope::Reply;
use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::*;

/// The canonical root of a tree, as the composition requires it.
fn root(tree: &Tree) -> Root {
    let path = fs::canonicalize(&tree.root).unwrap();
    Root::of(path.to_str().unwrap()).unwrap()
}

fn reply(tree: &Tree) -> Reply {
    let request = json!({
        "protocol_version": "10.0.0",
        "snapshot": {"root": tree.path(), "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "app", "exclude_test_sources": false},
        "resolver": resolver(),
    });
    crate::run::reply_of(Profile::Python, request.to_string().as_bytes()).unwrap()
}

fn project() -> Tree {
    Tree::new(&[
        (
            "pyproject.toml",
            "[project]\nrequires-python = \">=3.11\"\n",
        ),
        ("src/app/__init__.py", ""),
        ("src/app/client.py", "import app.service\n"),
        ("src/app/service.py", "VALUE = 1\n"),
    ])
}

#[test]
fn the_request_names_the_grammar_and_only_names_standard_in_each_minor() {
    let resolver = resolver();
    assert_eq!(resolver["interpreter"]["version"], GRAMMAR);
    let names = resolver["interpreter"]["stdlib_module_names"]
        .as_array()
        .unwrap();
    assert!(names.contains(&json!("os")));
    assert!(!names.contains(&json!("distutils")));
    assert!(!names.contains(&json!("_interpreters")));
}

#[test]
fn a_reply_of_the_snapshot_is_bound_to_it() {
    let tree = project();
    let root = root(&tree);
    let reply = reply(&tree);
    assert!(reply.facts.inputs.len() >= 4, "{:?}", reply.facts.inputs);
    assert_eq!(bound(&root, &reply), Ok(()));
}

#[test]
fn a_planted_digest_or_a_changed_file_refuses_the_reply() {
    let tree = project();
    let root = root(&tree);
    let original = reply(&tree);

    let mut fake = original.clone();
    fake.facts.inputs[0].digest = "0".repeat(64);
    assert!(bound(&root, &fake)
        .unwrap_err()
        .contains("differs from its digest"));

    let mut fake = original.clone();
    fake.facts.source.source_digest = "0".repeat(64);
    assert!(bound(&root, &fake).unwrap_err().contains("source digest"));

    let mut fake = original.clone();
    fake.facts.inputs.pop();
    assert!(bound(&root, &fake).unwrap_err().contains("source digest"));

    fs::write(tree.root.join("src/app/service.py"), "VALUE = 2\n").unwrap();
    assert!(bound(&root, &original)
        .unwrap_err()
        .contains("differs from its digest"));
    fs::remove_file(tree.root.join("src/app/service.py")).unwrap();
    assert!(bound(&root, &original)
        .unwrap_err()
        .contains("cannot be read again"));
}
