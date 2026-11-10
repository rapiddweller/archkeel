// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: crate resolution. Each fixture is Rust source and the paths that it writes.

use super::*;

fn features() -> BTreeSet<String> {
    BTreeSet::from(["dump".to_owned()])
}

fn scanned(text: &str) -> Scan {
    scan(text, &features(), false).unwrap()
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
    let found = scanned("fn f() {\n    let x = json_dep::json!(1);\n}").references;
    let site = &found[0].site;
    assert_eq!(
        (
            found[0].root.as_str(),
            site.line,
            site.column,
            site.excerpt.as_str()
        ),
        ("json_dep", 2, 12, "let x = json_dep::json!(1);")
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
fn an_exported_macro_rules_and_include_are_unknown() {
    assert_eq!(
        reasons("#[macro_export]\nmacro_rules! m { () => { a::b() }; }"),
        ["The macro_rules! definition m is exported: it expands in other crates"]
    );
    // A macro that stays in the crate is read as code of the file: its path is a reference.
    assert_eq!(
        reasons("macro_rules! m { () => { a::b() }; }"),
        Vec::<String>::new()
    );
    assert_eq!(paths("macro_rules! m { () => { a::b() }; }"), ["a::b"]);
    assert!(scanned("macro_rules! m { ($c:ident) => { $c::make() }; }")
        .mentioned
        .contains("make"));
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
        found.names.iter().map(String::as_str).collect::<Vec<_>>(),
        ["a", "b", "c", "d", "e", "inline", "q"]
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
        scan("fn ok() {}\n\nfn broken( {", &features(), false).unwrap_err(),
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
fn every_name_that_the_file_declares_or_imports_is_collected_at_any_depth_in_any_namespace() {
    let names = |text: &str| scanned(text).names.into_iter().collect::<Vec<_>>();
    assert_eq!(
        names("fn f() {}\nconst C: u8 = 1;\nstatic D: u8 = 2;\nstruct S;\nenum E {}\nunion U { a: u8 }"),
        ["C", "D", "E", "S", "U", "f"]
    );
    assert_eq!(
        names("trait T {}\ntype A = u8;\nmod m {}\nmacro_rules! mac { () => {} }"),
        ["A", "T", "m", "mac"]
    );
    // A block, an inline module and a `cfg(test)` module are the same file.
    assert_eq!(
        names(
            "fn g() { struct Local; fn inner() {} }\nmod m { pub mod deep { pub struct Hidden; } }"
        ),
        ["Hidden", "Local", "deep", "g", "inner", "m"]
    );
    // A use leaf binds its last name or its alias, in any namespace.
    assert_eq!(
        names("use a::b::c;\nuse a::d as e;\nuse a::f::{self, g};"),
        ["c", "e", "f", "g"]
    );
    assert_eq!(
        names("use json_dep;\nextern crate x as y;\nextern { fn ffi(); static S: u8; }"),
        ["S", "ffi", "json_dep", "y"]
    );
    // A glob and a type parameter bind no name that the scan knows.
    assert_eq!(names("use a::*;\nfn f<T>(x: T) {}"), ["f"]);
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
fn a_message_key_and_a_lint_hold_no_path_and_any_other_key_does() {
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

#[test]
fn a_crate_name_that_the_file_also_names_is_collected_with_its_references_for_the_rule() {
    // The four repros of the review: a module, a type, an import of a type and an import of a
    // function, each beside a use of the crate name. The scan collects both; `resolve` decides.
    for text in [
        "pub mod b { }\n#[cfg(test)] mod tests { fn t() { b::make(); } }",
        "pub struct b;\nmod m { fn t() { b::make(); } }",
        "use self::inner::b;\nmod m { fn t() { b::make(); } }",
        "use crate::util::b;\nfn t() { b::make(); }",
    ] {
        let found = scanned(text);
        assert!(found.names.contains("b"), "{text}");
        assert!(
            found
                .references
                .iter()
                .any(|r| r.path == "b::make" && !r.absolute),
            "{text}"
        );
    }
}

#[test]
fn a_name_that_only_its_own_crate_provides_is_no_shadow_and_any_other_source_is() {
    let shadows = |text: &str| scanned(text).shadows.into_iter().collect::<Vec<_>>();
    let none = Vec::<String>::new();
    // The leaf comes from the crate of the same name: both candidates lie in that crate.
    assert_eq!(shadows("use anyhow::anyhow;"), none);
    assert_eq!(shadows("use indoc::{indoc, formatdoc};"), ["formatdoc"]);
    assert_eq!(shadows("use anyhow::Error as anyhow;"), none);
    assert_eq!(shadows("use anyhow::anyhow as anyhow;"), none);
    assert_eq!(shadows("use ::anyhow::anyhow;"), none);
    assert_eq!(shadows("use anyhow::{self};"), none);
    // A leaf from another crate, a rename from another crate, an item and a module hide it.
    assert_eq!(shadows("use other::anyhow;"), ["anyhow"]);
    assert_eq!(shadows("use other::Error as anyhow;"), ["anyhow"]);
    assert_eq!(shadows("use anyhow;"), ["anyhow"]);
    assert_eq!(shadows("struct anyhow;"), ["anyhow"]);
    // One foreign source is enough, in either order.
    assert_eq!(shadows("mod anyhow {}\nuse anyhow::anyhow;"), ["anyhow"]);
    assert_eq!(
        shadows("use anyhow::anyhow;\nuse other::anyhow;"),
        ["anyhow"]
    );
    // The name is still collected.
    assert!(scanned("use anyhow::anyhow;").names.contains("anyhow"));
}

#[test]
fn a_raw_identifier_a_one_segment_string_and_an_attribute_expression_are_read() {
    let found = |text: &str| paths(text);
    // r#: in a path, a use leaf, a rename and a macro path.
    assert_eq!(
        found("fn f() { r#base_crate::make(); }"),
        ["base_crate::make"]
    );
    assert_eq!(found("use r#base_crate::make;"), ["base_crate::make"]);
    assert!(scanned("use a::r#b as r#c;").names.contains("c"));
    // A string that is one name, under a key that is no message key.
    assert_eq!(
        found("#[serde(with = \"base_crate\")]\nstruct S;"),
        ["base_crate"]
    );
    assert_eq!(
        found("#[serde(crate = \"base_crate\")]\nstruct S;"),
        ["base_crate"]
    );
    assert_eq!(
        found("#[serde(rename = \"base_crate\")]\nstruct S;"),
        Vec::<String>::new()
    );
    // The value of `key = expression`, also in `doc`; a plain doc text is no code.
    assert_eq!(
        found("#![doc = base_crate::readme!()]"),
        ["base_crate::readme"]
    );
    assert_eq!(
        found("#[path_attr = base_crate::VALUE]\nstruct S;"),
        ["base_crate::VALUE"]
    );
    assert_eq!(
        found(
            "/// uses base_crate::make in prose\nstruct S;\n#[doc = \"base_crate::x\"]\nfn f() {}"
        ),
        Vec::<String>::new()
    );
    assert_eq!(
        found("#[serde_as(as = \"base_crate::X\")]\nstruct S;"),
        ["base_crate::X"]
    );
}

#[test]
fn the_net_collects_names_only_from_macros_attribute_streams_and_strings() {
    let mentioned = |text: &str| scanned(text).mentioned.into_iter().collect::<Vec<_>>();
    let none = Vec::<String>::new();
    // Ordinary code: a local, a field, a parameter and a value cannot be a crate.
    assert_eq!(mentioned("fn f(url: u8) { let x = url + 1; x.url; }"), none);
    assert_eq!(mentioned("struct S { url: String }"), none);
    assert_eq!(
        mentioned("/// url in a doc comment\nfn f() {} // url"),
        none
    );
    // A macro body, an attribute stream and a string stay.
    assert!(mentioned("fn f() { mac!(url); }").contains(&"url".to_owned()));
    assert!(mentioned("#[other::attr(url)]\nstruct S;").contains(&"url".to_owned()));
    assert!(mentioned("const A: &str = \"url::x\";").contains(&"url".to_owned()));
    assert!(mentioned("#[serde(with = \"url\")]\nstruct S;").contains(&"url".to_owned()));
}

fn test_scoped(text: &str) -> Scan {
    scan(text, &features(), true).unwrap()
}

#[test]
fn a_test_item_gives_no_fact_when_the_request_excludes_tests() {
    let text = "use kept_crate::Value;\n\
        #[cfg(test)] use other::Thing;\n\
        #[cfg(test)] mod tests { fn t() { let _ = dev::x(); } }\n\
        #[test] fn alone() { let _ = dev::y(); }\n\
        #[cfg(all(test, unix))] fn gated() { let _ = dev::z(); }\n";
    assert_eq!(paths(text).len(), 5);
    let kept = test_scoped(text);
    let roots: Vec<&str> = kept.references.iter().map(|r| r.root.as_str()).collect();
    assert_eq!(roots, ["kept_crate"]);
    assert!(!kept.names.contains("tests") && !kept.names.contains("alone"));
    assert!(kept.mentioned.iter().all(|name| name != "dev"));
}

#[test]
fn a_cfg_test_module_file_below_a_test_item_is_a_test_child() {
    let text = "#[cfg(test)] mod tests;\n\
        #[cfg(test)] mod inline { mod deep; }\n\
        mod prod;\n";
    let kept = test_scoped(text);
    let found: Vec<(&str, bool, Vec<&str>)> = kept
        .children
        .iter()
        .map(|c| {
            (
                c.name.as_str(),
                c.test,
                c.inline.iter().map(String::as_str).collect(),
            )
        })
        .collect();
    assert_eq!(
        found,
        [
            ("tests", true, vec![]),
            ("deep", true, vec!["inline"]),
            ("prod", false, vec![])
        ]
    );
    // Without the flag the scan is as before: the child is marked, and its facts stay.
    let plain = scanned(text);
    assert_eq!(
        plain.children.iter().map(|c| c.test).collect::<Vec<_>>(),
        [true, false, false]
    );
}

#[test]
fn a_test_member_a_test_statement_and_a_test_attribute_of_a_crate_give_no_fact() {
    let text = "struct S;\n\
        impl S {\n\
            #[cfg(test)] fn t() { let _ = dev::a(); }\n\
            fn keep() { let _ = kept_crate::a(); #[cfg(test)] let _ = dev::b(); #[cfg(test)] dev::c!(); }\n\
        }\n\
        trait T { #[cfg(test)] fn t() { let _ = dev::d(); } fn k() { let _ = kept_crate::b(); } }\n\
        #[tokio::test] async fn run() { let _ = dev::e(); }\n\
        #[rstest] fn case() { let _ = dev::f(); }\n";
    assert!(paths(text).len() > 2);
    let kept = test_scoped(text);
    let roots: Vec<&str> = kept.references.iter().map(|r| r.root.as_str()).collect();
    assert_eq!(roots, ["kept_crate", "kept_crate"]);
    assert!(kept.mentioned.iter().all(|name| name != "dev"));
}
