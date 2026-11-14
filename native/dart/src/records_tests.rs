// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host, which reads the inputs, the file facts and the gaps of the Dart reply. The
// expected JSON comes from the Python collector (`collect._Collection`) on the same tree.

use serde_json::json;

use super::*;
use crate::discover::{Problem, Source};
use crate::parse::DartParser;
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
        package_files: Vec::new(),
    }
}

/// The sections with the parse of each source, as the dump builds them.
fn build(discovery: &Discovery, roots: &[String]) -> Sections {
    let mut parser = DartParser::new().unwrap();
    let syntax: Vec<_> = discovery
        .sources
        .iter()
        .map(|source| parser.parse(&source.content))
        .collect();
    sections(discovery, roots, &syntax)
}

#[test]
fn a_file_fact_cites_its_first_line_or_line_zero() {
    let sources = vec![
        source("lib/a.dart", "shop.a", "class A {}  \n// x"),
        source("lib/b.dart", "shop.b", "\nclass B {}"),
        source("lib/c.dart", "shop.c", " \n\t"),
    ];
    let built = build(&discovery(sources, Vec::new()), &["lib".to_owned()]);
    let files = serde_json::to_value(&built.files).unwrap();
    // The ids equaled those of the Python collector of release 4.0.1; its test is deleted.
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
    let built = build(
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

#[test]
fn the_inputs_are_sorted_by_path_also_after_pubspec_yaml() {
    let sources = vec![
        source("test/a_test.dart", "shop.a_test", ""),
        source("lib/a.dart", "shop.a", ""),
    ];
    let built = build(
        &discovery(sources, Vec::new()),
        &["lib".to_owned(), "test".to_owned()],
    );
    let paths: Vec<&str> = built
        .inputs
        .iter()
        .map(|input| input.path.as_str())
        .collect();
    assert_eq!(paths, ["lib/a.dart", "pubspec.yaml", "test/a_test.dart"]);
}

#[test]
fn a_syntax_error_removes_the_file_fact_and_gives_a_gap_at_the_first_error() {
    let sources = vec![
        source("lib/a.dart", "shop.a", "class A {}\n"),
        source("lib/broken.dart", "shop.broken", "class A {}\nclass {\n"),
        source("lib/mixin.dart", "shop.mixin", "mixin M on A {}\n"),
    ];
    let built = build(&discovery(sources, Vec::new()), &["lib".to_owned()]);
    let files: Vec<&str> = built.files.iter().map(|f| f.rel_path.as_str()).collect();
    assert_eq!(files, ["lib/a.dart", "lib/mixin.dart"]);
    let gaps = serde_json::to_value(&built.gaps).unwrap();
    let mut kinds: Vec<(String, String)> = gaps
        .as_array()
        .unwrap()
        .iter()
        .map(|gap| (gap["kind"].to_string(), gap["subjects"][0].to_string()))
        .collect();
    kinds.sort();
    assert_eq!(
        kinds,
        [
            (
                "\"SyntaxError\"".to_owned(),
                "\"lib/broken.dart:2\"".to_owned()
            ),
            (
                "\"UnsupportedDeclaration\"".to_owned(),
                "\"lib/mixin.dart:1\"".to_owned()
            ),
        ]
    );
    let syntax = gaps
        .as_array()
        .unwrap()
        .iter()
        .find(|gap| gap["kind"] == json!("SyntaxError"))
        .unwrap();
    assert_eq!(
        syntax["data"]["message"],
        json!("syntax errors prevent complete source facts")
    );
    let cited = syntax["evidence_ids"][0].as_str().unwrap();
    let evidence = built
        .evidence
        .iter()
        .find(|e| e.id.as_str() == cited)
        .unwrap();
    assert_eq!((evidence.line, evidence.excerpt.is_empty()), (2, false));
}

#[test]
fn a_source_that_is_not_utf8_gives_an_encoding_gap_and_a_syntax_gap() {
    let mut latin = source("lib/latin.dart", "shop.latin", "");
    latin.content = b"// caf\xe9\nclass C {}\n".to_vec();
    let built = build(&discovery(vec![latin], Vec::new()), &["lib".to_owned()]);
    assert!(built.files.is_empty());
    let gaps = serde_json::to_value(&built.gaps).unwrap();
    let mut kinds: Vec<String> = gaps
        .as_array()
        .unwrap()
        .iter()
        .map(|gap| gap["kind"].as_str().unwrap().to_owned())
        .collect();
    kinds.sort();
    assert_eq!(kinds, ["SyntaxError", "invalid_encoding"]);
}
