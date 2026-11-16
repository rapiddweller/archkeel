// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the module edges. Each fixture is a small workspace on disk.

use super::*;
use crate::collect::tests::{is_declared, run, APP, BASE, WORKSPACE};

const APP_MANIFEST: (&str, &str) = (
    "crates/app/Cargo.toml",
    "[package]\nname = \"app\"\nedition = \"2021\"\n",
);

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
                ImportFact::MacroBody(_) => "macro_body",
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
    // The glob names every name (`*`, AD-604) and binds none; the use leaf has its own binding.
    assert!(found
        .iter()
        .any(|r| r.2 == "ns.app.c" && r.3.as_deref() == Some("*") && r.4.is_none()));
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
            ("ns.app.user", "ns.app.macros"),
            ("ns.app.user", "ns.app.util"),
            ("ns.app.macros", "ns.app.util"),
        ]
    );
    // The edge of the definition is a template: only the call has the path as an import.
    let kinds: Vec<&str> = found.iter().map(|r| r.0).collect();
    assert_eq!(kinds, ["import", "import", "macro_body"]);
}

#[test]
fn a_macro_called_inside_a_macro_body_gives_the_edges_of_both_bodies_to_the_caller() {
    let files = [
        (
            "crates/app/src/lib.rs",
            "mod macros;\nmod user;\nmod one;\nmod two;\n",
        ),
        (
            "crates/app/src/macros.rs",
            "macro_rules! outer { () => { $crate::one::f(); inner!() }; }\n\
             macro_rules! inner { () => { $crate::two::g() }; }",
        ),
        ("crates/app/src/one.rs", "pub fn f() {}"),
        ("crates/app/src/two.rs", "pub fn g() {}"),
        ("crates/app/src/user.rs", "fn t() { outer!(); }"),
    ];
    let found = module_edges(&files);
    let from_user: Vec<&str> = found
        .iter()
        .filter(|r| r.1 == "ns.app.user" && r.0 == "import")
        .map(|r| r.2.as_str())
        .collect();
    assert_eq!(
        from_user,
        ["ns.app.macros", "ns.app.macros", "ns.app.one", "ns.app.two"],
        "{found:?}"
    );
}

#[test]
fn a_path_in_a_serde_string_of_a_macro_body_is_an_edge_of_each_caller() {
    let files = [
        (
            "crates/app/src/lib.rs",
            "mod macros;\nmod user;\nmod util;\n",
        ),
        (
            "crates/app/src/macros.rs",
            "macro_rules! row { () => { #[serde(default = \"crate::util::make\")] struct S; }; }",
        ),
        ("crates/app/src/util.rs", "pub fn make() {}"),
        ("crates/app/src/user.rs", "row!();"),
    ];
    let found = module_edges(&files);
    let kinds: Vec<(&str, &str)> = found.iter().map(|r| (r.0, r.1.as_str())).collect();
    assert!(kinds.contains(&("import", "ns.app.user")), "{found:?}");
    assert!(
        found
            .iter()
            .any(|r| r.0 == "import" && r.2 == "ns.app.util"),
        "{found:?}"
    );
}

