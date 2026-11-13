// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and the pair gaps of #953. Each fixture is a crate on disk
// with `mod a; mod b; mod c;`, where `c` defines `S` and `b` holds an `impl` of `S`.

use archkeel_facts::GapFact;

use crate::collect::tests::run;

const MANIFEST: (&str, &str) = (
    "crates/app/Cargo.toml",
    "[package]\nname = \"app\"\nedition = \"2021\"\n",
);
const LIB: (&str, &str) = ("crates/app/src/lib.rs", "mod a;\nmod b;\nmod c;\n");
const TYPE: (&str, &str) = ("crates/app/src/c.rs", "pub struct S;\n");

fn b(text: &str) -> (&'static str, String) {
    ("crates/app/src/b.rs", text.to_owned())
}

/// The module edges `a -> b` and the pair gaps of `a`, as (source, target).
fn found(files: &[(&str, String)]) -> (bool, Vec<(String, String)>) {
    let mut all: Vec<(&str, &str)> = vec![MANIFEST, LIB, TYPE];
    all.extend(files.iter().map(|(rel, text)| (*rel, text.as_str())));
    let facts = run(&all, false);
    let edge = facts.imports.iter().any(|record| {
        let data = record.data.data();
        (data.source_module.as_str(), data.target_module.as_str()) == ("ns.app.a", "ns.app.b")
    });
    let pairs = facts.gaps.iter().filter_map(|gap| match &gap.data {
        GapFact::CollectionGap(data) => Some(data),
        _ => None,
    });
    let pairs = pairs
        .filter_map(|data| {
            let source = data.source_module.as_ref()?.as_str().to_owned();
            Some((source, data.module.as_ref()?.as_str().to_owned()))
        })
        .collect();
    (edge, pairs)
}

fn a(text: &str) -> (&'static str, String) {
    ("crates/app/src/a.rs", text.to_owned())
}

fn pair() -> Vec<(String, String)> {
    vec![("ns.app.a".to_owned(), "ns.app.b".to_owned())]
}

const CALL: &str = "pub fn f(s: &crate::c::S) {\n    s.m(1);\n}\n";

#[test]
fn a_path_to_a_member_of_a_foreign_impl_is_an_edge_to_its_module() {
    let impl_b = b("impl crate::c::S {\n    pub fn m() {}\n}\n");
    let found = found(&[
        impl_b,
        a("use crate::c::S;\npub fn f() {\n    S::m();\n}\n"),
    ]);
    assert_eq!(found, (true, Vec::new()));
}

#[test]
fn a_path_to_a_member_that_the_file_of_the_type_defines_is_no_edge_to_another_module() {
    let own = (
        "crates/app/src/c.rs",
        "pub struct S;\nimpl S {\n    pub fn m() {}\n}\n".to_owned(),
    );
    let impl_b = b("impl crate::c::S {\n    pub fn n() {}\n}\n");
    let found = found(&[own, impl_b, a("pub fn f() {\n    crate::c::S::m();\n}\n")]);
    assert_eq!(found, (false, Vec::new()));
}

#[test]
fn a_method_call_that_may_reach_a_foreign_member_is_a_gap_of_the_pair() {
    let impl_b = b("impl crate::c::S {\n    pub(crate) fn m(&self, x: u8) {}\n}\n");
    assert_eq!(found(&[impl_b, a(CALL)]), (false, pair()));
}

#[test]
fn a_call_reaches_no_member_of_another_arity_nor_one_without_self_nor_a_private_one() {
    for member in [
        "pub fn m(&self) {}",
        "pub fn m(x: u8) {}",
        "fn m(&self, x: u8) {}",
    ] {
        let impl_b = b(&format!("impl crate::c::S {{\n    {member}\n}}\n"));
        assert_eq!(found(&[impl_b, a(CALL)]), (false, Vec::new()), "{member}");
    }
}

#[test]
fn a_method_call_in_a_macro_body_or_a_type_that_the_scan_cannot_place_is_a_gap_too() {
    let impl_b = b("impl crate::c::S {\n    pub fn m(&self) {}\n}\n");
    let format = a("pub fn f(s: &crate::c::S) -> String {\n    format!(\"{}\", s.m())\n}\n");
    assert_eq!(found(&[impl_b, format]), (false, pair()));
    let glob = b("use crate::c::*;\nimpl S {\n    pub fn m(&self) {}\n}\n");
    let call = a("pub fn f(s: &crate::c::S) {\n    s.m();\n}\n");
    assert_eq!(found(&[glob, call]), (false, pair()));
}

#[test]
fn a_caller_with_an_edge_to_the_module_of_the_impl_gets_no_gap() {
    let impl_b = b("pub fn g() {}\nimpl crate::c::S {\n    pub fn m(&self, x: u8) {}\n}\n");
    let call = a("use crate::b::g;\npub fn f(s: &crate::c::S) {\n    g();\n    s.m(1);\n}\n");
    assert_eq!(found(&[impl_b, call]), (true, Vec::new()));
}

