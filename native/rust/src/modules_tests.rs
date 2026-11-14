// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the edges between modules. Each fixture is a small crate on disk; `outcome` reads the
// path as written in one module and says which module it names.

use super::*;
use crate::crates::discover;
use crate::source::walk as list_files;
use crate::tree::walk;
use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

fn outcome(files: &[(&str, &str)], module: &str, path: &str) -> Outcome {
    let mut all = vec![(
        "Cargo.toml",
        "[package]\nname = \"app\"\nedition = \"2021\"\n",
    )];
    all.extend_from_slice(files);
    outcome_in(&all, module, path)
}

/// Like `outcome`, with the manifest in `all`.
fn outcome_in(all: &[(&str, &str)], module: &str, path: &str) -> Outcome {
    let root = Tree::new(all);
    let mut source = Snapshot::new(&root.path());
    let listed = list_files(&mut source, "");
    let workspace = discover(&mut source, &listed, "ns");
    let walked = walk(&mut source, &workspace, false);
    let found = index(&workspace, &walked.modules);
    let module = walked.modules.iter().find(|m| m.module == module).unwrap();
    let frame = found.frame(&module.module).unwrap();
    let reference = module.scan.references.iter().find(|r| r.path == path);
    reference.map_or_else(
        || Outcome::Unknown(format!("no path {path}")),
        |reference| found.resolve(frame, reference),
    )
}

fn edge(module: &str, symbol: Option<&str>, level: i64) -> Outcome {
    Outcome::Edge(Edge {
        module: module.to_owned(),
        lexical: module.to_owned(),
        symbol: symbol.map(str::to_owned),
        level,
    })
}

const TREE: [(&str, &str); 4] = [
    ("src/lib.rs", "mod a;\nmod b;\n"),
    ("src/a.rs", "mod c;\npub fn f() {}"),
    ("src/a/c.rs", "pub fn g() {}"),
    ("src/b.rs", ""),
];

fn with(file: &str, text: &str) -> Vec<(String, String)> {
    TREE.iter()
        .map(|(name, body)| {
            let body = if *name == file { text } else { body };
            ((*name).to_owned(), body.to_owned())
        })
        .collect()
}

fn run(file: &str, text: &str, module: &str, path: &str) -> Outcome {
    let owned = with(file, text);
    let files: Vec<(&str, &str)> = owned
        .iter()
        .map(|(a, b)| (a.as_str(), b.as_str()))
        .collect();
    outcome(&files, module, path)
}

#[test]
fn crate_self_and_super_name_a_module_with_their_level() {
    let b = |text: &str, path: &str| run("src/b.rs", text, "ns.app.b", path);
    assert_eq!(
        b("fn t() { crate::a::f(); }", "crate::a::f"),
        edge("ns.app.a", Some("f"), 0)
    );
    assert_eq!(
        b("fn t() { crate::a::c::g(); }", "crate::a::c::g"),
        edge("ns.app.a.c", Some("g"), 0)
    );
    assert_eq!(
        b("fn t() { self::h(); }", "self::h"),
        edge("ns.app.b", Some("h"), 1)
    );
    assert_eq!(
        b("fn t() { super::a::f(); }", "super::a::f"),
        edge("ns.app.a", Some("f"), 2)
    );
    // A path that ends at a module has no symbol, and `{self}` names its module.
    assert_eq!(
        b("use crate::a::c;", "crate::a::c"),
        edge("ns.app.a.c", None, 0)
    );
    assert_eq!(
        b("use crate::a::{self};", "crate::a"),
        edge("ns.app.a", None, 0)
    );
    assert_eq!(b("use crate as root;", "crate"), edge("ns.app", None, 0));
}

#[test]
fn super_above_the_crate_root_is_unknown() {
    let found = run(
        "src/lib.rs",
        "mod a;\nmod b;\nuse super::x;",
        "ns.app",
        "super::x",
    );
    assert!(matches!(found, Outcome::Unknown(_)), "{found:?}");
}

#[test]
fn a_child_module_name_and_a_use_binding_name_the_module() {
    let a = |text: &str, path: &str| run("src/a.rs", text, "ns.app.a", path);
    assert_eq!(
        a("mod c;\nfn t() { c::g(); }", "c::g"),
        edge("ns.app.a.c", Some("g"), 1)
    );
    let bound = "mod c;\nuse crate::b as bee;\nfn t() { bee::x(); }";
    assert_eq!(a(bound, "bee::x"), edge("ns.app.b", Some("x"), 0));
    // A name that is no module, no binding and no glob gives no edge.
    assert_eq!(
        a("mod c;\nfn t() { Vec::new(); }", "Vec::new"),
        Outcome::None
    );
}

