// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! AD-488: the project source under the scan roots, without the TSConfig.

use std::collections::BTreeSet;

use super::project_sources;
use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

fn sources(files: &[(&str, &str)], roots: &[&str], used: &[&str]) -> Vec<String> {
    let tree = Tree::new(files);
    let mut snapshot = Snapshot::new(&tree.path());
    let roots: Vec<String> = roots.iter().map(|root| (*root).to_owned()).collect();
    let used: BTreeSet<String> = used.iter().map(|file| (*file).to_owned()).collect();
    project_sources(&mut snapshot, &roots, &used)
}

#[test]
fn each_source_suffix_in_any_case_is_project_source_and_other_files_are_not() {
    let found = sources(
        &[
            ("src/a.ts", ""),
            ("src/b.tsx", ""),
            ("src/c.mts", ""),
            ("src/d.cts", ""),
            ("src/e.d.ts", ""),
            ("src/f.js", ""),
            ("src/g.mjs", ""),
            ("src/h.cjs", ""),
            ("src/i.jsx", ""),
            ("src/.hidden/j.ts", ""),
            ("src/k.min.js", ""),
            ("src/L.TS", ""),
            ("src/data.json", ""),
            ("src/style.css", ""),
            ("src/README", ""),
            ("other/o.ts", ""),
        ],
        &["src"],
        &[],
    );
    let expected = [
        "src/.hidden/j.ts",
        "src/L.TS",
        "src/a.ts",
        "src/b.tsx",
        "src/c.mts",
        "src/d.cts",
        "src/e.d.ts",
        "src/f.js",
        "src/g.mjs",
        "src/h.cjs",
        "src/i.jsx",
        "src/k.min.js",
    ];
    assert_eq!(found, expected);
}

/// A name does not prove emitted output, and a build output directory can hold written code.
#[test]
fn emitted_names_and_build_output_are_project_source() {
    let found = sources(
        &[
            ("src/a.ts", ""),
            ("src/a.js", ""),
            ("src/a.d.ts", ""),
            ("src/a.tsx", ""),
            ("src/out/s.js", ""),
            ("src/out/t.ts", ""),
        ],
        &["src"],
        &[],
    );
    let expected = [
        "src/a.d.ts",
        "src/a.js",
        "src/a.ts",
        "src/a.tsx",
        "src/out/s.js",
        "src/out/t.ts",
    ];
    assert_eq!(found, expected);
}

#[test]
fn only_an_installed_directory_beside_its_manifest_and_unused_is_not_project_source() {
    let files = [
        ("src/package.json", "{}"),
        ("src/node_modules/p/index.ts", ""),
        ("src/jspm_packages/q/index.ts", ""),
        ("src/bower.json", "{}"),
        ("src/bower_components/r/index.js", ""),
        ("src/b/node_modules/local/index.ts", ""),
        ("src/c/bower_components/s/index.js", ""),
        ("src/c/package.json", "{}"),
    ];
    let without_manifest = [
        "src/b/node_modules/local/index.ts",
        "src/c/bower_components/s/index.js",
    ];
    assert_eq!(sources(&files, &["src"], &[]), without_manifest);
    let used = sources(&files, &["src"], &["src/node_modules/p/index.ts"]);
    let expected = [
        "src/b/node_modules/local/index.ts",
        "src/c/bower_components/s/index.js",
        "src/node_modules/p/index.ts",
    ];
    assert_eq!(used, expected);
}

/// A directory that a link reaches first through an exempt path is still walked by its own path.
#[cfg(unix)]
#[test]
fn an_exempt_directory_marks_no_real_path_as_seen() {
    let tree = Tree::new(&[("package.json", "{}"), ("lib/evil.ts", "")]);
    let root = std::path::Path::new(&tree.path()).to_path_buf();
    let linked = std::os::unix::fs::symlink(root.join("lib"), root.join("node_modules"));
    assert!(linked.is_ok());
    let mut snapshot = Snapshot::new(&tree.path());
    let found = project_sources(&mut snapshot, &[".".to_owned()], &BTreeSet::new());
    assert_eq!(found, ["lib/evil.ts"]);
}

#[test]
fn a_file_root_counts_by_its_suffix() {
    let files = [("src/a.ts", ""), ("main.ts", ""), ("main.css", "")];
    assert_eq!(sources(&files, &["main.ts"], &[]), ["main.ts"]);
    assert!(sources(&files, &["main.css"], &[]).is_empty());
}
