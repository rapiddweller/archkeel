// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `archkeel-collect`, which will call `typed_reply` in the process of the core as it
// calls the TypeScript and Rust collectors (AD-406, AD-454).

use archkeel_facts::envelope::{Profile, Provenance, SectionName};
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::protocol::reply_version;
use serde_json::json;

use super::{decode, typed_reply};

fn reply_of(files: &[(&str, &str)]) -> archkeel_facts::envelope::Reply {
    let tree = Tree::new(files);
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let request = decode(request.to_string().as_bytes()).unwrap();
    let provenance = Provenance::native(Profile::Dart, ("0.0.0", "test"), ("rustc", "1.97"));
    typed_reply(
        &request,
        provenance,
        reply_version(request.protocol_version),
    )
    .unwrap()
}

#[test]
fn the_typed_reply_declares_imports_and_unknowns_only() {
    let reply = reply_of(&[
        ("pubspec.yaml", "name: shop\nenvironment:\n  sdk: ^3.4.0\n"),
        ("lib/a.dart", "import 'b.dart';\nimport 'dart:io';\n"),
        ("lib/b.dart", ""),
    ]);
    let facts = &reply.facts;
    assert_eq!(facts.profile, Profile::Dart);
    assert_eq!(
        facts.capabilities.sections,
        [SectionName::Imports, SectionName::Unknowns]
    );
    assert!(facts.capabilities.resolution_features.is_empty());
    assert_eq!(facts.files.len(), 2);
    assert_eq!(facts.imports.len(), 2);
    assert!(facts.coverage.full_scope);
    assert_eq!(facts.coverage.files_parsed, 2);
    assert_eq!(facts.inputs.len(), 3, "two sources and pubspec.yaml");
}

#[test]
fn a_gap_of_the_survey_is_a_gap_of_the_reply() {
    let reply = reply_of(&[
        ("pubspec.yaml", "name: shop\n"),
        ("lib/a.dart", "import 'gone.dart';\n"),
    ]);
    assert!(!reply.facts.coverage.full_scope);
    assert!(reply
        .facts
        .coverage
        .gaps
        .iter()
        .any(|gap| gap.title.contains("DartTargetMissing")));
}
