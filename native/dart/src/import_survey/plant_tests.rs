// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). Each test plants a file system
// fault or a request that the survey must not read as complete (AD-454).

use std::collections::BTreeMap;

use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::{gap_rows, survey};

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";

fn with_pubspec<'a>(files: &[(&'a str, &'a str)]) -> Vec<(&'a str, &'a str)> {
    let mut all = vec![("pubspec.yaml", PUBSPEC)];
    all.extend_from_slice(files);
    all
}

fn gaps(found: &super::Survey) -> BTreeMap<String, usize> {
    gap_rows(found)
}

fn scoped(files: &[(&str, &str)], roots: &[&str], exclude: bool) -> super::Survey {
    let tree = Tree::new(&with_pubspec(files));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": roots, "namespace": "shop", "exclude_test_sources": exclude},
        "resolver": {"language": "dart"},
    });
    survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap()).unwrap()
}

#[test]
fn test_paths_leave_before_module_names_and_collisions() {
    let files = [
        ("lib/domain/a-test.dart", ""),
        ("lib/domain/a_test.dart", ""),
        ("lib/domain/test/9helper.dart", ""),
    ];
    let excluded = scoped(&files, &["lib"], true);
    assert_eq!(
        excluded.excluded,
        ["lib/domain/a_test.dart", "lib/domain/test/9helper.dart"]
    );
    assert_eq!(excluded.coverage.selected_files, ["lib/domain/a-test.dart"]);
    assert!(excluded.coverage.full_scope, "{:?}", excluded.unknowns);

    let default = scoped(&files, &["lib"], false);
    assert!(default.excluded.is_empty());
    assert_eq!(gaps(&default).get("DartModuleCollision"), Some(&2));
    assert_eq!(gaps(&default).get("DartModuleError"), Some(&1));
}

#[test]
fn production_collisions_stay_unknown_with_test_exclusion() {
    let found = scoped(
        &[
            ("lib/domain/a-test.dart", ""),
            ("lib/domain/a_test.dart", ""),
        ],
        &["lib"],
        false,
    );
    assert_eq!(gaps(&found).get("DartModuleCollision"), Some(&2));
    let found = scoped(
        &[("lib/domain/a-b.dart", ""), ("lib/domain/a_b.dart", "")],
        &["lib"],
        true,
    );
    assert_eq!(gaps(&found).get("DartModuleCollision"), Some(&2));
    assert!(!found.coverage.full_scope);
}

#[test]
fn an_import_into_an_excluded_colliding_file_stays_unknown() {
    let found = scoped(
        &[
            ("lib/domain/a-test.dart", "import 'a_test.dart';\n"),
            ("lib/domain/a_test.dart", ""),
        ],
        &["lib"],
        true,
    );
    assert_eq!(found.excluded, ["lib/domain/a_test.dart"]);
    assert_eq!(gaps(&found).get("DartTargetNotSelected"), Some(&1));
    assert!(!found.coverage.full_scope);
}

#[test]
fn separate_roots_name_each_excluded_path_even_when_relative_names_match() {
    let found = scoped(
        &[
            ("one/a.dart", ""),
            ("two/b.dart", ""),
            ("one/test/9helper.dart", ""),
            ("two/test/9helper.dart", ""),
        ],
        &["one", "two"],
        true,
    );
    assert_eq!(
        found.excluded,
        ["one/test/9helper.dart", "two/test/9helper.dart"]
    );
    assert_eq!(found.coverage.selected_files, ["one/a.dart", "two/b.dart"]);
    assert!(found.coverage.full_scope, "{:?}", found.unknowns);
}

#[cfg(unix)]
#[test]
fn a_link_out_of_the_root_and_an_unreadable_directory_are_gaps() {
    use std::os::unix::fs::{symlink, PermissionsExt};
    let tree = Tree::new(&with_pubspec(&[("lib/a.dart", "import 'b.dart';\n")]));
    let outside = Tree::new(&[("b.dart", "")]);
    symlink(outside.root.join("b.dart"), tree.root.join("lib/b.dart")).unwrap();
    std::fs::create_dir(tree.root.join("lib/closed")).unwrap();
    std::fs::write(tree.root.join("lib/closed/c.dart"), "").unwrap();
    let closed = tree.root.join("lib/closed");
    std::fs::set_permissions(&closed, std::fs::Permissions::from_mode(0o000)).unwrap();
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let request = crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap();
    let found = survey(&request);
    std::fs::set_permissions(&closed, std::fs::Permissions::from_mode(0o755)).unwrap();
    let found = found.unwrap();
    let rows = gaps(&found);
    assert_eq!(rows.get("DartSourceLink"), Some(&1), "{rows:?}");
    assert_eq!(rows.get("SnapshotError"), Some(&1), "{rows:?}");
    assert_eq!(rows.get("DartTargetNotSelected"), Some(&1), "{rows:?}");
    assert!(found.imports.is_empty());
}