#[test]
fn a_name_that_the_file_declares_twice_is_unknown_never_an_edge() {
    let twice = "mod c;\nstruct c;\nfn t() { c::g(); }";
    let found = run("src/a.rs", twice, "ns.app.a", "c::g");
    assert!(matches!(found, Outcome::Unknown(_)), "{found:?}");
    let bound = "use crate::b;\nfn b() {}\nfn t() { b::x(); }";
    let found = run("src/a.rs", bound, "ns.app.a", "b::x");
    assert!(matches!(found, Outcome::Unknown(_)), "{found:?}");
}

#[test]
fn a_glob_of_a_local_module_brings_in_its_child_modules_and_its_bindings() {
    // `use super::*` in `c` brings the child `c`'s sibling names of `a`: `a` has `mod c`, and a
    // use binding of `a` too.
    let a = "mod c;\nuse crate::b as bee;\n";
    let c = "use super::*;\nfn t() { bee::x(); }";
    let files = [
        ("src/lib.rs", "mod a;\nmod b;\n"),
        ("src/a.rs", a),
        ("src/a/c.rs", c),
        ("src/b.rs", ""),
    ];
    assert_eq!(
        outcome(&files, "ns.app.a.c", "bee::x"),
        edge("ns.app.b", Some("x"), 0)
    );
    let sibling = "use super::*;\nfn t() { c::g(); }";
    let files = [
        ("src/a/d.rs", sibling),
        ("src/a.rs", "mod c;\nmod d;\n"),
        ("src/lib.rs", "mod a;"),
    ];
    let files = [files.as_slice(), &[("src/a/c.rs", "pub fn g() {}")]].concat();
    assert_eq!(
        outcome(&files, "ns.app.a.d", "c::g"),
        edge("ns.app.a.c", Some("g"), 1)
    );
}

#[test]
fn a_glob_that_the_scan_cannot_follow_makes_an_unbound_name_unknown() {
    let text = "use super::super::*;\nfn t() { x::f(); }";
    let found = run("src/b.rs", text, "ns.app.b", "x::f");
    assert!(matches!(found, Outcome::Unknown(_)), "{found:?}");
    // A glob of std or of an enum brings no module, and a use path under a glob is UNKNOWN.
    let text = "use std::collections::*;\nuse crate::a::Kind::*;\nfn t() { x::f(); }";
    assert_eq!(run("src/b.rs", text, "ns.app.b", "x::f"), Outcome::None);
    let text = "use crate::a::*;\nuse x::y;";
    let found = run("src/b.rs", text, "ns.app.b", "x::y");
    assert!(matches!(found, Outcome::Unknown(_)), "{found:?}");
}

#[test]
fn an_inline_module_is_a_lexical_module_of_its_file() {
    let text = "mod inner { pub fn f() {} mod deeper { fn t() { super::f(); crate::b::x(); } } }";
    let lexical = |found: Outcome| {
        let Outcome::Edge(edge) = found else {
            return (found_text(&found), String::new(), 0);
        };
        (edge.module, edge.lexical, edge.level)
    };
    let up = lexical(run(
        "src/a.rs",
        &format!("mod c;\n{text}"),
        "ns.app.a",
        "super::f",
    ));
    assert_eq!(up, ("ns.app.a".to_owned(), "ns.app.a.inner".to_owned(), 2));
    let root = lexical(run(
        "src/a.rs",
        &format!("mod c;\n{text}"),
        "ns.app.a",
        "crate::b::x",
    ));
    assert_eq!(root.0, "ns.app.b");
}

#[test]
fn a_binary_names_the_library_of_its_package_by_the_package_name() {
    let files = [
        ("src/lib.rs", "pub mod util;\n"),
        ("src/util.rs", ""),
        ("src/main.rs", "fn main() { app::util::run(); }"),
    ];
    assert_eq!(
        outcome(&files, "ns.app.bin_app", "app::util::run"),
        edge("ns.app.util", Some("run"), 0)
    );
}

#[test]
fn extern_crate_self_binds_the_root_of_the_crate() {
    let text = "extern crate self as me;\nfn t() { me::a::f(); }";
    assert_eq!(
        run("src/b.rs", text, "ns.app.b", "me::a::f"),
        edge("ns.app.a", Some("f"), 0)
    );
}

fn found_text(found: &Outcome) -> String {
    format!("{found:?}")
}

fn crate_of(edition: &str, a: &'static str) -> Vec<(&'static str, &'static str)> {
    let manifest = if edition.is_empty() {
        "[package]\nname = \"app\"\n".to_owned()
    } else {
        format!("[package]\nname = \"app\"\nedition = \"{edition}\"\n")
    };
    let manifest: &'static str = Box::leak(manifest.into_boxed_str());
    vec![
        ("Cargo.toml", manifest),
        ("src/lib.rs", "mod a;\nmod b;\n"),
        ("src/a.rs", a),
        ("src/b.rs", "pub fn make() {}"),
    ]
}

