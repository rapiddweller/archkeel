// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads these facts. Each fixture is a small workspace on disk.

use archkeel_wire::protocol::Version;
use serde_json::Value;

use super::*;
use archkeel_snapshot::test_tree::Tree;

const WORKSPACE: &str = "[workspace]\nmembers = [\"base\", \"app\"]\n\
    [workspace.dependencies]\nbase = { path = \"base\", package = \"base-crate\" }\n";
const BASE: &str = "[package]\nname = \"base-crate\"\n[dependencies]\nserde_json = \"1\"\n";
const APP: &str = "[package]\nname = \"app\"\n[dependencies]\nbase = { workspace = true }\n\
    renamed = { package = \"other-crate\", version = \"1\" }\nserde_json = \"1\"\n\
    [features]\ndump = []\n";

fn facts(files: &[(&str, &str)]) -> Facts {
    let root = Tree::new(files);
    let request = Request {
        version: Version::V8,
        root: root.path(),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        roots: vec!["crates".to_owned()],
        namespace: "ns".to_owned(),
        exclude_test_sources: false,
        tsconfig: String::new(),
        bundler: false,
    };
    let provenance = Provenance {
        profile: PROFILE,
        adapter_version: "1".to_owned(),
        code_digest: "d".to_owned(),
        runtime_name: "rust",
        runtime_version: "1.88.0".to_owned(),
        runtime_required: ">=1.88".to_owned(),
    };
    collect(&request, provenance)
}

fn workspace(app_source: &str) -> Facts {
    facts(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", "pub fn f() {}"),
        ("crates/app/Cargo.toml", APP),
        ("crates/app/src/lib.rs", app_source),
    ])
}

fn edges(facts: &Facts) -> Vec<(String, String)> {
    let records = &facts.sections[0].1;
    let mut found: Vec<_> = records
        .iter()
        .map(|r| {
            (
                r.data["source_module"].to_string(),
                r.data["specifier"].to_string(),
            )
        })
        .collect();
    found.sort();
    found
}

/// The reasons in text order: the gaps are in the order of their identities.
fn reasons(facts: &Facts) -> Vec<&str> {
    let mut found: Vec<&str> = facts.gaps.iter().map(|gap| gap.title.as_str()).collect();
    found.sort_unstable();
    found
}

#[test]
fn a_path_to_another_crate_of_the_workspace_is_a_local_edge_to_its_root_module() {
    let facts = workspace("use base::f;\nfn g() { base::f(); }");
    assert_eq!(reasons(&facts), Vec::<&str>::new());
    assert_eq!(facts.imports.len(), 1);
    for target in &facts.imports {
        assert!(matches!(
            target,
            Target::Local { module, file, .. }
                if module == "ns.base_crate" && file == "crates/base/src/lib.rs"
        ));
    }
}

#[test]
fn a_renamed_dependency_is_an_edge_to_the_package_and_a_local_item_is_not_an_edge() {
    let facts = workspace("use renamed::x;\nmod serde_json {}\nfn g() { serde_json::go(); }");
    let targets: Vec<_> = facts
        .imports
        .iter()
        .map(|target| match target {
            Target::External { package, .. } => format!("external {package}"),
            other => format!("{other:?}"),
        })
        .collect();
    assert_eq!(targets, ["external other_crate"]);
}

#[test]
fn std_is_a_builtin_edge_and_one_path_gives_one_record() {
    let facts = workspace("use std::fs;\nfn g() { std::fs::read(\"x\"); std::fs::read(\"y\"); }");
    assert!(facts
        .imports
        .iter()
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
        .files
        .iter()
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
    let section: Vec<_> = facts.sections.iter().map(|(name, _)| *name).collect();
    assert_eq!(section, ["imports", "unknowns"]);
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
        ["crates/src/lib.rs", "crates/src/orphan.rs"]
    );
    assert_eq!((facts.files.len(), facts.files_read), (1, 1));
}

#[test]
fn two_runs_give_the_same_facts() {
    let first = workspace("use base::f;\nuse std::io;\nfn g() { serde_json::json!(1); }");
    let second = workspace("use base::f;\nuse std::io;\nfn g() { serde_json::json!(1); }");
    assert_eq!(first, second);
}