#[test]
fn a_source_that_is_not_utf8_is_a_gap_and_has_no_module() {
    let tree = Tree::new(&with_pubspec(&[("lib/a.dart", "")]));
    std::fs::write(tree.root.join("lib/b.dart"), b"import 'a.dart';\n// \xff\n").unwrap();
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(
        gaps(&found).get("SyntaxError"),
        Some(&1),
        "{:?}",
        gaps(&found)
    );
    assert_eq!(found.files.len(), 1);
    assert!(found.imports.is_empty());
}

#[test]
fn a_request_excludes_only_recognized_test_sources() {
    let tree = Tree::new(&with_pubspec(&[
        ("lib/a.dart", ""),
        ("lib/latest.dart", ""),
        ("lib/a_test.dart", ""),
        ("lib/test/helper.dart", ""),
    ]));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(
        found.coverage.selected_files,
        ["lib/a.dart", "lib/latest.dart"]
    );
    assert_eq!(found.excluded, ["lib/a_test.dart", "lib/test/helper.dart"]);
    assert!(found.coverage.full_scope, "{:?}", found.unknowns);
}

#[test]
fn a_project_folder_named_test_does_not_exclude_its_library() {
    let tree = Tree::new(&[
        ("packages/test/pubspec.yaml", PUBSPEC),
        ("packages/test/lib/a.dart", ""),
        ("packages/test/lib/a_test.dart", ""),
    ]);
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["packages/test"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(found.coverage.selected_files, ["packages/test/lib/a.dart"]);
    assert_eq!(found.excluded, ["packages/test/lib/a_test.dart"]);
}

#[test]
fn a_nested_package_named_test_does_not_hide_its_library() {
    let tree = Tree::new(&[
        ("pubspec.yaml", PUBSPEC),
        ("packages/test/pubspec.yaml", "name: inner\n"),
        ("packages/test/lib/a.dart", ""),
        ("packages/test/test/a_test.dart", ""),
    ]);
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["."], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(found.coverage.selected_files, ["packages/test/lib/a.dart"]);
    assert_eq!(found.excluded, ["packages/test/test/a_test.dart"]);
    assert!(!found.coverage.full_scope);
}

#[test]
fn separate_package_roots_keep_a_package_named_test() {
    let tree = Tree::new(&[
        ("pubspec.yaml", PUBSPEC),
        ("packages/test/pubspec.yaml", "name: test\n"),
        ("packages/test/lib/a.dart", ""),
        ("packages/other/pubspec.yaml", "name: other\n"),
        ("packages/other/lib/b.dart", ""),
        ("packages/other/test/b_test.dart", ""),
    ]);
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["packages/test", "packages/other"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(
        found.coverage.selected_files,
        ["packages/other/lib/b.dart", "packages/test/lib/a.dart"]
    );
    assert_eq!(found.excluded, ["packages/other/test/b_test.dart"]);
    assert!(!found.coverage.full_scope);
}

#[test]
fn a_selected_test_root_is_excluded_without_excluding_the_library_root() {
    let tree = Tree::new(&with_pubspec(&[
        ("lib/a.dart", ""),
        ("test/helper.dart", ""),
    ]));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib", "test"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(found.coverage.selected_files, ["lib/a.dart"]);
    assert_eq!(found.excluded, ["test/helper.dart"]);
}

#[test]
fn a_library_that_claims_an_excluded_part_stays_unknown() {
    let tree = Tree::new(&with_pubspec(&[
        ("lib/a.dart", "part 'a_test.dart';\n"),
        ("lib/a_test.dart", "part of 'a.dart';\n"),
    ]));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(found.excluded, ["lib/a_test.dart"]);
    assert_eq!(gaps(&found).get("DartTargetNotSelected"), Some(&1));
    assert!(!found.coverage.full_scope);
}

#[test]
fn a_scope_with_only_excluded_tests_is_not_complete() {
    let tree = Tree::new(&with_pubspec(&[("lib/a_test.dart", "")]));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert!(!found.coverage.full_scope, "{:?}", found.coverage);
}

#[cfg(unix)]
#[test]
fn a_linked_package_file_at_the_root_is_a_gap() {
    let tree = Tree::new(&with_pubspec(&[("lib/a.dart", "")]));
    let outside = Tree::new(&[("package_config.json", "{}")]);
    std::os::unix::fs::symlink(
        outside.root.join("package_config.json"),
        tree.root.join("package_config.json"),
    )
    .unwrap();
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop"},
        "resolver": {"language": "dart"},
    });
    let decoded = crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap();
    let found = survey(&decoded).unwrap();
    assert_eq!(
        gaps(&found).get("DartPackageConfig"),
        Some(&1),
        "{:?}",
        gaps(&found)
    );
    assert!(!found.coverage.full_scope);
}
