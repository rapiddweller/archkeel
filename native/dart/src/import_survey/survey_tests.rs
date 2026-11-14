// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). Each test plants one rule or one
// gap of AD-454. A gap must keep the coverage incomplete, so a missing edge can never give PASS.

use std::collections::BTreeMap;

use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::{edge_rows, gap_rows, survey, Survey};

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";

pub(crate) fn run_roots(files: &[(&str, &str)], roots: &[&str]) -> Survey {
    let tree = Tree::new(files);
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": roots, "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let request = crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap();
    survey(&request).unwrap()
}

fn run(files: &[(&str, &str)]) -> Survey {
    run_roots(files, &["lib"])
}

fn with_pubspec<'a>(files: &[(&'a str, &'a str)]) -> Vec<(&'a str, &'a str)> {
    let mut all = vec![("pubspec.yaml", PUBSPEC)];
    all.extend_from_slice(files);
    all
}

fn gaps(found: &Survey) -> BTreeMap<String, usize> {
    gap_rows(found)
}

fn only_gap(found: &Survey, name: &str) {
    let expected = BTreeMap::from([(name.to_owned(), 1)]);
    assert_eq!(gaps(found), expected, "{:#?}", found.unknowns);
    assert!(!found.coverage.full_scope);
}

#[test]
fn relative_own_package_sdk_and_external_uris_give_edges() {
    let found = run(&with_pubspec(&[
        (
            "lib/a.dart",
            "import 'src/b.dart';\nimport 'package:shop/src/c.dart';\n\
             import 'dart:async';\nimport 'package:http/http.dart' as http;\n",
        ),
        ("lib/src/b.dart", "import '../a.dart';\n"),
        ("lib/src/c.dart", ""),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(
        edge_rows(&found),
        [
            "shop.a import dart.async",
            "shop.a import http.http",
            "shop.a import shop.src.b",
            "shop.a import shop.src.c",
            "shop.src.b import shop.a",
        ]
    );
    assert_eq!(found.files.len(), 3);
    assert_eq!(found.imports.len(), found.targets.len());
    let kinds: Vec<&str> = found
        .targets
        .iter()
        .map(|target| match target {
            archkeel_facts::envelope::Target::Local { .. } => "local",
            archkeel_facts::envelope::Target::External { .. } => "external",
            archkeel_facts::envelope::Target::Builtin { .. } => "builtin",
            archkeel_facts::envelope::Target::Unresolved { .. } => "unresolved",
        })
        .collect();
    assert_eq!(kinds.iter().filter(|kind| **kind == "local").count(), 3);
    assert!(kinds.contains(&"external") && kinds.contains(&"builtin"));
}

#[test]
fn an_export_is_a_reexport_edge_and_a_deferred_import_is_a_plain_edge() {
    let found = run(&with_pubspec(&[
        (
            "lib/a.dart",
            "export 'b.dart';\nimport 'c.dart' deferred as c;\n",
        ),
        ("lib/b.dart", ""),
        ("lib/c.dart", ""),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(
        edge_rows(&found),
        ["shop.a export shop.b", "shop.a import shop.c"]
    );
}

#[test]
fn each_conditional_alternative_is_an_edge() {
    let found = run(&with_pubspec(&[
        (
            "lib/a.dart",
            "import 'stub.dart' if (dart.library.io) 'io.dart' if (dart.library.html) 'web.dart';\n\
             export 'stub.dart' if (dart.library.io) 'io.dart';\n",
        ),
        ("lib/stub.dart", ""),
        ("lib/io.dart", ""),
        ("lib/web.dart", ""),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(
        edge_rows(&found),
        [
            "shop.a export shop.io",
            "shop.a export shop.stub",
            "shop.a import shop.io",
            "shop.a import shop.stub",
            "shop.a import shop.web",
        ]
    );
}

#[test]
fn a_missing_conditional_alternative_is_a_gap() {
    let found = run(&with_pubspec(&[
        (
            "lib/a.dart",
            "import 'stub.dart' if (dart.library.io) 'io.dart';\n",
        ),
        ("lib/stub.dart", ""),
    ]));
    only_gap(&found, "DartTargetMissing");
    assert_eq!(edge_rows(&found), ["shop.a import shop.stub"]);
}

#[test]
fn a_part_is_owned_by_its_library_and_has_no_file_fact() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "import 'b.dart';\npart 'a_part.dart';\n"),
        ("lib/a_part.dart", "part of 'a.dart';\nclass P {}\n"),
        ("lib/b.dart", ""),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(found.files.len(), 2, "a part has no file fact");
    assert_eq!(found.parts.len(), 1);
    assert_eq!(found.parts[0].part, "lib/a_part.dart");
    assert_eq!(found.parts[0].library, "lib/a.dart");
    assert_eq!(found.parts[0].module.as_str(), "shop.a");
    assert_eq!(edge_rows(&found), ["shop.a import shop.b"]);
}

#[test]
fn an_import_in_a_part_is_a_syntax_gap_of_the_grammar() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "part 'p.dart';\n"),
        ("lib/p.dart", "part of 'a.dart';\nimport 'b.dart';\n"),
        ("lib/b.dart", ""),
    ]));
    let rows = gaps(&found);
    assert_eq!(rows.get("SyntaxError"), Some(&1), "{rows:?}");
    assert!(!found.coverage.full_scope);
}

#[test]
fn a_part_of_by_library_name_is_owned() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "library shop.a;\npart 'p.dart';\n"),
        ("lib/p.dart", "part of shop.a;\n"),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(found.parts.len(), 1);
}

