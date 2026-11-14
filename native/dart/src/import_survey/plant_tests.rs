// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). Each test plants a file system
// fault or a request that the survey must not read as complete (AD-450).

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
fn a_request_that_excludes_test_sources_is_refused() {
    let tree = Tree::new(&with_pubspec(&[("lib/a.dart", "")]));
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop", "exclude_test_sources": true},
        "resolver": {"language": "dart"},
    });
    let refused =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap_err();
    assert!(refused.contains("exclude_test_sources"), "{refused}");
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
