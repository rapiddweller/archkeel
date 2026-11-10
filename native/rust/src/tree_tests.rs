// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the facts of the collector. Each fixture is a module tree on disk.

use super::*;
use crate::crates::discover;
use crate::source::walk as list_files;
use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

const MANIFEST: (&str, &str) = ("Cargo.toml", "[package]\nname = \"app\"\n");

fn walked(files: &[(&str, &str)]) -> Walked {
    let mut all = vec![MANIFEST];
    all.extend_from_slice(files);
    let root = Tree::new(&all);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    let workspace = discover(&mut source, &listed, "ns");
    walk(&mut source, &workspace, false)
}

fn modules(walked: &Walked) -> Vec<(&str, &str)> {
    let mut found: Vec<_> = walked
        .modules
        .iter()
        .map(|m| (m.module.as_str(), m.rel.as_str()))
        .collect();
    found.sort_unstable();
    found
}

fn reasons(walked: &Walked) -> Vec<&str> {
    walked.problems.iter().map(|p| p.reason.as_str()).collect()
}

#[test]
fn follows_flat_files_folders_and_inline_modules() {
    let found = walked(&[
        (
            "src/lib.rs",
            "mod flat;\nmod folder;\nmod inline { mod deep; }",
        ),
        ("src/flat.rs", "mod child;"),
        ("src/flat/child.rs", ""),
        ("src/folder/mod.rs", "mod leaf;"),
        ("src/folder/leaf.rs", ""),
        ("src/inline/deep.rs", ""),
    ]);
    assert_eq!(reasons(&found), Vec::<&str>::new());
    assert_eq!(
        modules(&found),
        [
            ("ns.app", "src/lib.rs"),
            ("ns.app.flat", "src/flat.rs"),
            ("ns.app.flat.child", "src/flat/child.rs"),
            ("ns.app.folder", "src/folder/mod.rs"),
            ("ns.app.folder.leaf", "src/folder/leaf.rs"),
            ("ns.app.inline.deep", "src/inline/deep.rs"),
        ]
    );
}

#[test]
fn a_path_attribute_names_the_file_and_the_file_owns_its_directory() {
    let found = walked(&[
            ("src/lib.rs", "#[path = \"parts/one.rs\"]\nmod one;\n#[cfg(test)]\n#[path = \"two_tests.rs\"]\nmod two;"),
            ("src/parts/one.rs", "mod nested;"),
            ("src/parts/nested.rs", ""),
            ("src/two_tests.rs", ""),
        ],
    );
    assert_eq!(reasons(&found), Vec::<&str>::new());
    assert_eq!(
        modules(&found),
        [
            ("ns.app", "src/lib.rs"),
            ("ns.app.one", "src/parts/one.rs"),
            ("ns.app.one.nested", "src/parts/nested.rs"),
            ("ns.app.two", "src/two_tests.rs"),
        ]
    );
}

#[test]
fn a_missing_an_ambiguous_and_a_shared_module_file_are_problems() {
    let found = walked(&[
            ("src/lib.rs", "mod missing;\nmod both;\n#[path = \"x.rs\"] mod one;\n#[path = \"x.rs\"] mod two;\n#[path = \"../../escape.rs\"] mod out;"),
            ("src/both.rs", ""),
            ("src/both/mod.rs", ""),
            ("src/x.rs", ""),
        ],
    );
    let found = reasons(&found);
    assert_eq!(
        found,
        [
            "Module file not found: mod missing in src/lib.rs",
            "Module file is ambiguous: mod both in src/lib.rs",
            "The file src/x.rs is the file of two modules",
            "The file src/x.rs is the file of two modules",
            "Module file not found: ../../escape.rs (mod out in src/lib.rs)",
        ]
    );
}

#[test]
fn a_file_with_a_syntax_error_is_a_module_with_a_problem_and_no_facts() {
    let found = walked(&[("src/lib.rs", "mod bad;"), ("src/bad.rs", "fn broken( {")]);
    assert_eq!(
        reasons(&found),
        ["Syntax error in src/bad.rs: unparseable construct at line 1"]
    );
    assert_eq!(
        modules(&found),
        [("ns.app", "src/lib.rs"), ("ns.app.bad", "src/bad.rs")]
    );
}

#[test]
fn a_file_that_no_tree_reaches_is_not_claimed() {
    let found = walked(&[("src/lib.rs", ""), ("src/orphan.rs", "")]);
    assert!(found.claimed.contains("src/lib.rs") && !found.claimed.contains("src/orphan.rs"));
}

#[test]
fn a_raw_identifier_module_has_the_file_name_without_the_prefix() {
    let found = walked(&[("src/lib.rs", "mod r#type;"), ("src/type.rs", "")]);
    assert_eq!(
        modules(&found),
        [("ns.app", "src/lib.rs"), ("ns.app.type", "src/type.rs")]
    );
}

#[test]
fn a_build_script_that_two_crates_name_is_walked_once_and_is_a_problem_of_both() {
    let root = Tree::new(&[
        (
            "a/Cargo.toml",
            "[package]\nname = \"a\"\nbuild = \"../b/build.rs\"\n",
        ),
        ("a/src/lib.rs", ""),
        ("b/Cargo.toml", "[package]\nname = \"b\"\n"),
        ("b/src/lib.rs", ""),
        ("b/build.rs", "use sha2::Digest;"),
    ]);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    let workspace = discover(&mut source, &listed, "ns");
    let found = walk(&mut source, &workspace, false);
    let builds: Vec<_> = found
        .modules
        .iter()
        .filter(|m| m.rel == "b/build.rs")
        .collect();
    assert_eq!(builds.len(), 1);
    assert_eq!(
        (builds[0].module.as_str(), builds[0].crate_index),
        ("ns.b.build_script", 1)
    );
    // The file and the manifest of the second crate carry the reason: both crates are UNKNOWN.
    let both: Vec<_> = found
        .problems
        .iter()
        .map(|p| (p.file.as_str(), p.reason.as_str()))
        .collect();
    let reason = "The file b/build.rs is the file of two crates";
    assert_eq!(both, [("b/build.rs", reason), ("a/Cargo.toml", reason)]);
}

