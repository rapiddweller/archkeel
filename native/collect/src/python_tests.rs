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
        (
            "src/app/client.py",
            "import app.service\nimport requests\nimport os\n",
        ),
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

/// The store refusal of a changed copy of a real survey, or an empty text.
fn refusal(reply: Reply) -> String {
    archkeel_store::ingest_typed(reply)
        .err()
        .unwrap_or_default()
}

#[test]
fn the_store_accepts_a_complete_survey_and_refuses_each_planted_claim() {
    use archkeel_facts::envelope::{LimitSupport, ProtocolVersion, Target};
    use archkeel_facts::ids::PackageName;

    let tree = project();
    let original = reply(&tree);
    assert!(
        original.facts.coverage.full_scope,
        "{:?}",
        original.facts.coverage
    );
    assert_eq!(refusal(original.clone()), "");
    let limits = original.facts.profile_limits.unwrap();
    assert_eq!(limits.dependency_symbols, LimitSupport::Unsupported);
    assert_eq!(limits.interface_boundary, LimitSupport::Unsupported);

    type Change = fn(&mut Reply);
    let cases: [(&str, Change); 8] = [
        ("only the Python import survey", |r| {
            r.facts.profile = Profile::TypeScript
        }),
        ("10.0.0 import survey", |r| {
            r.protocol_version = ProtocolVersion::V9
        }),
        ("resolution feature", |r| {
            r.facts
                .capabilities
                .resolution_features
                .push("static-imports".to_owned());
        }),
        ("no symbol or interface rule", |r| {
            if let Some(limits) = r.facts.profile_limits.as_mut() {
                limits.interface_boundary = LimitSupport::Supported;
            }
        }),
        ("external target", |r| {
            let local = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::Local { .. }));
            if let Some(target) = local {
                *target = Target::External {
                    import_id: target.import_id().clone(),
                    package: PackageName::new("app"),
                };
            }
        }),
        ("a builtin target must be standard", |r| {
            let found = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::External { .. }));
            if let Some(target) = found {
                *target = Target::Builtin {
                    import_id: target.import_id().clone(),
                    name: "requests".to_owned(),
                };
            }
        }),
        ("an external target must be a package", |r| {
            let found = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::Builtin { .. }));
            if let Some(target) = found {
                *target = Target::External {
                    import_id: target.import_id().clone(),
                    package: PackageName::new("os"),
                };
            }
        }),
        ("a Python import has no specifier", |r| {
            if let Some(archkeel_facts::Section::Imports(records)) = r.facts.sections.first_mut() {
                if let archkeel_facts::ImportFact::Import(data) = &mut records[0].data {
                    data.type_only = Some(false);
                }
            }
        }),
    ];
    for (reason, change) in cases {
        let mut changed = original.clone();
        change(&mut changed);
        let refused = refusal(changed);
        assert!(refused.contains(reason), "{reason}: {refused}");
    }
}

#[test]
fn a_survey_with_a_gap_is_incomplete_and_its_gaps_must_be_its_unknowns() {
    use archkeel_facts::Section;

    let tree = project();
    fs::write(
        tree.root.join("src/app/client.py"),
        "import importlib\nimportlib.import_module(name)\n",
    )
    .unwrap();
    let original = reply(&tree);
    assert!(!original.facts.coverage.full_scope);
    assert_eq!(refusal(original.clone()), "");

    let mut partial = original.clone();
    for section in &mut partial.facts.sections {
        if let Section::Unknowns(records) = section {
            records.push(records[0].clone());
            records[1].id = archkeel_facts::ids::FactId::new("UNKNOWN-planted");
        }
    }
    assert!(!refusal(partial).is_empty());

    let mut hidden = original.clone();
    hidden.facts.coverage.gaps.clear();
    hidden.facts.coverage.full_scope = true;
    assert!(!refusal(hidden).is_empty());
}
