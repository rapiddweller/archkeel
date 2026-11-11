// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the inputs, the file facts and the gaps of the Dart reply. Each source that the scan
// cannot read must be a problem, so that the collection is never complete by omission. The
// expected problems are the ones of `snapshot.read_snapshot` of the Python collector.

use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

use super::*;

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.0.0\n";

fn run(tree: &Tree, roots: &[&str]) -> Result<Discovery, String> {
    let roots: Vec<String> = roots.iter().map(|root| (*root).to_owned()).collect();
    discover(&mut Snapshot::new(&tree.path()), "shop", &roots)
}

fn problems(found: &Discovery) -> Vec<(&str, &str)> {
    let mut list: Vec<(&str, &str)> = found
        .problems
        .iter()
        .map(|item| (item.path.as_str(), item.kind.as_str()))
        .collect();
    list.sort_unstable();
    list
}

#[test]
fn the_sources_of_each_root_are_read_with_their_module_and_digest() {
    let files = [
        ("pubspec.yaml", PUBSPEC),
        ("lib/a.dart", "class A {}"),
        ("lib/src/b-c.g.dart", ""),
        ("lib/readme.md", ""),
        ("bin/main.dart", "void main() {}"),
    ];
    let tree = Tree::new(&files);
    let found = run(&tree, &["lib", "bin"]).unwrap();
    let names: Vec<(&str, &str)> = found
        .sources
        .iter()
        .map(|source| (source.rel_path.as_str(), source.module.as_str()))
        .collect();
    let expected = [
        ("bin/main.dart", "shop.main"),
        ("lib/a.dart", "shop.a"),
        ("lib/src/b-c.g.dart", "shop.src.b_c_g"),
    ];
    assert_eq!(names, expected);
    assert_eq!(found.sources[1].digest, sha256_hex(b"class A {}"));
    assert_eq!(found.package_name, "shop");
    assert_eq!(found.sdk.as_deref(), Some("^3.0.0"));
    assert_eq!(found.pubspec_digest, Some(sha256_hex(PUBSPEC.as_bytes())));
    assert!(found.problems.is_empty());
}

#[test]
fn a_root_at_the_snapshot_root_names_modules_from_the_root() {
    let tree = Tree::new(&[("pubspec.yaml", PUBSPEC), ("lib/a.dart", "")]);
    let found = run(&tree, &["."]).unwrap();
    assert_eq!(found.sources[0].rel_path, "lib/a.dart");
    assert_eq!(found.sources[0].module, "shop.lib.a");
}

#[test]
fn each_unreadable_source_is_a_problem() {
    let files = [
        ("lib/9bad.dart", ""),
        ("lib/a-b.dart", ""),
        ("lib/a_b.dart", ""),
        ("lib/.dart_tool/x.dart", ""),
        ("lib/sub/pubcache/y.dart", ""),
    ];
    let tree = Tree::new(&files);
    let found = run(&tree, &["lib", "missing"]).unwrap();
    let expected = [
        ("lib/.dart_tool", "ExcludedTreeError"),
        ("lib/9bad.dart", "DartModuleError"),
        ("lib/a-b.dart", "DartModuleCollision"),
        ("lib/a_b.dart", "DartModuleCollision"),
        ("lib/sub/pubcache", "ExcludedTreeError"),
        ("missing", "SelectedRootError"),
        ("pubspec.yaml", "PubspecMissing"),
    ];
    assert_eq!(problems(&found), expected);
    let collision = found
        .problems
        .iter()
        .find(|item| item.kind == ExceptionName::DartModuleCollision)
        .unwrap();
    assert_eq!(
        collision.message,
        "shop.a_b maps from lib/a-b.dart, lib/a_b.dart"
    );
    // A colliding source stays a source, as in the Python collector.
    assert_eq!(found.sources.len(), 2);
    assert_eq!(found.package_name, "");
}

#[cfg(unix)]
#[test]
fn a_link_is_a_problem_and_is_never_followed() {
    use std::os::unix::fs::symlink;

    let tree = Tree::new(&[
        ("pubspec.yaml", PUBSPEC),
        ("lib/a.dart", ""),
        ("other/b.dart", ""),
    ]);
    symlink(
        tree.root.join("lib/a.dart"),
        tree.root.join("lib/link.dart"),
    )
    .unwrap();
    symlink(tree.root.join("other"), tree.root.join("lib/linked")).unwrap();
    symlink(tree.root.join("other"), tree.root.join("alias")).unwrap();
    let found = run(&tree, &["lib", "alias"]).unwrap();
    let expected = [
        ("alias", "DartSourceLink"),
        ("lib/link.dart", "DartSourceLink"),
        ("lib/linked", "DartSourceLink"),
    ];
    assert_eq!(problems(&found), expected);
    assert_eq!(found.sources.len(), 1);
}

#[cfg(unix)]
#[test]
fn a_pubspec_link_stops_the_collection() {
    let tree = Tree::new(&[("real.yaml", PUBSPEC), ("lib/a.dart", "")]);
    std::os::unix::fs::symlink(tree.root.join("real.yaml"), tree.root.join("pubspec.yaml"))
        .unwrap();
    let error = run(&tree, &["lib"]).unwrap_err();
    assert_eq!(
        error,
        "regular pubspec.yaml is required inside the snapshot"
    );
}

#[test]
fn a_pubspec_without_a_valid_name_stops_the_collection() {
    let tree = Tree::new(&[("pubspec.yaml", "name: 9x\n"), ("lib/a.dart", "")]);
    let error = run(&tree, &["lib"]).unwrap_err();
    assert_eq!(error, "pubspec.yaml must declare a valid package name");
}

#[test]
fn a_source_over_the_size_limit_is_a_problem_and_not_a_source() {
    let large = "a".repeat(archkeel_snapshot::MAX_FILE_BYTES as usize + 1);
    let tree = Tree::new(&[("pubspec.yaml", PUBSPEC), ("lib/big.dart", &large)]);
    let found = run(&tree, &["lib"]).unwrap();
    assert!(found.sources.is_empty());
    assert_eq!(problems(&found), [("lib/big.dart", "SnapshotError")]);
    assert_eq!(
        found.problems[0].message,
        "source file is over the size limit of 4194304 bytes"
    );
}

use archkeel_facts::identity::sha256_hex;