#[test]
fn a_path_attribute_that_leaves_the_crate_is_a_problem_of_both_files() {
    let root = Tree::new(&[
        ("app/Cargo.toml", "[package]\nname = \"app\"\n"),
        (
            "app/src/lib.rs",
            "#[path = \"../../base/src/lib.rs\"] mod b;",
        ),
        ("base/Cargo.toml", "[package]\nname = \"base\"\n"),
        ("base/src/lib.rs", ""),
    ]);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    let workspace = discover(&mut source, &listed, "ns");
    let found = walk(&mut source, &workspace, false);
    let reason = "A path attribute leaves the crate directory: base/src/lib.rs";
    let both: Vec<_> = found
        .problems
        .iter()
        .map(|p| (p.file.as_str(), p.reason.as_str()))
        .collect();
    assert_eq!(
        both,
        [("base/src/lib.rs", reason), ("app/src/lib.rs", reason)]
    );
    let names: Vec<_> = found.modules.iter().map(|m| m.module.as_str()).collect();
    assert_eq!(names, ["ns.app", "ns.base"]);
}

#[test]
fn a_chain_deeper_than_the_limit_is_cut_with_a_reason_and_a_file_that_nests_too_deep_gives_no_facts(
) {
    let mut files = vec![("src/lib.rs".to_owned(), "mod c0;".to_owned())];
    for i in 0..MAX_MODULE_DEPTH + 2 {
        files.push((
            format!("src/c{i}.rs"),
            format!("#[path = \"c{}.rs\"] mod c{};", i + 1, i + 1),
        ));
    }
    files.push((
        "src/deep.rs".to_owned(),
        "fn f() { let x = ".to_owned()
            + &"(".repeat(MAX_NESTING + 1)
            + "1"
            + &")".repeat(MAX_NESTING + 1)
            + "; }",
    ));
    files.push(("src/lib.rs".to_owned(), "mod c0;\nmod deep;".to_owned()));
    let borrowed: Vec<(&str, &str)> = files
        .iter()
        .map(|(a, b)| (a.as_str(), b.as_str()))
        .collect();
    let found = walked(&borrowed);
    let reasons = reasons(&found);
    assert!(reasons
        .contains(&format!("Brackets nest deeper than {MAX_NESTING} in src/deep.rs").as_str()));
    let cut =
        format!("Modules nest deeper than {MAX_MODULE_DEPTH} levels: src/c{MAX_MODULE_DEPTH}.rs");
    assert!(reasons.contains(&cut.as_str()), "{reasons:?}");
    // The root, c0 to c63 (depth 1 to 64) and `deep` are read; c64 and below are not.
    assert_eq!(found.modules.len(), MAX_MODULE_DEPTH + 2);
}

#[test]
fn a_test_module_is_claimed_and_not_a_module_when_the_request_excludes_tests() {
    let root = Tree::new(&[
        ("Cargo.toml", "[package]\nname = \"app\"\n"),
        ("src/lib.rs", "#[cfg(test)] mod tests;\nmod prod;"),
        ("src/tests.rs", "mod more;"),
        ("src/tests/more.rs", "fn m() {}"),
        ("src/prod.rs", ""),
        ("src/foo_tests.rs", ""),
    ]);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    let workspace = discover(&mut source, &listed, "ns");
    let found = walk(&mut source, &workspace, true);
    assert_eq!(
        modules(&found),
        [("ns.app", "src/lib.rs"), ("ns.app.prod", "src/prod.rs")]
    );
    let tests: Vec<&str> = found.tests.iter().map(String::as_str).collect();
    assert_eq!(tests, ["src/tests.rs", "src/tests/more.rs"]);
    assert!(found.claimed.contains("src/tests/more.rs"));
    assert!(found.is_excluded("src/tests.rs") && !found.is_excluded("src/foo_tests.rs"));
}

#[test]
fn cfg_alternatives_of_one_module_name_keep_both_files_under_distinct_modules() {
    let found = walked(&[
        (
            "src/lib.rs",
            "#[cfg(unix)]\n#[path = \"a.rs\"]\nmod inner;\n#[cfg(not(unix))]\n#[path = \"b.rs\"]\nmod inner;",
        ),
        ("src/a.rs", "mod leaf;"),
        ("src/b.rs", ""),
        ("src/leaf.rs", ""),
    ]);
    assert_eq!(reasons(&found), Vec::<&str>::new());
    assert_eq!(
        modules(&found),
        [
            ("ns.app", "src/lib.rs"),
            ("ns.app.inner", "src/a.rs"),
            ("ns.app.inner.leaf", "src/leaf.rs"),
            ("ns.app.inner_alt2", "src/b.rs"),
        ]
    );
}

#[test]
fn a_file_that_two_differently_named_modules_load_stays_a_problem() {
    let found = walked(&[
        (
            "src/lib.rs",
            "#[path = \"a.rs\"]\nmod one;\n#[path = \"a.rs\"]\nmod two;",
        ),
        ("src/a.rs", ""),
    ]);
    assert!(reasons(&found)[0].contains("is the file of two modules"));
}
