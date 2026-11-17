// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package keys of the root `pubspec.yaml`: a workspace, a local dependency and an import of
//! a package that the package map does not prove external (AD-454, AD-800).

use std::collections::BTreeMap;

use super::tests::run_roots;
use super::{gap_rows, Survey};

fn run(files: &[(&str, &str)]) -> Survey {
    run_roots(files, &["lib"])
}

fn gaps(found: &Survey) -> BTreeMap<String, usize> {
    gap_rows(found)
}

#[test]
fn a_workspace_or_path_dependency_is_a_gap() {
    let core = "name: shop\ndependencies:\n  core:\n    path: ../core\n";
    let cases = [
        ("name: shop\nworkspace:\n  - pkgs/a\n", "", "DartWorkspace"),
        (
            "name: shop\nresolution: workspace\n",
            "import 'package:x/x.dart';",
            "DartLocalPackage",
        ),
        (
            "name: shop\nresolution: workspace\n",
            "import 'package:shop/b.dart';",
            "DartLocalPackage",
        ),
        (core, "import 'package:core/c.dart';", "DartLocalPackage"),
        (
            core,
            "import 'package:meta/meta.dart';",
            "DartUndeclaredPackage",
        ),
        (
            "name: shop\ndependencies:\n  core:\n    git: ../core\n",
            "import 'package:core/c.dart';",
            "DartLocalPackage",
        ),
        (
            "name: shop\ndependencies:\n  core:\n    path: ../core\n    other: x\n",
            "import 'package:core/c.dart';",
            "DartLocalPackage",
        ),
    ];
    for (pubspec, source, name) in cases {
        let found = run(&[
            ("pubspec.yaml", pubspec),
            ("lib/a.dart", source),
            ("lib/b.dart", ""),
        ]);
        let rows = gaps(&found);
        assert_eq!(rows.get(name), Some(&1), "{pubspec}{source}: {rows:?}");
        assert!(!found.coverage.full_scope);
    }
}

/// #1539: a local package or a workspace that no import reaches adds no edge, and a hosted, SDK
/// or remote git dependency is external (AD-800).
#[test]
fn an_unused_local_package_and_an_external_dependency_keep_the_full_scope() {
    let cases = [
        (
            "name: shop\ndependencies:\n  http: ^1.2.0\ndev_dependencies:\n  lints:\n    path: ../../lints\n",
            "import 'package:http/http.dart';",
        ),
        ("name: shop\nresolution: workspace\n", "import 'b.dart';"),
        (
            "name: shop\ndependencies:\n  http: ^1.2.0\n  flutter:\n    sdk: flutter\n  \
             tool:\n    git: https://github.com/a/tool.git\n  pin:\n    git:\n      url: git@github.com:a/pin.git\n",
            "import 'package:http/http.dart';\nimport 'package:flutter/material.dart';\n\
             import 'package:tool/tool.dart';\nimport 'package:pin/pin.dart';",
        ),
    ];
    for (pubspec, source) in cases {
        let found = run(&[
            ("pubspec.yaml", pubspec),
            ("lib/a.dart", source),
            ("lib/b.dart", ""),
        ]);
        assert!(
            found.coverage.full_scope,
            "{pubspec}: {:#?}",
            found.unknowns
        );
    }
}

#[test]
fn a_workspace_member_outside_the_scan_is_external() {
    let found = run(&[
        ("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"),
        ("other/pubspec.yaml", "name: other\nresolution: workspace\n"),
        ("lib/a.dart", "import 'package:async/a.dart';"),
    ]);
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert!(found
        .inputs
        .iter()
        .any(|input| input.path == "other/pubspec.yaml"));
}

#[test]
fn workspace_resolution_without_a_complete_disjoint_map_is_a_gap() {
    for files in [
        vec![("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"), ("lib/a.dart", "")],
        vec![("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"), ("other/pubspec.yaml", "name: shop\nresolution: workspace\n"), ("lib/a.dart", "")],
        vec![("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"), ("other/pubspec.yaml", "name: other\nresolution: workspace\ndependency_overrides:\n  dep:\n    path: ../lib\n"), ("lib/a.dart", "")],
        vec![("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"), ("other/pubspec.yaml", "name: other\nresolution: workspace\n"), ("other/pubspec_overrides.yaml", "dependency_overrides: {}"), ("lib/a.dart", "")],
        vec![("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"), ("other/pubspec.yaml", "name: other\nresolution: workspace\n"), ("pubspec.lock", "packages: {}"), ("lib/a.dart", "")],
    ] {
        let found = run(&files);
        assert!(gaps(&found).contains_key("DartWorkspace"), "{:#?}", found.unknowns);
        assert!(!found.coverage.full_scope);
    }
    // AD-800: an imported member is a gap at its import.
    let found = run(&[
        ("pubspec.yaml", "name: shop\nworkspace:\n  - other\n"),
        ("other/pubspec.yaml", "name: other\nresolution: workspace\n"),
        ("lib/a.dart", "import 'package:other/a.dart';"),
    ]);
    assert_eq!(
        gaps(&found).get("DartLocalPackage"),
        Some(&1),
        "{:#?}",
        found.unknowns
    );
}

const WORKSPACE: &str = "name: ws\nenvironment:\n  sdk: ^3.6.0\nworkspace:\n  - app\n  - other\n";
const APP: &str = "name: app\nenvironment:\n  sdk: ^3.6.0\nresolution: workspace\n\
                   dependencies:\n  http: ^1.2.0\n";
const OTHER: &str = "name: other\nenvironment:\n  sdk: ^3.6.0\nresolution: workspace\n";

