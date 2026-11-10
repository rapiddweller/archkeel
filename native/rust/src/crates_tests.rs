// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk of the module trees. Each fixture is a small workspace on disk.

use super::*;
use crate::source::walk as list_files;
use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

fn found(files: &[(&str, &str)]) -> Workspace {
    let root = Tree::new(files);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    discover(&mut source, &listed, "ns")
}

fn roots(krate: &Crate) -> Vec<(&str, &str)> {
    krate
        .roots
        .iter()
        .map(|r| (r.module.as_str(), r.rel.as_str()))
        .collect()
}

#[test]
fn a_package_has_a_primary_root_and_named_secondary_roots() {
    let workspace = found(&[
        ("Cargo.toml", "[workspace]\nmembers = [\"a\"]\n"),
        ("a/Cargo.toml", "[package]\nname = \"my-app\"\n"),
        ("a/src/lib.rs", ""),
        ("a/src/main.rs", ""),
        ("a/src/bin/tool.rs", ""),
        ("a/build.rs", ""),
        ("a/tests/it.rs", ""),
        ("a/examples/demo.rs", ""),
    ]);
    assert_eq!(workspace.problems, []);
    let krate = &workspace.crates[0];
    assert_eq!(krate.ident, "my_app");
    assert_eq!(
        roots(krate),
        [
            ("ns.my_app.build_script", "a/build.rs"),
            ("ns.my_app.example_demo", "a/examples/demo.rs"),
            ("ns.my_app.bin_tool", "a/src/bin/tool.rs"),
            ("ns.my_app", "a/src/lib.rs"),
            ("ns.my_app.bin_my_app", "a/src/main.rs"),
            ("ns.my_app.test_it", "a/tests/it.rs"),
        ]
    );
    assert_eq!(
        krate.primary.as_ref().map(|r| r.rel.as_str()),
        Some("a/src/lib.rs")
    );
}

#[test]
fn without_a_library_the_main_binary_is_primary() {
    let workspace = found(&[
        ("Cargo.toml", "[package]\nname = \"app\"\n"),
        ("src/main.rs", ""),
    ]);
    assert_eq!(roots(&workspace.crates[0]), [("ns.app", "src/main.rs")]);
}

#[test]
fn a_build_script_outside_the_crate_belongs_to_the_crate_that_holds_the_file() {
    let workspace = found(&[
        (
            "a/Cargo.toml",
            "[package]\nname = \"a\"\nbuild = \"../b/build.rs\"\n",
        ),
        ("a/src/lib.rs", ""),
        ("b/Cargo.toml", "[package]\nname = \"b\"\n"),
        ("b/src/lib.rs", ""),
        ("b/build.rs", ""),
    ]);
    let a = &workspace.crates[0];
    assert_eq!(
        roots(a),
        [
            ("ns.a", "a/src/lib.rs"),
            ("ns.a.build_script", "b/build.rs")
        ]
    );
    // The crate that holds the file is walked after `a` here, but it still lists the file.
    assert!(workspace.crates[1]
        .roots
        .iter()
        .any(|r| r.rel == "b/build.rs"));
}

#[test]
fn a_manifest_that_cannot_be_read_or_names_another_lib_is_a_problem() {
    let workspace = found(&[
        ("bad/Cargo.toml", "[package\n"),
        (
            "lib/Cargo.toml",
            "[package]\nname = \"lib\"\n[lib]\nname = \"other\"\n",
        ),
        ("lib/src/lib.rs", ""),
    ]);
    let reasons: Vec<_> = workspace
        .problems
        .iter()
        .map(|p| (p.file.as_str(), p.reason.as_str()))
        .collect();
    assert_eq!(
        reasons,
        [
            ("bad/Cargo.toml", "Cannot read bad/Cargo.toml: expected `]` at line 1"),
            (
                "lib/Cargo.toml",
                "The library name other differs from the package name lib: a path to it is not read"
            ),
        ]
    );
}

#[test]
fn two_crates_with_one_name_are_a_problem() {
    let workspace = found(&[
        ("a/Cargo.toml", "[package]\nname = \"same\"\n"),
        ("b/Cargo.toml", "[package]\nname = \"same\"\n"),
    ]);
    assert_eq!(
        workspace.problems[0].reason,
        "Two crates have the name same"
    );
}
