// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the module edges. Each fixture is a small workspace on disk.

use super::super::tests::{is_declared, run, APP, BASE, WORKSPACE};
use super::*;

const APP_MANIFEST: (&str, &str) = ("crates/app/Cargo.toml", "[package]\nname = \"app\"\n");

/// The module edges: (kind, source, target, symbol, binding, level) without the crate edges.
type Row = (
    &'static str,
    String,
    String,
    Option<String>,
    Option<String>,
    i64,
);

fn module_edges(files: &[(&str, &str)]) -> Vec<Row> {
    let mut all = vec![APP_MANIFEST];
    all.extend_from_slice(files);
    let facts = run(&all, false);
    let mut rows: Vec<Row> = facts
        .imports
        .iter()
        .filter(|record| {
            record
                .data
                .data()
                .target_module
                .as_str()
                .starts_with("ns.app")
        })
        .filter(|record| {
            record
                .data
                .data()
                .source_module
                .as_str()
                .starts_with("ns.app")
        })
        .map(|record| {
            let data = record.data.data();
            let kind = match &record.data {
                ImportFact::Reexport(_) => "reexport",
                _ => "import",
            };
            (
                kind,
                data.source_module.as_str().to_owned(),
                data.target_module.as_str().to_owned(),
                data.symbol.clone(),
                data.binding.clone(),
                data.relative_level,
            )
        })
        .collect();
    rows.sort();
    rows
}

fn row(kind: &'static str, from: &str, to: &str, symbol: Option<&str>, level: i64) -> Row {
    let binding = symbol.map(str::to_owned);
    (
        kind,
        from.to_owned(),
        to.to_owned(),
        symbol.map(str::to_owned),
        binding,
        level,
    )
}

#[test]
fn a_use_a_path_and_a_reexport_inside_a_crate_are_import_and_reexport_records() {
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod b;\n"),
        (
            "crates/app/src/a.rs",
            "pub use crate::b::Shape;\nfn t() { super::b::make(); }",
        ),
        ("crates/app/src/b.rs", "pub struct Shape;\npub fn make() {}"),
    ];
    let found = module_edges(&files);
    let path: Row = (
        "import",
        "ns.app.a".to_owned(),
        "ns.app.b".to_owned(),
        Some("make".to_owned()),
        None,
        2,
    );
    let shape = row("reexport", "ns.app.a", "ns.app.b", Some("Shape"), 0);
    assert_eq!(found, [path, shape]);
}

#[test]
fn a_forbidden_edge_behind_a_local_name_a_glob_and_a_path_module_is_still_an_edge() {
    let files = [
        (
            "crates/app/src/lib.rs",
            "mod a;\nmod b;\n#[path = \"other.rs\"]\nmod c;\n",
        ),
        ("crates/app/src/b.rs", "pub fn make() {}"),
        ("crates/app/src/other.rs", "pub fn go() {}"),
        (
            "crates/app/src/a.rs",
            "use crate::b as local;\nuse crate::c::*;\nfn t() { local::make(); }",
        ),
    ];
    let found = module_edges(&files);
    let targets: BTreeSet<&str> = found.iter().map(|r| r.2.as_str()).collect();
    assert_eq!(targets, BTreeSet::from(["ns.app.b", "ns.app.c"]));
    // The glob has no symbol and the use leaf has its own binding.
    assert!(found
        .iter()
        .any(|r| r.2 == "ns.app.c" && r.3.is_none() && r.4.is_none()));
}

#[test]
fn a_macro_call_is_an_edge_to_the_module_of_the_macro_and_to_the_modules_of_its_body() {
    let files = [
        (
            "crates/app/src/lib.rs",
            "#[macro_use]\nmod macros;\nmod user;\nmod util;\n",
        ),
        (
            "crates/app/src/macros.rs",
            "macro_rules! build { () => { $crate::util::make() }; }",
        ),
        ("crates/app/src/util.rs", "pub fn make() {}"),
        ("crates/app/src/user.rs", "fn t() { build!(); }"),
    ];
    let found = module_edges(&files);
    let pairs: Vec<(&str, &str)> = found.iter().map(|r| (r.1.as_str(), r.2.as_str())).collect();
    assert_eq!(
        pairs,
        [
            ("ns.app.macros", "ns.app.util"),
            ("ns.app.user", "ns.app.macros"),
            ("ns.app.user", "ns.app.util"),
        ]
    );
}

#[test]
fn a_relative_path_in_a_macro_body_and_two_macros_of_one_name_are_unknown() {
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod b;\nmod user;\n"),
        (
            "crates/app/src/a.rs",
            "macro_rules! m { () => { super::b::f() }; }",
        ),
        ("crates/app/src/b.rs", "macro_rules! twice { () => {}; }"),
        (
            "crates/app/src/user.rs",
            "macro_rules! twice { () => {}; }\nfn t() { twice!(); }",
        ),
    ];
    let mut all = vec![APP_MANIFEST];
    all.extend_from_slice(&files);
    let facts = run(&all, false);
    let reasons: Vec<&str> = facts.gaps.iter().map(|g| g.title.as_str()).collect();
    assert!(
        reasons
            .iter()
            .any(|r| r.contains("names crate, super or self")),
        "{reasons:?}"
    );
    assert!(
        reasons
            .iter()
            .any(|r| r.contains("twice! is defined more than once")),
        "{reasons:?}"
    );
}

#[test]
fn a_path_into_another_crate_of_the_workspace_names_the_deepest_module() {
    let facts = run(
        &[
            ("crates/Cargo.toml", WORKSPACE),
            ("crates/base/Cargo.toml", BASE),
            ("crates/base/src/lib.rs", "pub mod deep;"),
            ("crates/base/src/deep.rs", "pub fn f() {}"),
            ("crates/app/Cargo.toml", APP),
            ("crates/app/src/lib.rs", "fn t() { base::deep::f(); }"),
        ],
        false,
    );
    let targets: Vec<&str> = facts
        .imports
        .iter()
        .filter(|record| !is_declared(record))
        .map(|record| record.data.data().target_module.as_str())
        .collect();
    assert_eq!(targets, ["ns.base_crate.deep"]);
}
