// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads these facts. Each fixture is a small workspace on disk.

use archkeel_wire::protocol::Version;

use super::*;
use crate::reply::Collected;
use archkeel_facts::envelope::Dirty;
use archkeel_facts::envelope::Target;
use archkeel_facts::envelope::{Profile, Provenance};
use archkeel_facts::request::{RustRequest, RustSettings, Scope, Snapshot};
use archkeel_facts::{ImportFact, Record};
use archkeel_snapshot::test_tree::Tree;
use std::collections::BTreeSet;

pub(crate) const WORKSPACE: &str = "[workspace]\nmembers = [\"base\", \"app\"]\n\
    [workspace.dependencies]\nbase = { path = \"base\", package = \"base-crate\" }\n";
pub(crate) const BASE: &str =
    "[package]\nname = \"base-crate\"\n[dependencies]\nserde_json = \"1\"\n";
pub(crate) const APP: &str =
    "[package]\nname = \"app\"\n[dependencies]\nbase = { workspace = true }\n\
    renamed = { package = \"other-crate\", version = \"1\" }\nserde_json = \"1\"\n\
    [features]\ndump = []\n";

fn facts(files: &[(&str, &str)]) -> Collected {
    run(files, false)
}

pub(crate) fn run(files: &[(&str, &str)], exclude_tests: bool) -> Collected {
    let root = Tree::new(files);
    let request = RustRequest {
        protocol_version: Version::V8,
        snapshot: Snapshot {
            root: root.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["crates".to_owned()],
            namespace: "ns".to_owned(),
            exclude_test_sources: Some(exclude_tests),
        },
        resolver: RustSettings {},
    };
    let provenance = Provenance::native(Profile::Rust, ("1", "d"), ("1.88.0", "1.88"));
    collect(&request, provenance)
}

fn workspace(app_source: &str) -> Collected {
    facts(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", "pub fn f() {}"),
        ("crates/app/Cargo.toml", APP),
        ("crates/app/src/lib.rs", app_source),
    ])
}

/// The record of a dependency that a manifest declares: its path is `<section>: <name>`.
pub(crate) fn is_declared(record: &Record<ImportFact>) -> bool {
    let specifier = record.data.data().specifier.clone().unwrap_or_default();
    specifier.contains("dependencies: ")
}

/// The targets of the edges that source writes: a declared dependency is another edge.
fn source_targets(facts: &Collected) -> Vec<&Target> {
    let declared: BTreeSet<&str> = facts
        .imports
        .iter()
        .filter(|record| is_declared(record))
        .map(|record| record.id.as_str())
        .collect();
    let targets = facts.head.imports.iter();
    targets
        .filter(|target| !declared.contains(target.import_id().as_str()))
        .collect()
}

fn edges(facts: &Collected) -> Vec<(String, String)> {
    let mut found: Vec<_> = facts
        .imports
        .iter()
        .filter(|record| !is_declared(record))
        .map(|r| {
            let data = r.data.data();
            let specifier = data.specifier.clone().unwrap_or_default();
            (
                format!("{:?}", data.source_module.as_str()),
                format!("{specifier:?}"),
            )
        })
        .collect();
    found.sort();
    found
}

/// The reasons in text order: the gaps are in the order of their identities.
fn reasons(facts: &Collected) -> Vec<&str> {
    let mut found: Vec<&str> = facts.gaps.iter().map(|gap| gap.title.as_str()).collect();
    found.sort_unstable();
    found
}

#[test]
fn a_path_to_another_crate_of_the_workspace_is_a_local_edge_to_its_root_module() {
    let facts = workspace("use base::f;\nfn g() { base::f(); }");
    assert_eq!(reasons(&facts), Vec::<&str>::new());
    assert_eq!(source_targets(&facts).len(), 1);
    for target in source_targets(&facts) {
        assert!(matches!(
            target,
            Target::Local { module, file, .. }
                if module.as_str() == "ns.base_crate" && file == "crates/base/src/lib.rs"
        ));
    }
}

#[test]
fn a_renamed_dependency_is_an_edge_to_the_package_and_a_local_item_is_not_an_edge() {
    let facts = workspace("use renamed::x;\nmod serde_json {}\nfn g() { serde_json::go(); }");
    let targets: Vec<_> = source_targets(&facts)
        .into_iter()
        .map(|target| match target {
            Target::External { package, .. } => format!("external {}", package.as_str()),
            other => format!("{other:?}"),
        })
        .collect();
    assert_eq!(targets, ["external other_crate"]);
}

#[test]
fn std_is_a_builtin_edge_and_one_path_gives_one_record() {
    let facts = workspace("use std::fs;\nfn g() { std::fs::read(\"x\"); std::fs::read(\"y\"); }");
    assert!(source_targets(&facts)
        .into_iter()
        .all(|t| matches!(t, Target::Builtin { .. })));
    assert_eq!(
        edges(&facts),
        [
            ("\"ns.app\"".to_owned(), "\"std::fs\"".to_owned()),
            ("\"ns.app\"".to_owned(), "\"std::fs::read\"".to_owned()),
        ]
    );
}