#[test]
fn a_trait_that_a_glob_brings_in_is_a_gap_when_a_call_may_use_it() {
    let lib = (
        "crates/app/src/lib.rs",
        "mod a;\nmod b;\nmod c;\nuse b::T;\n".to_owned(),
    );
    let trait_b = b("pub trait T {\n    fn m(&self);\n}\n");
    let calls = |body: &str| a(&format!("use super::*;\npub fn f() {{\n    {body}\n}}\n"));
    let found_with = |body: &str| found(&[lib.clone(), trait_b.clone(), calls(body)]);
    assert_eq!(found_with("5u8.m();"), (false, pair()));
    assert_eq!(found_with("5u8.other();"), (false, Vec::new()));
    // A name of unknown kind (here a re-export) may be a trait with any method.
    let reexport = b("pub use crate::c::S as T;\n");
    let unknown = found(&[lib.clone(), reexport, calls("5u8.other();")]);
    assert_eq!(unknown, (false, pair()));
}

#[test]
fn a_path_call_that_the_scan_cannot_resolve_exactly_is_a_gap_of_the_pair() {
    let impl_b = b("impl crate::c::S {\n    pub fn m(&self) {}\n    pub fn new() {}\n}\n");
    for caller in [
        "pub fn f(s: &crate::c::S) {\n    <crate::c::S>::m(s);\n}\n",
        "type Al = crate::c::S;\npub fn f(s: &Al) {\n    Al::m(s);\n}\n",
        "use crate::c::*;\npub fn f() {\n    S::new();\n}\n",
    ] {
        assert_eq!(
            found(&[impl_b.clone(), a(caller)]),
            (false, pair()),
            "{caller}"
        );
    }
    // A renamed `use` names the type exactly: the path is an edge.
    let renamed = a("use crate::c::S as Q;\npub fn f(s: &Q) {\n    Q::m(s);\n}\n");
    assert_eq!(found(&[impl_b, renamed]), (true, Vec::new()));
}

/// The pair gaps of each collection gap of the facts, sorted, as (source, target).
fn pair_gaps(files: &[(&str, String)]) -> Vec<(String, String)> {
    let all: Vec<(&str, &str)> = files
        .iter()
        .map(|(rel, text)| (*rel, text.as_str()))
        .collect();
    let facts = run(&all, false);
    let mut pairs: Vec<(String, String)> = (facts.gaps.iter())
        .filter_map(|gap| match &gap.data {
            GapFact::CollectionGap(d) => Some((
                d.source_module.as_ref()?.as_str().to_owned(),
                d.module.as_ref()?.as_str().to_owned(),
            )),
            _ => None,
        })
        .collect();
    pairs.sort();
    pairs
}

/// AD-418, review B1 of #1121: the core passes a rule over a pair gap only when no gap of the
/// call reaches the target side, so the collector must name each visible candidate of the name.
#[test]
fn a_method_call_gives_a_gap_for_each_foreign_member_of_its_name() {
    let lib = (
        "crates/app/src/lib.rs",
        "mod a;\nmod b;\nmod c;\nmod d;\n".to_owned(),
    );
    let ty = (
        "crates/app/src/c.rs",
        "pub struct S;\npub struct S2;\n".to_owned(),
    );
    let impl_b = b("impl crate::c::S {\n    pub(crate) fn m(&self, x: u8) {}\n}\n");
    let impl_d = (
        "crates/app/src/d.rs",
        "impl crate::c::S2 {\n    pub fn m(&self, x: u8) {}\n}\n".to_owned(),
    );
    let manifest = (MANIFEST.0, MANIFEST.1.to_owned());
    let pairs = pair_gaps(&[manifest, lib, ty, impl_b, impl_d, a(CALL)]);
    let want = |t: &str| ("ns.app.a".to_owned(), t.to_owned());
    assert_eq!(pairs, vec![want("ns.app.b"), want("ns.app.d")]);
}

/// AD-418, review F3 of #1121: a candidate in another crate that the caller names by a renamed
/// dependency (`alias = { package = "core-x" }`) is a gap of the pair, as an unrenamed one is.
#[test]
fn a_method_call_gives_a_gap_for_a_member_of_a_crate_of_a_renamed_dependency() {
    let file = |rel: &'static str, text: &str| (rel, text.to_owned());
    let pairs = pair_gaps(&[
        file(
            "crates/Cargo.toml",
            "[workspace]\nmembers = [\"core-x\", \"app\"]\n",
        ),
        file(
            "crates/core-x/Cargo.toml",
            "[package]\nname = \"core-x\"\nedition = \"2021\"\n",
        ),
        file("crates/core-x/src/lib.rs", "pub struct S;\nmod b;\n"),
        file(
            "crates/core-x/src/b.rs",
            "impl crate::S {\n    pub fn m(&self, x: u8) {}\n}\n",
        ),
        file(
            "crates/app/Cargo.toml",
            "[package]\nname = \"app\"\nedition = \"2021\"\n\
             [dependencies]\nalias = { path = \"../core-x\", package = \"core-x\" }\n",
        ),
        file("crates/app/src/lib.rs", "mod a;\n"),
        file(
            "crates/app/src/a.rs",
            "pub fn f(s: &alias::S) {\n    s.m(1);\n}\n",
        ),
    ]);
    assert_eq!(
        pairs,
        vec![("ns.app.a".to_owned(), "ns.core_x.b".to_owned())]
    );
}