#[test]
fn a_call_that_the_scan_cannot_place_and_a_body_that_it_cannot_read_are_unknown_in_the_caller() {
    let files = [
        ("crates/app/src/lib.rs", "mod macros;\nmod a;\nmod b;\n"),
        (
            "crates/app/src/macros.rs",
            "macro_rules! m { () => { $crate::b::f() }; }\n\
             macro_rules! var { ($x:ident) => { $crate::$x::f() }; }",
        ),
        ("crates/app/src/b.rs", "pub fn f() {}"),
        (
            "crates/app/src/a.rs",
            "fn t() { other::wrap! { m!(); } var!(b); }",
        ),
    ];
    let mut all = vec![APP_MANIFEST];
    all.extend_from_slice(&files);
    let facts = run(&all, false);
    let at_a: Vec<&str> = facts
        .gaps
        .iter()
        .filter(|g| g.subjects.iter().any(|s| s == "ns.app.a"))
        .map(|g| g.title.as_str())
        .collect();
    assert!(
        at_a.iter()
            .any(|r| r.contains("m! is called where the scan cannot place it")),
        "{at_a:?}"
    );
    assert!(
        at_a.iter()
            .any(|r| r.contains("var! expands where the scan cannot read")),
        "{at_a:?}"
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

fn gap_titles(files: &[(&str, &str)]) -> Vec<String> {
    let mut all = vec![APP_MANIFEST];
    all.extend_from_slice(files);
    let facts = run(&all, false);
    facts.gaps.iter().map(|g| g.title.clone()).collect()
}

const LOCAL_MACROS: &str =
    "fn one() {\n    macro_rules! m { () => { crate::b::f() }; }\n    m!();\n}\n\
    fn two() {\n    macro_rules! m { () => { crate::c::f() }; }\n    m!();\n}\n";

#[test]
fn a_macro_of_a_function_body_is_scoped_to_that_body_and_its_path_is_an_edge() {
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod b;\nmod c;\n"),
        ("crates/app/src/a.rs", LOCAL_MACROS),
        ("crates/app/src/b.rs", "pub fn f() {}"),
        ("crates/app/src/c.rs", "pub fn f() {}"),
    ];
    assert_eq!(gap_titles(&files), Vec::<String>::new());
    let found = module_edges(&files);
    for target in ["ns.app.b", "ns.app.c"] {
        let edge = |r: &&Row| r.0 == "import" && r.1 == "ns.app.a" && r.2 == target;
        assert_eq!(found.iter().filter(edge).count(), 1, "{target}: {found:?}");
    }
}

#[test]
fn two_macros_that_one_call_sees_are_unknown_and_a_call_outside_the_body_sees_none() {
    let both = LOCAL_MACROS.replace("fn two() {", "fn two() {\n    macro_rules! m { () => {}; }");
    let nested = format!("{both}fn after() {{ m!(); }}\n");
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod b;\nmod c;\n"),
        ("crates/app/src/a.rs", nested.as_str()),
        ("crates/app/src/b.rs", "macro_rules! m { () => {}; }"),
        ("crates/app/src/c.rs", "pub fn f() {}"),
    ];
    let titles = gap_titles(&files);
    // `two` sees its own definition and the one of `b`; `one` and `after` see only the crate-wide one.
    let twice = "The macro m! is defined more than once in the crate";
    assert_eq!(
        titles.iter().filter(|t| *t == twice).count(),
        2,
        "{titles:?}"
    );
}

#[test]
fn a_call_before_the_macro_of_a_body_does_not_see_it() {
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod b;\n"),
        (
            "crates/app/src/a.rs",
            "fn t() {\n    m!();\n    macro_rules! m { () => { crate::b::f() }; }\n}\n",
        ),
        ("crates/app/src/b.rs", "pub fn f() {}"),
    ];
    let found = module_edges(&files);
    assert!(
        found.iter().all(|r| r.2 != "ns.app.b" || r.0 != "import"),
        "{found:?}"
    );
}

/// The route of each record into another module (AD-604): its true hops, and whether each step
/// is proven to the definition.
fn routes(files: &[(&str, &str)]) -> Vec<(String, Vec<String>, Option<bool>)> {
    let mut all = vec![APP_MANIFEST];
    all.extend_from_slice(files);
    let facts = run(&all, false);
    let mut found: Vec<_> = facts
        .imports
        .iter()
        .map(|record| record.data.data())
        .filter(|data| data.source_module.as_str() == "ns.app.a")
        .map(|data| {
            let symbol = data.symbol.clone().unwrap_or_default();
            let hops = data.reexport_chain.clone().unwrap_or_default();
            (symbol, hops, data.route_complete)
        })
        .collect();
    found.sort();
    found
}

