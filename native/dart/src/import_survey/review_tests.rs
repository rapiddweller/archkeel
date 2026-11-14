// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). The plants of the proof review of
// AD-454: a package configuration that moves a package, `Isolate.spawnUri` and the parse bounds.

use std::collections::BTreeMap;

use super::tests::run_roots;
use super::{edge_rows, gap_rows, Survey};

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";
const CONFIG: &str = ".dart_tool/package_config.json";

fn config(packages: &str) -> String {
    format!("{{\"configVersion\": 2, \"packages\": [{packages}]}}")
}

const OWN: &str = r#"{"name": "shop", "rootUri": "../", "packageUri": "lib/"}"#;

fn surveyed(config: &str) -> Survey {
    run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            (CONFIG, config),
            ("lib/a.dart", "import 'package:shop/b.dart';\n"),
            ("lib/b.dart", ""),
        ],
        &["lib"],
    )
}

fn only(found: &Survey, name: &str) {
    let expected = BTreeMap::from([(name.to_owned(), 1)]);
    assert_eq!(gap_rows(found), expected, "{:#?}", found.unknowns);
    assert!(!found.coverage.full_scope);
}

#[test]
fn the_pub_config_with_the_default_mapping_is_complete() {
    let external =
        r#"{"name": "http", "rootUri": "file:///cache/http-1.0.0/", "packageUri": "lib/"}"#;
    let found = surveyed(&config(&format!("{OWN}, {external}")));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(edge_rows(&found), ["shop.a import shop.b"]);
    assert!(found.inputs.iter().any(|input| input.path == CONFIG));
}

#[test]
fn a_config_that_moves_the_own_package_is_a_gap() {
    let moved = r#"{"name": "shop", "rootUri": "../../elsewhere/", "packageUri": "lib/"}"#;
    only(&surveyed(&config(moved)), "DartPackageConfig");
    let source = r#"{"name": "shop", "rootUri": "../", "packageUri": "src/"}"#;
    only(&surveyed(&config(source)), "DartPackageConfig");
    let absolute = r#"{"name": "shop", "rootUri": "file:///elsewhere/", "packageUri": "lib/"}"#;
    only(&surveyed(&config(absolute)), "DartPackageConfig");
}

#[test]
fn a_config_without_the_own_package_or_malformed_is_a_gap() {
    let other = r#"{"name": "http", "rootUri": "file:///cache/http/", "packageUri": "lib/"}"#;
    only(&surveyed(&config(other)), "DartPackageConfig");
    only(&surveyed("{not json"), "DartPackageConfig");
    only(&surveyed(r#"{"configVersion": 2}"#), "DartPackageConfig");
    only(
        &surveyed(&config(r#"{"name": "shop"}"#)),
        "DartPackageConfig",
    );
}

#[test]
fn a_config_that_maps_another_package_into_this_root_is_a_gap() {
    let inside = r#"{"name": "core", "rootUri": "../packages/core/", "packageUri": "lib/"}"#;
    only(
        &surveyed(&config(&format!("{OWN}, {inside}"))),
        "DartPackageConfig",
    );
    let scheme = r#"{"name": "core", "rootUri": "http://x/core/", "packageUri": "lib/"}"#;
    only(
        &surveyed(&config(&format!("{OWN}, {scheme}"))),
        "DartPackageConfig",
    );
}

#[test]
fn an_absolute_config_entry_into_this_root_is_a_gap() {
    let tree =
        archkeel_snapshot::test_tree::Tree::new(&[("pubspec.yaml", PUBSPEC), ("lib/a.dart", "")]);
    let root = tree.root.canonicalize().unwrap();
    let inside = format!(
        r#"{{"name": "core", "rootUri": "file://{}/packages/core/", "packageUri": "lib/"}}"#,
        root.to_str().unwrap()
    );
    std::fs::create_dir_all(tree.root.join(".dart_tool")).unwrap();
    std::fs::write(tree.root.join(CONFIG), config(&format!("{OWN}, {inside}"))).unwrap();
    let request = serde_json::json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let decoded = super::reply::decode(request.to_string().as_bytes()).unwrap();
    only(&super::survey(&decoded).unwrap(), "DartPackageConfig");
}

#[test]
fn dart_isolate_keeps_the_edge_and_is_a_gap() {
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", "import 'dart:isolate';\n"),
        ],
        &["lib"],
    );
    only(&found, "DartIsolate");
    assert_eq!(edge_rows(&found), ["shop.a import dart.isolate"]);
}

#[test]
fn a_dense_source_below_the_byte_budget_is_over_the_token_budget() {
    let dense = format!("import 'b.dart';\nvar x = [{}];\n", "1,".repeat(200_000));
    assert!(dense.len() < super::PARSE_BUDGET_BYTES);
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", &dense),
            ("lib/b.dart", ""),
        ],
        &["lib"],
    );
    only(&found, "DartParseBudget");
    assert!(found.imports.is_empty());
}

#[cfg(unix)]
#[test]
fn a_linked_package_configuration_is_a_gap() {
    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("pubspec.yaml", PUBSPEC),
        ("lib/a.dart", ""),
        ("real.json", &config(OWN)),
    ]);
    std::fs::create_dir_all(tree.root.join(".dart_tool")).unwrap();
    std::os::unix::fs::symlink(tree.root.join("real.json"), tree.root.join(CONFIG)).unwrap();
    let request = serde_json::json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let decoded = super::reply::decode(request.to_string().as_bytes()).unwrap();
    only(&super::survey(&decoded).unwrap(), "DartPackageConfig");
}
