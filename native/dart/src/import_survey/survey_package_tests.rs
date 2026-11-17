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