#[test]
fn a_module_is_named_below_the_namespace_and_the_crate() {
    let facts = workspace("mod inner;");
    assert_eq!(
        reasons(&facts),
        ["Module file not found: mod inner in crates/app/src/lib.rs"]
    );
    let modules: Vec<_> = facts
        .head
        .files
        .iter()
        .filter(|f| !f.module.as_str().ends_with(".cargo_toml"))
        .map(|f| (f.module.as_str(), f.package.as_str()))
        .collect();
    assert_eq!(modules, [("ns.app", "ns"), ("ns.base_crate", "ns")]);
}

#[test]
fn each_place_that_cannot_be_read_is_a_gap_with_its_line() {
    let facts = workspace("fn g() {\n    other::make!(a::b);\n}\n#[cfg(unix)]\nmod unix;");
    assert_eq!(
        reasons(&facts),
        [
            "A cfg condition gates a module: cfg(unix)",
            "Module file not found: mod unix in crates/app/src/lib.rs",
            "The macro make! holds a path that the scan cannot read",
        ]
    );
    let lines: Vec<_> = facts
        .evidence
        .iter()
        .filter(|e| e.excerpt.contains("make!"))
        .map(|e| e.line)
        .collect();
    assert_eq!(lines, [2]);
    assert_eq!(facts.head.sections, ["imports", "symbols", "unknowns"]);
}

#[test]
fn a_file_in_no_module_tree_and_a_scan_root_that_is_no_directory_are_gaps() {
    let facts = facts(&[
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", ""),
        ("crates/src/orphan.rs", ""),
    ]);
    assert_eq!(
        reasons(&facts),
        ["Source file is in no module tree: crates/src/orphan.rs"]
    );
    assert_eq!(
        facts.selected_files,
        [
            "crates/Cargo.toml",
            "crates/src/lib.rs",
            "crates/src/orphan.rs"
        ]
    );
    assert_eq!((facts.head.files.len(), facts.files_read), (2, 2));
}

#[test]
fn two_runs_give_the_same_facts() {
    let first = workspace("use base::f;\nuse std::io;\nfn g() { serde_json::json!(1); }");
    let second = workspace("use base::f;\nuse std::io;\nfn g() { serde_json::json!(1); }");
    let (first, second) = (first.encode(Version::V8), second.encode(Version::V8));
    assert_eq!(first, second);
}

#[test]
fn a_declared_dependency_is_an_edge_of_its_crate_with_the_line_of_the_manifest() {
    let manifest = "[package]\nname = \"app\"\n[dependencies]\nbase = { workspace = true }\n\
        [dev_dependencies]\nserde_json = \"1\"\n[build-dependencies]\nrenamed = { package = \"other-crate\", version = \"1\" }\n\
        [target.'cfg(unix)'.dependencies]\nlibc = \"0.2\"\n";
    let facts = facts(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", ""),
        ("crates/app/Cargo.toml", manifest),
        ("crates/app/src/lib.rs", "pub fn f() {}"),
    ]);
    let mut declared: Vec<(String, String, String)> = facts
        .imports
        .iter()
        .filter(|record| is_declared(record))
        .map(|record| {
            let data = record.data.data();
            let evidence = &record.evidence_ids[0];
            let cited = facts
                .evidence
                .iter()
                .find(|e| e.id.as_str() == evidence.as_str());
            let cited = cited.expect("the evidence is cited");
            let at = format!("{}:{}", cited.file, cited.line);
            let specifier = data.specifier.clone().unwrap_or_default();
            (data.source_module.as_str().to_owned(), specifier, at)
        })
        .collect();
    declared.sort();
    let want = |specifier: &str, line: u32| {
        (
            "ns.app.cargo_toml".to_owned(),
            specifier.to_owned(),
            format!("crates/app/Cargo.toml:{line}"),
        )
    };
    let mut expected = vec![
        (
            "ns.base_crate.cargo_toml".to_owned(),
            "dependencies: serde_json".to_owned(),
            "crates/base/Cargo.toml:4".to_owned(),
        ),
        want("dependencies: base", 4),
        want("dev-dependencies: serde_json", 6),
        want("build-dependencies: renamed", 8),
        want("dependencies: libc", 10),
    ];
    expected.sort();
    assert_eq!(declared, expected);
    assert!(reasons(&facts).is_empty(), "{:?}", reasons(&facts));
}

#[test]
fn a_dependency_table_that_the_reader_does_not_know_is_unknown() {
    let manifest = "[package]\nname = \"app\"\n[dependancies]\nbase = \"1\"\n";
    let facts = facts(&[("crates/Cargo.toml", manifest), ("crates/src/lib.rs", "")]);
    assert_eq!(
        reasons(&facts),
        ["A dependency table that the reader does not know: [dependancies] in app"]
    );
}