fn app(files: &[(&str, &str)]) -> Survey {
    let mut all = vec![
        ("pubspec.yaml", WORKSPACE),
        ("app/pubspec.yaml", APP),
        ("other/pubspec.yaml", OTHER),
    ];
    all.extend_from_slice(files);
    run_roots(&all, &["app/lib"])
}

/// #1539: the package of a scan is the nearest `pubspec.yaml` at or above its root; the
/// workspace root above it is read for its members and does not become the package.
#[test]
fn an_app_inside_a_workspace_is_its_own_package() {
    let found = app(&[
        (
            "app/lib/a.dart",
            "import 'package:app/b.dart';\nimport 'package:http/http.dart';\n",
        ),
        ("app/lib/b.dart", ""),
    ]);
    assert!(found.coverage.full_scope, "{:#?}", found.unknowns);
    assert_eq!(
        super::edge_rows(&found),
        ["shop.a import http.http", "shop.a import shop.b"]
    );
    for path in ["pubspec.yaml", "app/pubspec.yaml", "other/pubspec.yaml"] {
        assert!(
            found.inputs.iter().any(|input| input.path == path),
            "{path}"
        );
    }
}

#[test]
fn an_import_of_a_workspace_member_is_a_gap_at_the_import() {
    let found = app(&[("app/lib/a.dart", "import 'package:other/o.dart';\n")]);
    assert_eq!(
        gaps(&found),
        BTreeMap::from([("DartLocalPackage".to_owned(), 1)])
    );
    // The root package of the workspace is a package too.
    let found = app(&[("app/lib/a.dart", "import 'package:ws/w.dart';\n")]);
    assert_eq!(
        gaps(&found),
        BTreeMap::from([("DartLocalPackage".to_owned(), 1)])
    );
}

#[test]
fn a_member_with_a_local_dependency_makes_that_name_local() {
    let other = "name: other\nresolution: workspace\ndependencies:\n  tool:\n    path: ../tool\n";
    let found = run_roots(
        &[
            ("pubspec.yaml", WORKSPACE),
            ("app/pubspec.yaml", APP),
            ("other/pubspec.yaml", other),
            (
                "app/lib/a.dart",
                "import 'package:tool/t.dart';\nimport 'package:meta/meta.dart';\n",
            ),
        ],
        &["app/lib"],
    );
    let expected = BTreeMap::from([
        ("DartLocalPackage".to_owned(), 1),
        ("DartUndeclaredPackage".to_owned(), 1),
    ]);
    assert_eq!(gaps(&found), expected, "{:#?}", found.unknowns);
}

#[test]
fn a_workspace_that_the_survey_cannot_read_holds_each_import() {
    for (root, other) in [
        // The root does not list the app.
        ("name: ws\nworkspace:\n  - other\n", OTHER),
        // A member pubspec is missing.
        (WORKSPACE, ""),
        // A member has its own overrides file.
        (WORKSPACE, "OVERRIDES"),
    ] {
        let mut files = vec![
            ("pubspec.yaml", root),
            ("app/pubspec.yaml", APP),
            ("app/lib/a.dart", "import 'package:http/http.dart';\n"),
        ];
        match other {
            "" => {}
            "OVERRIDES" => {
                files.push(("other/pubspec.yaml", OTHER));
                files.push(("other/pubspec_overrides.yaml", "dependency_overrides: {}\n"));
            }
            text => files.push(("other/pubspec.yaml", text)),
        }
        let found = run_roots(&files, &["app/lib"]);
        assert_eq!(
            gaps(&found).get("DartLocalPackage"),
            Some(&1),
            "{root}: {:#?}",
            found.unknowns
        );
    }
}

#[test]
fn nested_packages_without_a_workspace_keep_their_gap() {
    let found = run_roots(
        &[
            ("pubspec.yaml", "name: shop\n"),
            ("app/pubspec.yaml", "name: app\n"),
            ("app/lib/a.dart", ""),
        ],
        &["app/lib"],
    );
    assert_eq!(
        gaps(&found).get("DartNestedPackage"),
        Some(&1),
        "{:#?}",
        found.unknowns
    );
    // Scan roots in two packages: the snapshot root stays the package, as before.
    let found = run_roots(
        &[
            ("pubspec.yaml", WORKSPACE),
            ("app/pubspec.yaml", APP),
            ("other/pubspec.yaml", OTHER),
            ("app/lib/a.dart", ""),
            ("other/lib/o.dart", ""),
        ],
        &["app/lib", "other/lib"],
    );
    assert!(!found.coverage.full_scope);
    assert!(
        gaps(&found).contains_key("DartNestedPackage"),
        "{:#?}",
        found.unknowns
    );
}

/// #1706: without an own package, `package:shop/b.dart` names the module `shop.b` of another
/// package, which is also the module of `lib/b.dart` in the namespace `shop`. The import is a gap
/// that names the module; no target says that a local module is external.
#[test]
fn an_external_module_with_the_name_of_a_scanned_module_is_a_gap() {
    for pubspec in [None, Some("name: other\n")] {
        let mut files = vec![
            ("lib/a.dart", "import 'package:shop/b.dart';\n"),
            ("lib/b.dart", "class B {}\n"),
        ];
        files.extend(pubspec.map(|text| ("pubspec.yaml", text)));
        let found = run(&files);
        assert_eq!(
            gaps(&found).get("DartUnsupportedUri"),
            Some(&1),
            "{:#?}",
            found.unknowns
        );
        assert!(
            super::edge_rows(&found).is_empty(),
            "{:?}",
            super::edge_rows(&found)
        );
    }
}