#[test]
fn edition_2015_starts_a_use_path_and_a_colon_path_at_the_crate_root() {
    let root_edge = edge("ns.app.b", Some("make"), 0);
    for source in ["use b::make;", "fn t() { ::b::make(); }"] {
        let old = crate_of("2015", source);
        assert_eq!(
            outcome_in(&old, "ns.app.a", "b::make"),
            root_edge,
            "{source}"
        );
        // An absent edition is 2015, too.
        let none = crate_of("", source);
        assert_eq!(
            outcome_in(&none, "ns.app.a", "b::make"),
            root_edge,
            "{source}"
        );
    }
    // From 2018 a `::` path names a crate, and a bare `use b` is no module of the root.
    let modern = crate_of("2018", "fn t() { ::b::make(); }");
    assert_eq!(outcome_in(&modern, "ns.app.a", "b::make"), Outcome::None);
}

#[test]
fn a_leaf_that_has_the_name_of_its_own_first_segment_starts_at_a_crate_not_at_itself() {
    let text =
        "use dep::{dep, tool};\nuse dep::kinds::Kind;\nfn f() { Kind::A; tool::run(); dep(); }";
    let files = [("src/lib.rs", text)];
    assert_eq!(outcome(&files, "ns.app", "Kind::A"), Outcome::None);
    assert_eq!(outcome(&files, "ns.app", "tool::run"), Outcome::None);
    assert_eq!(outcome(&files, "ns.app", "dep::kinds::Kind"), Outcome::None);
}

#[test]
fn a_leaf_with_the_name_of_its_first_segment_stays_unknown_when_a_glob_may_bring_in_the_name() {
    let text = "use other::*;\nuse dep::{dep};\nuse dep::kinds::Kind;";
    let files = [("src/lib.rs", text)];
    assert!(matches!(
        outcome(&files, "ns.app", "dep::kinds::Kind"),
        Outcome::Unknown(_)
    ));
}

// The alias of `extern crate self as me;` in the crate root names the root from every module
// (the extern prelude), from a `::` path, and as `crate::me` where the root binds it.
fn aliased(root: &str, text: &str, path: &str) -> Outcome {
    let tree = [
        ("src/lib.rs", root),
        ("src/a.rs", "pub fn f() {}"),
        ("src/b.rs", text),
    ];
    let mut all = vec![(
        "Cargo.toml",
        "[package]\nname = \"app\"\nedition = \"2021\"\n",
    )];
    all.extend_from_slice(&tree);
    outcome_in(&all, "ns.app.b", path)
}

const ALIAS_ROOT: &str = "extern crate self as me;\nmod a;\nmod b;\n";

#[test]
fn the_alias_of_the_root_names_the_root_from_another_module() {
    let want = edge("ns.app.a", Some("f"), 0);
    assert_eq!(
        aliased(ALIAS_ROOT, "fn t() { me::a::f(); }", "me::a::f"),
        want
    );
    assert_eq!(
        aliased(ALIAS_ROOT, "fn t() { ::me::a::f(); }", "me::a::f"),
        want
    );
    let own = "extern crate self as app;\nmod a;\nmod b;\n";
    assert_eq!(aliased(own, "fn t() { ::app::a::f(); }", "app::a::f"), want);
}

#[test]
fn the_alias_of_the_root_is_a_name_of_the_root_module_too() {
    let root = "pub extern crate self as me;\nmod a;\nmod b;\n";
    let want = edge("ns.app.a", Some("f"), 0);
    assert_eq!(
        aliased(root, "fn t() { crate::me::a::f(); }", "crate::me::a::f"),
        want
    );
    assert_eq!(
        aliased(root, "fn t() { super::me::a::f(); }", "super::me::a::f"),
        edge("ns.app.a", Some("f"), 2)
    );
}

#[test]
fn a_name_that_the_file_declares_hides_the_alias_or_is_unknown() {
    let text = "fn me() {}\nfn t() { me::a::f(); }";
    assert!(matches!(
        aliased(ALIAS_ROOT, text, "me::a::f"),
        Outcome::Unknown(_)
    ));
    let local = "mod me { pub mod a { pub fn f() {} } }\nfn t() { me::a::f(); }";
    assert_eq!(
        aliased(ALIAS_ROOT, local, "me::a::f"),
        Outcome::Edge(Edge {
            module: "ns.app.b".to_owned(),
            lexical: "ns.app.b.me.a".to_owned(),
            symbol: Some("f".to_owned()),
            level: 1,
        })
    );
}

#[test]
fn an_alias_that_only_a_nested_module_binds_is_no_prelude_name() {
    let all = [
        (
            "Cargo.toml",
            "[package]\nname = \"app\"\nedition = \"2021\"\n",
        ),
        ("src/lib.rs", "mod a;\nmod b;\n"),
        ("src/a.rs", "extern crate self as me;\npub fn f() {}"),
        ("src/b.rs", "fn t() { me::a::f(); }"),
    ];
    assert_eq!(outcome_in(&all, "ns.app.b", "me::a::f"), Outcome::None);
}