#[test]
fn a_part_of_another_library_name_is_unowned() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "library shop.a;\npart 'p.dart';\n"),
        ("lib/p.dart", "part of shop.other;\n"),
    ]));
    only_gap(&found, "DartPartUnowned");
}

#[test]
fn a_library_name_is_compared_as_a_whole() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "library ofx;\npart 'p.dart';\n"),
        ("lib/p.dart", "part of x;\n"),
    ]));
    only_gap(&found, "DartPartUnowned");
}

#[test]
fn a_part_that_no_library_claims_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", ""),
        ("lib/p.dart", "part of 'a.dart';\n"),
    ]));
    only_gap(&found, "DartPartUnowned");
    assert!(found.parts.is_empty());
}

#[test]
fn a_part_uri_to_a_library_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "part 'b.dart';\n"),
        ("lib/b.dart", ""),
    ]));
    only_gap(&found, "DartPartNotPart");
}

#[test]
fn a_part_claimed_by_two_libraries_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "part 'p.dart';\n"),
        ("lib/b.dart", "part 'p.dart';\n"),
        ("lib/p.dart", "part of 'a.dart';\n"),
    ]));
    only_gap(&found, "DartPartConflict");
    assert!(found.parts.is_empty());
}

#[test]
fn an_absent_generated_part_is_a_named_missing_target() {
    let found = run(&with_pubspec(&[(
        "lib/model.dart",
        "part 'model.g.dart';\npart 'model.freezed.dart';\n",
    )]));
    assert_eq!(
        gaps(&found),
        BTreeMap::from([("DartTargetMissing".to_owned(), 2)])
    );
    assert!(found
        .unknowns
        .iter()
        .all(|record| record.title.contains("the generated file")));
}

#[test]
fn a_present_generated_part_is_source_like_any_other() {
    let found = run(&with_pubspec(&[
        ("lib/model.dart", "part 'model.g.dart';\n"),
        ("lib/model.g.dart", "part of 'model.dart';\n"),
        ("lib/use.dart", "import 'model.g.dart';\n"),
    ]));
    only_gap(&found, "DartTargetIsPart");
    assert_eq!(found.parts.len(), 1);
}

#[test]
fn an_import_of_a_part_file_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "part 'p.dart';\n"),
        ("lib/p.dart", "part of 'a.dart';\n"),
        ("lib/b.dart", "import 'p.dart';\n"),
    ]));
    only_gap(&found, "DartTargetIsPart");
}

#[test]
fn a_missing_target_is_a_gap_and_gives_no_edge() {
    let found = run(&with_pubspec(&[("lib/a.dart", "import 'gone.dart';\n")]));
    only_gap(&found, "DartTargetMissing");
    assert!(found.imports.is_empty());
}

#[test]
fn a_target_outside_the_scan_roots_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "import '../tool/t.dart';\n"),
        ("tool/t.dart", ""),
    ]));
    only_gap(&found, "DartTargetNotSelected");
}

#[test]
fn a_relative_uri_above_the_snapshot_root_is_a_gap() {
    let found = run(&with_pubspec(&[("lib/a.dart", "import '../../x.dart';\n")]));
    only_gap(&found, "DartTargetOutside");
}

#[test]
fn an_own_package_uri_above_lib_is_a_gap() {
    let found = run(&with_pubspec(&[(
        "lib/a.dart",
        "import 'package:shop/../x.dart';\n",
    )]));
    only_gap(&found, "DartTargetOutside");
}

#[test]
fn an_unsupported_uri_is_a_gap() {
    for uri in [
        "http://x/a.dart",
        "/abs.dart",
        "a.dart?x",
        "a%20b.dart",
        "package:http",
    ] {
        let text = format!("import '{uri}';\n");
        let found = run(&with_pubspec(&[("lib/a.dart", &text)]));
        only_gap(&found, "DartUnsupportedUri");
    }
}

