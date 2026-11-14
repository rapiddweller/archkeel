// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! AD-488: the project source under the scan roots, without the TSConfig.

use super::project_sources;
use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

fn sources(files: &[(&str, &str)], roots: &[&str], outputs: &[&str]) -> Vec<String> {
    let tree = Tree::new(files);
    let mut snapshot = Snapshot::new(&tree.path());
    let roots: Vec<String> = roots.iter().map(|root| (*root).to_owned()).collect();
    let outputs: Vec<String> = outputs.iter().map(|out| (*out).to_owned()).collect();
    project_sources(&mut snapshot, &roots, &outputs)
}

#[test]
fn each_source_suffix_under_a_root_is_project_source_and_other_files_are_not() {
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

#[test]
fn installed_packages_build_output_and_emitted_files_are_not_project_source() {
    let found = sources(
        &[
            ("src/a.ts", ""),
            ("src/a.js", ""),
            ("src/a.d.ts", ""),
            ("src/b.mts", ""),
            ("src/b.mjs", ""),
            ("src/node_modules/p/index.ts", ""),
            ("src/x/bower_components/q.js", ""),
            ("src/jspm_packages/r.ts", ""),
            ("src/out/s.js", ""),
            ("src/outer/t.ts", ""),
        ],
        &["src"],
        &["src/out"],
    );
    assert_eq!(found, ["src/a.ts", "src/b.mts", "src/outer/t.ts"]);
}

#[test]
fn an_output_directory_that_holds_a_root_hides_nothing_and_a_file_root_counts() {
    let files = [("src/a.ts", ""), ("main.ts", ""), ("main.css", "")];
    assert_eq!(sources(&files, &["src"], &["."]), ["src/a.ts"]);
    assert_eq!(sources(&files, &["main.ts"], &[]), ["main.ts"]);
    assert!(sources(&files, &["main.css"], &[]).is_empty());
}
