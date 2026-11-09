// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: crate resolution. Each fixture is Rust source and the paths that it writes.

use super::*;

fn features() -> BTreeSet<String> {
    BTreeSet::from(["dump".to_owned()])
}

fn scanned(text: &str) -> Scan {
    scan(text, &features()).unwrap()
}

fn paths(text: &str) -> Vec<String> {
    scanned(text)
        .references
        .iter()
        .map(|r| r.path.clone())
        .collect()
}

fn reasons(text: &str) -> Vec<String> {
    scanned(text)
        .concerns
        .iter()
        .map(|c| c.reason.clone())
        .collect()
}

#[test]
fn a_use_tree_gives_one_reference_for_each_leaf() {
    assert_eq!(
        paths("use a::b::{c, d::e as f, g::*, self};\nuse h;\nuse ::i::j;"),
        [
            "a::b::c",
            "a::b::d::e",
            "a::b::g",
            "a::b::self",
            "h",
            "i::j"
        ]
    );
}

#[test]
fn a_qualified_path_in_an_item_or_a_body_is_a_reference() {
    let text = "fn f(x: a::T) -> b::U { let y = c::d(); <x as e::Tr>::go(); single(); y }\n\
                struct S { v: Vec<f::G> }";
    assert_eq!(paths(text), ["a::T", "b::U", "c::d", "e::Tr::go", "f::G"]);
}

#[test]
fn a_reference_has_the_line_column_and_text_of_its_first_segment() {
    let found = scanned("fn f() {\n    let x = serde_json::json!(1);\n}").references;
    let site = &found[0].site;
    assert_eq!(
        (
            found[0].root.as_str(),
            site.line,
            site.column,
            site.excerpt.as_str()
        ),
        ("serde_json", 2, 12, "let x = serde_json::json!(1);")
    );
}

#[test]
fn a_well_known_macro_body_is_read_as_expressions() {
    let text = "fn f() { assert_eq!(a::b(), 1); let _ = format!(\"{}\", c::d); matches!(x, E::A | E::B); }";
    assert_eq!(paths(text), ["a::b", "c::d", "E::A", "E::B"]);
    assert_eq!(reasons(text), Vec::<String>::new());
}

#[test]
fn another_macro_with_a_path_in_its_body_is_unknown() {
    assert_eq!(
        reasons("fn f() { lazy::make!(a::b); }"),
        ["The macro make! holds a path that the scan cannot read"]
    );
    // No path in the body: the macro cannot name a crate.
    assert_eq!(
        reasons("fn f() { make!(a, 1, \"x\"); }"),
        Vec::<String>::new()
    );
}

#[test]
fn macro_rules_and_include_are_unknown() {
    assert_eq!(
        reasons("macro_rules! m { () => { a::b() }; }"),
        ["The macro_rules! definition m is not expanded"]
    );
    assert_eq!(
        reasons("include!(concat!(env!(\"OUT_DIR\"), \"/x.rs\"));"),
        ["The macro include! adds code that the scan does not read"]
    );
}

#[test]
fn a_path_in_an_attribute_is_a_reference_and_a_derive_is_not_unknown() {
    let text = "#[derive(Debug, serde::Serialize)]\n\
                #[serde(with = \"codec::wire\")]\n\
                #[tool::wrap]\n\
                struct S { #[serde(skip)] a: u8 }\n\
                /// Doc with `x::y` in it.\nfn g() {}";
    assert_eq!(
        paths(text),
        ["serde::Serialize", "codec::wire", "tool::wrap"]
    );
    assert_eq!(reasons(text), Vec::<String>::new());
}

#[test]
fn a_mod_declaration_is_a_child_and_an_inline_mod_is_walked() {
    let found = scanned(
        "mod a;\n#[path = \"b/x.rs\"] mod b;\nmod inline { use z::q; mod c; mod d { mod e; } }",
    );
    let children: Vec<_> = found
        .children
        .iter()
        .map(|c| (c.name.as_str(), c.path.as_deref(), c.inline.join("/")))
        .collect();
    assert_eq!(
        children,
        [
            ("a", None, String::new()),
            ("b", Some("b/x.rs"), String::new()),
            ("c", None, "inline".to_owned()),
            ("e", None, "inline/d".to_owned()),
        ]
    );
    assert_eq!(found.references[0].path, "z::q");
    assert_eq!(
        found
            .declared
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        ["a", "b", "inline"]
    );
}

