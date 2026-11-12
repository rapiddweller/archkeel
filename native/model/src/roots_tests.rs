// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scan-root checks of `ir/coverage.py`, case by case (AD-384).

use super::Roots;

fn roots<'a>(roots: &'a [String], files: &[(&'a str, &'a str)]) -> Roots<'a> {
    Roots::new(roots, files.to_vec())
}

fn texts(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

#[test]
fn a_root_holds_the_files_below_it_and_no_other() {
    let given = texts(&["src", "./lib/"]);
    let found = roots(&given, &[]);
    assert!(found.under("src/a.rs"));
    assert!(found.under("./src/b/c.rs"));
    assert!(found.under("lib/x.rs"));
    assert!(!found.under("srcx/a.rs"));
    assert!(!found.under("/src/a.rs"));
    assert!(!found.under("other/src/a.rs"));
}

#[test]
fn an_absolute_root_holds_nothing_and_a_dot_root_holds_each_relative_file() {
    let absolute = texts(&["/src"]);
    assert!(!roots(&absolute, &[]).under("src/a.rs"));
    let dot = texts(&["."]);
    assert!(roots(&dot, &[]).under("a.rs"));
    assert!(roots(&dot, &[]).under("x/y/a.rs"));
}

#[test]
fn a_package_directory_steps_up_one_part_for_each_module_part_below_the_first() {
    // `app.core.deep.leaf` in `src/core/deep/leaf.rs`: the directory of `app.core` is `src/core`.
    let given = texts(&["src/core"]);
    let files = [
        ("app.core", "src/core/mod.rs"),
        ("app.core.deep.leaf", "src/core/deep/leaf.rs"),
    ];
    let found = roots(&given, &files);
    assert!(found.covers(&["app.core"], &[]));
    // The root `src/core/deep` does not hold the directory `src/core` of the package.
    let narrow = texts(&["src/core/deep"]);
    assert!(!roots(&narrow, &files).covers(&["app.core"], &[]));
}

#[test]
fn a_package_without_a_module_or_a_run_without_roots_is_not_covered() {
    let given = texts(&["src"]);
    let files = [("app.a", "src/a.rs")];
    assert!(!roots(&given, &files).covers(&["app.missing"], &[]));
    assert!(!roots(&[], &files).covers(&["app"], &[]));
    // No package and no exact module still needs a root (`scan_covers_exact_modules`).
    assert!(roots(&given, &files).covers(&[], &[]));
    assert!(!roots(&[], &files).covers(&[], &[]));
}

#[test]
fn an_exact_module_needs_its_own_file_under_a_root() {
    let given = texts(&["src"]);
    let files = [("app.a", "src/a.rs"), ("app.b", "gen/b.rs")];
    assert!(roots(&given, &files).covers(&[], &["app.a"]));
    assert!(!roots(&given, &files).covers(&[], &["app.b"]));
    assert!(!roots(&given, &files).covers(&[], &["app.c"]));
}