#[test]
fn a_route_follows_each_reexport_and_ends_at_a_macro_that_writes_no_import() {
    let made = "macro_rules! def {\n    ($n:ident) => {\n        pub struct $n;\n        impl $n {\n            fn f() { use std::fmt; }\n        }\n    };\n}\ndef!(Made);\n";
    let passed = "macro_rules! pass {\n    ($p:path) => {\n        $(pub use $p;)?\n    };\n}\npass!(crate::c::Shape);\n";
    let files = [
        (
            "crates/app/src/lib.rs",
            "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\npub use b::Shape;\n",
        ),
        ("crates/app/src/b.rs", "pub use crate::c::Shape;\n"),
        ("crates/app/src/c.rs", "pub struct Shape;\n"),
        ("crates/app/src/d.rs", made),
        ("crates/app/src/e.rs", passed),
        (
            "crates/app/src/a.rs",
            "use crate::Shape;\nuse crate::d::Made;\nuse crate::e::Shape as Other;\nuse crate::c::*;\npub fn f(_: Shape, _: Made, _: Other) {}\n",
        ),
    ];
    let hops = |names: &[&str]| names.iter().map(|n| format!("ns.app{n}")).collect();
    // A `use` in a function body of the expansion binds no name of `d`; a `use` at item level of
    // the expansion of `pass!` may publish `Shape` in `e`, so its route is not complete (AD-608).
    assert_eq!(
        routes(&files),
        [
            ("*".to_owned(), Vec::new(), None),
            ("Made".to_owned(), hops(&[".d.Made"]), None),
            (
                "Shape".to_owned(),
                hops(&[".Shape", ".b.Shape", ".c.Shape"]),
                None
            ),
            ("Shape".to_owned(), hops(&[".e.Shape"]), Some(false)),
        ]
    );
}

#[test]
fn the_route_of_a_member_carries_each_root_name_of_its_type() {
    let files = [
        (
            "crates/app/src/lib.rs",
            "mod a;\nmod t;\nmod x;\npub use t::T;\n",
        ),
        ("crates/app/src/t.rs", "pub struct T;\n"),
        (
            "crates/app/src/x.rs",
            "impl crate::t::T {\n    pub fn make() -> Self {\n        crate::t::T\n    }\n}\n",
        ),
        (
            "crates/app/src/a.rs",
            "use crate::t::T;\npub fn f() -> T {\n    T::make()\n}\n",
        ),
    ];
    let hops = |names: &[&str]| names.iter().map(|n| format!("ns.app{n}")).collect();
    // AD-608: the member reaches the block in `x`; the root publishes `T`, so a root entry of
    // `T` covers the call, and the use leaf and the path `T::make` keep the route of `crate::t::T`.
    assert_eq!(
        routes(&files),
        [
            ("T".to_owned(), hops(&[".t.T"]), None),
            ("T".to_owned(), hops(&[".t.T"]), None),
            ("T".to_owned(), hops(&[".x.T", ".T", ".t.T"]), None),
        ]
    );
}

#[test]
fn a_declaration_of_a_child_module_is_no_name_of_its_parent() {
    // AD-614: `Shape` is declared once in `a` and once in its inline module `tests`. The path in
    // `a` resolves by the leaf of `a`; before, the count of the whole file made it UNKNOWN.
    let files = [
        ("crates/app/src/lib.rs", "mod a;\nmod c;\n"),
        ("crates/app/src/c.rs", "pub enum Shape {\n    Round,\n}\n"),
        (
            "crates/app/src/a.rs",
            "use crate::c::Shape;\npub fn f() -> Shape {\n    Shape::Round\n}\nmod tests {\n    use crate::c::Shape;\n    fn g() -> Shape {\n        Shape::Round\n    }\n}\n",
        ),
    ];
    // One record for each distinct path of a file: the leaf and the path `Shape::Round`.
    let shape = Some("Shape".to_owned());
    assert_eq!(
        module_edges(&files),
        [
            (
                "import",
                "ns.app.a".to_owned(),
                "ns.app.c".to_owned(),
                shape.clone(),
                None,
                0
            ),
            (
                "import",
                "ns.app.a".to_owned(),
                "ns.app.c".to_owned(),
                shape.clone(),
                shape,
                0
            ),
        ]
    );
}
