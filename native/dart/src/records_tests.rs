// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host, which reads the inputs, the file facts and the gaps of the Dart reply. The
// expected JSON comes from the Python collector (`collect._Collection`) on the same tree.

use serde_json::json;

use super::*;
use crate::discover::Source;
use crate::pubspec::SdkState;

fn source(rel_path: &str, module: &str, content: &str) -> Source {
    Source {
        rel_path: rel_path.to_owned(),
        module: module.to_owned(),
        content: content.as_bytes().to_vec(),
        digest: sha256_hex(content.as_bytes()),
    }
}

fn discovery(sources: Vec<Source>, problems: Vec<Problem>) -> Discovery {
    Discovery {
        sources,
        package_name: "shop".to_owned(),
        sdk: None,
        sdk_state: SdkState::Missing,
        pubspec_digest: Some("d".repeat(64)),
        problems,
    }
}

#[test]
fn a_file_fact_cites_its_first_line_or_line_zero() {
    let sources = vec![
        source("lib/a.dart", "shop.a", "class A {}  \nx"),
        source("lib/b.dart", "shop.b", "\nclass B {}"),
        source("lib/c.dart", "shop.c", " \n\t"),
    ];
    let built = sections(&discovery(sources, Vec::new()), &["lib".to_owned()]);
    let files = serde_json::to_value(&built.files).unwrap();
    // The ids are checked against the Python collector by `tests/test_collector_native_dart_discovery.py`.
    assert_eq!(files[0]["module"], json!("shop.a"));
    assert_eq!(files[0]["package"], json!("shop"));
    assert_eq!(files[0]["blank"], json!(false));
    assert_eq!(files[2]["blank"], json!(true));
    let evidence = serde_json::to_value(&built.evidence).unwrap();
    let excerpts: Vec<(&str, i64)> = built
        .evidence
        .iter()
        .map(|item| (item.excerpt.as_str(), item.line))
        .collect();
    assert!(excerpts.contains(&("class A {}", 1)), "{evidence}");
    assert!(excerpts.contains(&("", 0)), "{evidence}");
    assert_eq!(built.scope, ["lib/**/*.dart"]);
    let paths: Vec<&str> = built
        .inputs
        .iter()
        .map(|input| input.path.as_str())
        .collect();
    assert_eq!(
        paths,
        ["lib/a.dart", "lib/b.dart", "lib/c.dart", "pubspec.yaml"]
    );
}

#[test]
fn a_problem_is_an_unknown_gap_at_line_one_of_its_path() {
    let found = Problem {
        path: "lib/link.dart".to_owned(),
        kind: archkeel_facts::vocab::ExceptionName::DartSourceLink,
        message: "source file is a symlink".to_owned(),
    };
    let built = sections(
        &discovery(Vec::new(), vec![found.clone(), found]),
        &[".".to_owned()],
    );
    assert_eq!(built.gaps.len(), 1, "one problem gives one gap");
    let gap = serde_json::to_value(&built.gaps[0]).unwrap();
    assert_eq!(gap["kind"], json!("DartSourceLink"));
    assert_eq!(gap["area"], json!("analysis_coverage"));
    assert_eq!(gap["evidence_class"], json!("UNKNOWN"));
    assert_eq!(
        gap["title"],
        json!("lib/link.dart:1 could not be analyzed: source file is a symlink")
    );
    assert_eq!(gap["subjects"], json!(["lib/link.dart:1"]));
    assert_eq!(gap["evidence_ids"], json!([]));
    assert_eq!(
        gap["data"],
        json!({"file": "lib/link.dart", "line": 1, "message": "source file is a symlink"})
    );
    assert_eq!(built.scope, ["**/*.dart"]);
}