#[test]
fn an_interpolated_uri_is_a_named_gap() {
    let found = run(&with_pubspec(&[(
        "lib/a.dart",
        "import '$x.dart';\nconst x = 'b';\n",
    )]));
    assert_eq!(
        gaps(&found).get("DartUriNotLiteral"),
        Some(&1),
        "{:#?}",
        found.unknowns
    );
    assert!(!found.coverage.full_scope);
}

#[test]
fn dart_mirrors_keeps_the_edge_and_is_a_gap() {
    let found = run(&with_pubspec(&[("lib/a.dart", "import 'dart:mirrors';\n")]));
    only_gap(&found, "DartMirrors");
    assert_eq!(edge_rows(&found), ["shop.a import dart.mirrors"]);
}

#[test]
fn a_workspace_or_path_dependency_is_a_gap() {
    let cases = [
        ("name: shop\nworkspace:\n  - pkgs/a\n", "DartWorkspace"),
        ("name: shop\nresolution: workspace\n", "DartWorkspace"),
        (
            "name: shop\ndependencies:\n  core:\n    path: ../core\n",
            "DartPathDependency",
        ),
    ];
    for (pubspec, name) in cases {
        let found = run(&[("pubspec.yaml", pubspec), ("lib/a.dart", "")]);
        let rows = gaps(&found);
        assert_eq!(rows.get(name), Some(&1), "{pubspec}: {rows:?}");
        assert!(!found.coverage.full_scope);
    }
}

#[test]
fn a_nested_package_or_a_package_config_is_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", ""),
        ("lib/inner/pubspec.yaml", "name: x\n"),
    ]));
    only_gap(&found, "DartNestedPackage");
    for name in ["package_config.json", ".packages", "pubspec_overrides.yaml"] {
        let found = run(&with_pubspec(&[("lib/a.dart", ""), (name, "{}")]));
        only_gap(&found, "DartPackageConfig");
    }
}

#[test]
fn the_generated_package_config_of_pub_is_not_a_gap() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", ""),
        (".dart_tool/package_config.json", "{}"),
    ]));
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
}

#[test]
fn a_source_over_the_parse_budget_is_a_gap_and_not_parsed() {
    let big = format!(
        "import 'b.dart';\n//{}\n",
        "x".repeat(super::PARSE_BUDGET_BYTES)
    );
    let found = run(&with_pubspec(&[("lib/a.dart", &big), ("lib/b.dart", "")]));
    only_gap(&found, "DartParseBudget");
    assert!(
        found.imports.is_empty(),
        "a source over the budget gives no edge"
    );
    assert_eq!(found.files.len(), 1);
}

#[test]
fn a_syntax_error_or_bad_bytes_give_a_gap_and_no_module() {
    let found = run(&with_pubspec(&[
        ("lib/a.dart", "import 'b.dart';\nclass {"),
        ("lib/b.dart", ""),
        ("lib/c.dart", "import 'a.dart';\n"),
    ]));
    let rows = gaps(&found);
    assert_eq!(rows.get("SyntaxError"), Some(&1), "{rows:?}");
    assert_eq!(rows.get("DartTargetUnparsed"), Some(&1), "{rows:?}");
    assert_eq!(found.files.len(), 2);
}

#[test]
fn a_missing_pubspec_makes_own_package_uris_external_and_the_scope_incomplete() {
    let found = run(&[
        ("lib/a.dart", "import 'package:shop/b.dart';\n"),
        ("lib/b.dart", ""),
    ]);
    assert_eq!(gaps(&found).get("PubspecMissing"), Some(&1));
    assert!(!found.coverage.full_scope);
}

#[test]
fn a_test_root_and_a_bin_root_resolve_like_lib() {
    let found = run_roots(
        &with_pubspec(&[
            ("lib/a.dart", ""),
            ("bin/main.dart", "import 'package:shop/a.dart';\n"),
            ("test/a_test.dart", "import '../lib/a.dart';\n"),
        ]),
        &["lib", "bin", "test"],
    );
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(
        edge_rows(&found),
        ["shop.a_test import shop.a", "shop.main import shop.a"]
    );
}

#[test]
fn gaps_and_coverage_hold_the_same_records() {
    let found = run(&with_pubspec(&[("lib/a.dart", "import 'gone.dart';\n")]));
    assert_eq!(found.coverage.gaps, found.unknowns);
    assert_eq!(found.named.len(), 1);
    assert_eq!(found.coverage.selected_files, ["lib/a.dart"]);
}

#[test]
fn the_decision_record_names_each_gap() {
    let record = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../docs/architecture/decisions/\
         ad-454-the-native-dart-import-survey-resolves-one-package-and-names-each-gap.md",
    );
    let text = std::fs::read_to_string(record).unwrap();
    for name in super::GapName::ALL {
        let row = format!("| `{}` |", name.as_str());
        assert!(text.contains(&row), "{row}");
    }
}
