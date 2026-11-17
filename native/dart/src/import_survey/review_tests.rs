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
fn a_relative_external_package_or_file_uri_with_a_host_is_a_gap() {
    for root in [
        "../../external/",
        "../../x/../external/",
        "file://example.org/pkg/",
    ] {
        let external = format!(r#"{{"name":"external","rootUri":"{root}","packageUri":"lib/"}}"#);
        only(
            &surveyed(&config(&format!("{OWN}, {external}"))),
            "DartPackageConfig",
        );
    }
}

#[test]
fn a_loader_from_a_hosted_reexport_is_a_gap_without_an_isolate_import() {
    let found = run_roots(&[
        ("pubspec.yaml", PUBSPEC),
        ("lib/a.dart", "import 'package:helper/helper.dart';\nvoid f() { Isolate.spawnUri(uri, [], null); }"),
    ], &["lib"]);
    only(&found, "DartIsolate");
}

#[test]
fn mirror_identifiers_from_a_hosted_reexport_are_gaps() {
    for name in [
        "currentMirrorSystem",
        "reflect",
        "reflectClass",
        "reflectType",
    ] {
        let text = format!("import 'package:helper/helper.dart';\nvoid f() {{ {name}(x); }}");
        let found = run_roots(
            &[("pubspec.yaml", PUBSPEC), ("lib/a.dart", &text)],
            &["lib"],
        );
        only(&found, "DartMirrors");
    }
}

#[test]
fn loader_and_mirror_words_in_strings_and_comments_are_not_identifiers() {
    let text = "// spawnUri reflect\nconst s = 'currentMirrorSystem reflectClass reflectType';";
    let found = run_roots(&[("pubspec.yaml", PUBSPEC), ("lib/a.dart", text)], &["lib"]);
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
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
fn dart_isolate_without_a_uri_loader_keeps_the_edge_without_a_gap() {
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", "import 'dart:isolate';\n"),
        ],
        &["lib"],
    );
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(edge_rows(&found), ["shop.a import dart.isolate"]);
}

#[test]
fn an_isolate_uri_loader_anywhere_in_the_scan_keeps_the_gap() {
    for source in [
        "Isolate.spawnUri(uri, [], null);",
        "var f = Isolate.spawnUri;",
        "(x as dynamic).spawnUri(uri, [], null);",
        "Function.apply(Isolate.spawnUri, [uri, [], null]);",
    ] {
        let text = format!("import 'dart:isolate';\nvoid f() {{ {source} }}");
        let found = run_roots(
            &[("pubspec.yaml", PUBSPEC), ("lib/a.dart", &text)],
            &["lib"],
        );
        only(&found, "DartIsolate");
    }
}

#[test]
fn isolate_ports_prefixes_and_static_spawn_do_not_load_a_uri() {
    for source in [
        "import 'dart:isolate' as iso;\nvoid f() { iso.ReceivePort(); }",
        "import 'dart:isolate' show Isolate, SendPort;\nvoid f() { Isolate.spawn(entry, null); }",
        "import 'dart:isolate';\n// spawnUri\nvar text = 'spawnUri';",
    ] {
        let found = run_roots(
            &[("pubspec.yaml", PUBSPEC), ("lib/a.dart", source)],
            &["lib"],
        );
        assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    }
}

#[test]
fn a_loader_in_a_part_or_behind_an_export_keeps_the_gap() {
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", "import 'dart:isolate';\npart 'p.dart';"),
            (
                "lib/p.dart",
                "part of 'a.dart';\nvoid f() { Isolate.spawnUri(uri, [], null); }",
            ),
        ],
        &["lib"],
    );
    only(&found, "DartIsolate");
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", "export 'dart:isolate';"),
            ("lib/b.dart", "import 'a.dart';\nvar f = Isolate.spawnUri;"),
        ],
        &["lib"],
    );
    only(&found, "DartIsolate");
}

#[test]
fn mirrors_keeps_isolate_and_mirrors_gaps() {
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            (
                "lib/a.dart",
                "import 'dart:isolate';\nimport 'dart:mirrors';",
            ),
        ],
        &["lib"],
    );
    assert_eq!(
        gap_rows(&found),
        BTreeMap::from([("DartIsolate".to_owned(), 1), ("DartMirrors".to_owned(), 1),])
    );
}

#[test]
fn no_such_method_that_calls_the_loader_keeps_the_gap() {
    let found = run_roots(
        &[
            ("pubspec.yaml", PUBSPEC),
            ("lib/a.dart", "import 'dart:isolate';\nclass X { noSuchMethod(i) => Isolate.spawnUri(uri, [], null); }"),
        ],
        &["lib"],
    );
    only(&found, "DartIsolate");
}

// Premise: code outside the scan roots does not load scanned code from a name passed as data.
#[test]
fn an_external_loader_has_the_same_result_with_or_without_isolate() {
    for import in ["import 'dart:isolate';", "import 'dart:async';"] {
        let text = format!("{import}\nimport 'package:loader/loader.dart';\nvoid f() {{ runWorker(Uri.parse('worker.dart')); }}");
        let found = run_roots(
            &[("pubspec.yaml", PUBSPEC), ("lib/a.dart", &text)],
            &["lib"],
        );
        assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    }
}

#[cfg(unix)]
#[test]
fn an_imported_workspace_member_can_link_into_the_scan() {
    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"),
        ("other/pubspec.yaml", "name: other\nresolution: workspace\n"),
        ("lib/a.dart", "import 'package:other/b.dart';"),
        ("lib/b.dart", ""),
    ]);
    std::os::unix::fs::symlink("../lib", tree.root.join("other/lib")).unwrap();
    let request = serde_json::json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let decoded = super::reply::decode(request.to_string().as_bytes()).unwrap();
    let found = super::survey(&decoded).unwrap();
    only(&found, "DartLocalPackage");
}

#[test]
fn a_workspace_config_keeps_a_gap_for_external_links() {
    let found = run_roots(
        &[
            ("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"),
            ("other/pubspec.yaml", "name: other\nresolution: workspace\n"),
            (CONFIG, &config(OWN)),
            ("lib/a.dart", ""),
        ],
        &["lib"],
    );
    only(&found, "DartWorkspace");
}

#[cfg(unix)]
#[test]
fn a_configured_external_package_can_link_into_the_scan() {
    let tree = archkeel_snapshot::test_tree::Tree::new(&[
        ("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"),
        ("other/pubspec.yaml", "name: other\nresolution: workspace\n"),
        ("lib/a.dart", "import 'package:external/b.dart';"),
        ("lib/b.dart", ""),
    ]);
    let external = archkeel_snapshot::test_tree::Tree::new(&[]);
    std::os::unix::fs::symlink(tree.root.join("lib"), external.root.join("lib")).unwrap();
    std::fs::create_dir_all(tree.root.join(".dart_tool")).unwrap();
    let entry = format!(
        r#"{{"name":"external","rootUri":"file://{}/","packageUri":"lib/"}}"#,
        external.path()
    );
    std::fs::write(tree.root.join(CONFIG), config(&format!("{OWN}, {entry}"))).unwrap();
    let request = serde_json::json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let decoded = super::reply::decode(request.to_string().as_bytes()).unwrap();
    let found = super::survey(&decoded).unwrap();
    only(&found, "DartWorkspace");
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
