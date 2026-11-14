// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `scan` binds a Dart reply to the snapshot, and the store accepts only a complete and
// consistent import survey (AD-468). Each planted claim refuses the reply.

use std::fs;

use archkeel_facts::envelope::{OwnedFile, Profile, Reply, Target};
use archkeel_facts::ids::{ModuleName, PackageName};
use archkeel_facts::{ImportFact, Section};
use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::*;

fn root(tree: &Tree) -> Root {
    let path = fs::canonicalize(&tree.root).unwrap();
    Root::of(path.to_str().unwrap()).unwrap()
}

fn project() -> Tree {
    Tree::new(&[
        ("pubspec.yaml", "name: shop\nenvironment:\n  sdk: ^3.4.0\n"),
        (
            "lib/a.dart",
            "import 'b.dart';\nimport 'dart:async';\nimport 'package:http/http.dart';\npart 'p.dart';\n",
        ),
        ("lib/b.dart", ""),
        ("lib/p.dart", "part of 'a.dart';\n"),
    ])
}

fn reply(tree: &Tree) -> Reply {
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": resolver(),
    });
    crate::run::reply_of(Profile::Dart, request.to_string().as_bytes()).unwrap()
}

fn refused(reply: Reply) -> String {
    archkeel_store::ingest_typed(reply)
        .err()
        .expect("the store must refuse the claim")
}

fn imports(reply: &mut Reply) -> &mut Vec<archkeel_facts::Record<ImportFact>> {
    reply
        .facts
        .sections
        .iter_mut()
        .find_map(|section| match section {
            Section::Imports(records) => Some(records),
            _ => None,
        })
        .unwrap()
}

#[test]
fn the_store_accepts_the_survey_with_its_part_owner() {
    let tree = project();
    let reply = reply(&tree);
    assert_eq!(reply.facts.files.len(), 2);
    assert_eq!(reply.facts.owned_files.len(), 1);
    assert_eq!(reply.facts.owned_files[0].owner.as_str(), "shop.a");
    assert_eq!(reply.facts.coverage.files_parsed, 3);
    assert!(reply.facts.coverage.full_scope);
    bound(&root(&tree), &reply).unwrap();
    archkeel_store::ingest_typed(reply).unwrap();
}

#[test]
fn a_changed_input_or_source_digest_is_refused() {
    let tree = project();
    let mut reply = reply(&tree);
    reply.facts.source.source_digest = "0".repeat(64);
    assert!(bound(&root(&tree), &reply)
        .unwrap_err()
        .contains("source digest"));
    let reply = self::reply(&tree);
    fs::write(tree.root.join("lib/b.dart"), "// changed\n").unwrap();
    assert!(bound(&root(&tree), &reply)
        .unwrap_err()
        .contains("differs from its digest"));
}

#[test]
fn a_part_without_an_owner_or_a_wrong_owner_is_refused() {
    let tree = project();
    let mut unowned = reply(&tree);
    unowned.facts.owned_files.clear();
    assert!(refused(unowned).contains("has no module, owner or gap"));
    let mut foreign = reply(&tree);
    foreign.facts.owned_files[0].owner = ModuleName::new("shop.nothing");
    assert!(refused(foreign).contains("no unique owner"));
    let mut module = reply(&tree);
    module.facts.owned_files.push(OwnedFile {
        rel_path: "lib/b.dart".to_owned(),
        module: ModuleName::new("shop.b"),
        owner: ModuleName::new("shop.a"),
    });
    assert!(refused(module).contains("no unique owner"));
}

#[test]
fn a_target_that_breaks_the_dart_uri_rules_is_refused() {
    let tree = project();
    let edit = |change: &dyn Fn(&mut Target)| {
        let mut reply = reply(&tree);
        reply.facts.imports.iter_mut().for_each(change);
        refused(reply)
    };
    let builtin = edit(&|target| {
        if let Target::Builtin { name, .. } = target {
            *name = "async".to_owned();
        }
    });
    assert!(builtin.contains("one dart: library"), "{builtin}");
    let external = edit(&|target| {
        if let Target::External { package, .. } = target {
            *package = PackageName::new("shop");
        }
    });
    assert!(external.contains("another package"), "{external}");
}

#[test]
fn an_import_with_known_symbols_or_a_specifier_is_refused() {
    let tree = project();
    let mut reply = reply(&tree);
    imports(&mut reply)[0].data.data_mut().symbols_known = true;
    assert!(refused(reply).contains("no known symbols"));
}

#[test]
fn a_dart_test_exclusion_is_refused_by_the_configuration() {
    let config = "[scan]\nlanguage = \"dart\"\nroots = [\"lib\"]\nnamespace = \"shop\"\n\
                  contract = \"c.json\"\nexclude_test_sources = true\n";
    let refused = crate::config::parse(config.as_bytes(), "archkeel.toml").unwrap_err();
    assert!(format!("{refused:?}").contains("exclude_test_sources is not supported"));
}

#[test]
fn coverage_gaps_that_are_not_the_unknowns_are_refused() {
    let tree = Tree::new(&[
        ("pubspec.yaml", "name: shop\nenvironment:\n  sdk: ^3.4.0\n"),
        ("lib/a.dart", "import 'gone.dart';\n"),
    ]);
    let mut reply = reply(&tree);
    assert!(!reply.facts.coverage.gaps.is_empty());
    for section in &mut reply.facts.sections {
        if let Section::Unknowns(records) = section {
            records.clear();
        }
    }
    assert!(refused(reply).contains("the coverage gaps must be the unknowns of the survey"));
}

#[test]
fn a_part_with_two_owners_is_refused() {
    let tree = project();
    let mut reply = reply(&tree);
    let mut second = reply.facts.owned_files[0].clone();
    second.owner = ModuleName::new("shop.b");
    reply.facts.owned_files.push(second);
    assert!(refused(reply).contains("no unique owner"));
}