#[test]
fn a_cfg_on_a_module_or_a_use_is_unknown_unless_it_is_test_or_a_declared_feature() {
    let text = "#[cfg(test)] mod t;\n#[cfg(feature = \"dump\")] mod dump;\n\
                #[cfg(unix)] mod unix;\n#[cfg(windows)] use w::x;";
    let reasons = reasons(text);
    assert_eq!(reasons.len(), 2);
    assert!(reasons[0].starts_with("A cfg condition gates a module: cfg(unix)"));
    assert!(reasons[1].starts_with("A cfg condition gates a use: cfg(windows)"));
}

#[test]
fn a_path_attribute_that_is_not_a_literal_is_unknown() {
    assert_eq!(
        reasons("#[path = concat!(\"a\", \".rs\")] mod m;"),
        ["A path attribute is not a string literal"]
    );
}

#[test]
fn a_syntax_error_names_its_line() {
    assert_eq!(
        scan("fn ok() {}\n\nfn broken( {", &features()).unwrap_err(),
        "unparseable construct at line 3"
    );
}

#[test]
fn a_stream_nested_too_deep_is_a_concern_and_not_a_crash() {
    let deep = format!("fn f() {{ m!{}a::b{}; }}", "(".repeat(200), ")".repeat(200));
    let found = reasons(&deep);
    assert_eq!(found, ["The macro m! is nested too deep to read"]);
}

#[test]
fn only_the_type_namespace_hides_a_crate_name() {
    let declared = |text: &str| scanned(text).declared.into_iter().collect::<Vec<_>>();
    // A function, a constant and a static are values: `b::x()` still names the crate `b`.
    assert_eq!(
        declared("fn b() {}\nconst c: u8 = 1;\nstatic d: u8 = 2;\nfn g() { b::x(); }"),
        Vec::<String>::new()
    );
    assert_eq!(
        paths("fn log() {}\nfn g() { log::info!(\"x\"); b::x(); }"),
        ["log::info", "b::x"]
    );
    // A type, a module and a rename are in the namespace of paths.
    assert_eq!(
        declared("struct S;\nenum E {}\nunion U { a: u8 }\ntrait T {}\ntype A = u8;\nmod m {}\nuse a::b as r;"),
        ["A", "E", "S", "T", "U", "m", "r"]
    );
    // A name in a block or in an inline module is local to it.
    assert_eq!(
        declared("fn g() { struct Local; }\nmod inner { struct Hidden; }"),
        ["inner"]
    );
    assert_eq!(
        declared("use crate::a::serde_json;\nuse serde_json;"),
        ["serde_json"]
    );
}

#[test]
fn a_path_with_leading_colons_is_marked_absolute_in_a_use_a_path_and_a_macro() {
    let found = scanned("use ::a::b;\nuse ::{c::d, e::f};\nuse g::h;\nfn f() { ::i::j(); k::l(); ::m::n!(); matches!(x, ::o::P); }");
    let marks: Vec<_> = found
        .references
        .iter()
        .map(|r| (r.path.as_str(), r.absolute))
        .collect();
    assert_eq!(
        marks,
        [
            ("a::b", true),
            ("c::d", true),
            ("e::f", true),
            ("g::h", false),
            ("i::j", true),
            ("k::l", false),
            ("m::n", true),
            ("o::P", true),
        ]
    );
}

#[test]
fn only_the_keys_of_a_path_attribute_hold_paths_and_a_lint_holds_names() {
    let nothing = Vec::<String>::new();
    assert_eq!(
        paths("#[serde(bound = \"T: b::X\")]\nstruct S<T>(T);"),
        ["b::X"]
    );
    assert_eq!(
        reasons("#[serde(bound = \"T: (b::X\")]\nstruct S<T>(T);"),
        ["A string in an attribute holds a path that the scan cannot read"]
    );
    // The reason of a lint is text, and a lint list holds lint names.
    assert_eq!(
        paths("#[expect(clippy::x, reason = \"see b::Y\")]\nfn f() {}"),
        nothing
    );
    assert_eq!(
        paths("#[allow(b::x)]\n#[cfg_attr(test, allow(b::y))]\nfn f() {}"),
        nothing
    );
    assert_eq!(
        paths("#[cfg_attr(test, derive(c::D))]\nstruct S;"),
        ["c::D"]
    );
    // A message, a name or a pattern is no path, and it is no gap either.
    let texts = "#[deprecated(note = \"use b::make\")]\n#[error(\"{}::{} failed\")]\n\
                 #[should_panic(expected = \"a::b\")]\nfn f() {}";
    assert_eq!(paths(texts), nothing);
    assert_eq!(reasons(texts), nothing);
}