/// One crate with each form of test code: a sibling file, a `path` file, an inline module that
/// holds a file, a `#[test]` function, the three test targets and a build script.
const TEST_FORMS: [(&str, &str); 11] = [
    ("crates/Cargo.toml", "[package]\nname = \"app\"\nbuild = \"build.rs\"\n[dev-dependencies]\nserde_json = \"1\"\n"),
    ("crates/src/lib.rs",
        "mod prod_tests;\n#[cfg(test)] mod tests;\n#[cfg(test)] #[path = \"lib_cases.rs\"] mod cases;\n\
         #[cfg(test)] mod inline { mod deep; }\n#[test] fn alone() { let _ = serde_json::json!(1); }\n",
    ),
    ("crates/src/prod_tests.rs", "pub fn p() {}"),
    ("crates/src/tests.rs", "fn t() { let _ = serde_json::json!(1); }"),
    ("crates/src/lib_cases.rs", "fn c() { let _ = serde_json::json!(2); }"),
    ("crates/src/inline/deep.rs", "fn d() {}"),
    ("crates/tests/it.rs", "fn i() { let _ = serde_json::json!(3); }"),
    ("crates/benches/b.rs", "fn b() {}"),
    ("crates/examples/e.rs", "fn e() {}"),
    ("crates/build.rs", "fn main() {}"),
    ("crates/src/unreached.rs", "fn u() {}"),
];

fn module_files(facts: &Collected) -> Vec<&str> {
    facts
        .head
        .files
        .iter()
        .map(|file| file.rel_path.as_str())
        .filter(|rel| rel.ends_with(".rs"))
        .collect()
}

#[test]
fn a_request_that_excludes_tests_has_no_test_file_and_no_gap_for_one() {
    let facts = run(&TEST_FORMS, true);
    assert_eq!(
        module_files(&facts),
        [
            "crates/build.rs",
            "crates/src/lib.rs",
            "crates/src/prod_tests.rs"
        ]
    );
    // The unreached file is a gap and stays selected: only test scope leaves.
    assert_eq!(
        facts.selected_files,
        [
            "crates/Cargo.toml",
            "crates/build.rs",
            "crates/src/lib.rs",
            "crates/src/prod_tests.rs",
            "crates/src/unreached.rs"
        ]
    );
    let reasons: Vec<&str> = facts.gaps.iter().map(|g| g.title.as_str()).collect();
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(
        reasons[0].contains("crates/src/unreached.rs"),
        "{reasons:?}"
    );
    // No test code made an edge, and the dev-dependency is no declared edge.
    assert_eq!(facts.imports, []);
}

#[test]
fn a_request_that_keeps_tests_has_each_test_file_and_its_edges() {
    let facts = run(&TEST_FORMS, false);
    assert_eq!(module_files(&facts).len(), 9);
    let specifiers: Vec<String> = facts
        .imports
        .iter()
        .filter_map(|record| record.data.data().specifier.clone())
        .collect();
    assert!(specifiers
        .iter()
        .any(|s| s == "dev-dependencies: serde_json"));
    assert!(facts.imports.len() == 5);
}

#[test]
fn a_scope_with_only_test_files_is_a_gap() {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"app\"\n"),
        ("crates/tests/it.rs", "fn i() {}"),
    ];
    let facts = run(&files, true);
    assert_eq!(module_files(&facts), Vec::<&str>::new());
    let reasons: Vec<&str> = facts.gaps.iter().map(|g| g.title.as_str()).collect();
    assert_eq!(reasons, [crate::test_scope::NO_PRODUCTION_SOURCE]);
}

#[test]
fn a_production_target_in_a_test_directory_is_a_gap_and_never_silent() {
    let files = [
        (
            "crates/Cargo.toml",
            "[package]\nname = \"app\"\n[[bin]]\nname = \"x\"\npath = \"tests/x.rs\"\n",
        ),
        ("crates/src/lib.rs", "mod helper;"),
        ("crates/src/helper.rs", ""),
        ("crates/tests/x.rs", "fn main() {}"),
    ];
    let facts = run(&files, true);
    assert_eq!(
        module_files(&facts),
        ["crates/src/helper.rs", "crates/src/lib.rs"]
    );
    let reasons: Vec<&str> = facts.gaps.iter().map(|g| g.title.as_str()).collect();
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(reasons[0].contains("crates/tests/x.rs"), "{reasons:?}");
    // Without the flag the target is a module as before.
    assert_eq!(module_files(&run(&files, false)).len(), 3);
}

#[test]
fn a_production_module_file_in_a_test_directory_is_a_gap() {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"app\"\n"),
        ("crates/src/lib.rs", "mod helpers;"),
        ("crates/src/helpers/mod.rs", "mod tests;"),
        ("crates/src/helpers/tests/mod.rs", ""),
    ];
    let facts = run(&files, true);
    let reasons: Vec<&str> = facts.gaps.iter().map(|g| g.title.as_str()).collect();
    assert_eq!(reasons.len(), 1, "{reasons:?}");
    assert!(reasons[0].contains("helpers/tests/mod.rs"), "{reasons:?}");
}
