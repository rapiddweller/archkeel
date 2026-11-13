// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the core passes a rule over a pair gap only when no gap reaches its target side
// (AD-418). A value can reach a caller from a crate that the caller reaches only through another
// crate (`app -> mid -> leaf`); a method call on it can reach a foreign member of `leaf`.
// Review B2 of #1121: each form names its candidate, or the test pins the named limit.

use archkeel_facts::GapFact;

use crate::collect::tests::run;

const LEAF_TYPE: &str = "pub struct S;\nimpl S {\n    pub fn own(&self) -> u8 {\n        3\n    }\n}\npub trait Tr {\n    fn t(&self) -> u8;\n}\nmod b;\n";
const LEAF_IMPL: &str = "impl crate::S {\n    pub fn m(&self) -> u8 {\n        1\n    }\n}\n\
    impl crate::Tr for crate::S {\n    fn t(&self) -> u8 {\n        2\n    }\n}\n";

/// The pair gaps of `app -> mid -> leaf`, where `mid` is `mid_lib` and `app.a` is `a`.
fn pairs(mid_lib: &str, a: &str) -> Vec<(String, String)> {
    let files = [
        (
            "crates/Cargo.toml",
            "[workspace]\nmembers = [\"leaf\", \"mid\", \"app\"]\n",
        ),
        (
            "crates/leaf/Cargo.toml",
            "[package]\nname = \"leaf\"\nedition = \"2021\"\n",
        ),
        ("crates/leaf/src/lib.rs", LEAF_TYPE),
        ("crates/leaf/src/b.rs", LEAF_IMPL),
        (
            "crates/mid/Cargo.toml",
            "[package]\nname = \"mid\"\nedition = \"2021\"\n\
             [dependencies]\nleaf = { path = \"../leaf\" }\n",
        ),
        ("crates/mid/src/lib.rs", mid_lib),
        (
            "crates/app/Cargo.toml",
            "[package]\nname = \"app\"\nedition = \"2021\"\n\
             [dependencies]\nmid = { path = \"../mid\" }\n",
        ),
        ("crates/app/src/lib.rs", "mod a;\n"),
        ("crates/app/src/a.rs", a),
    ];
    let facts = run(&files, false);
    let mut found: Vec<(String, String)> = (facts.gaps.iter())
        .filter_map(|gap| match &gap.data {
            GapFact::CollectionGap(d) => Some((
                d.source_module.as_ref()?.as_str().to_owned(),
                d.module.as_ref()?.as_str().to_owned(),
            )),
            _ => None,
        })
        .collect();
    found.sort();
    found
}

fn leaf() -> Vec<(String, String)> {
    vec![("ns.app.a".to_owned(), "ns.leaf.b".to_owned())]
}

#[test]
fn a_method_call_on_a_value_that_a_dependency_returns_names_the_member_of_its_dependency() {
    let found = pairs(
        "pub fn get() -> leaf::S {\n    leaf::S\n}\n",
        "pub fn f() -> u8 {\n    mid::get().m()\n}\n",
    );
    assert_eq!(found, leaf());
}

#[test]
fn a_method_call_on_a_type_that_a_dependency_re_exports_names_the_member() {
    let found = pairs(
        "pub use leaf::S;\n",
        "pub fn f(s: &mid::S) -> u8 {\n    s.m()\n}\n",
    );
    assert_eq!(found, leaf());
}

#[test]
fn a_method_call_on_a_type_alias_of_a_dependency_names_the_member() {
    let found = pairs(
        "pub type T = leaf::S;\n",
        "pub fn f(s: &mid::T) -> u8 {\n    s.m()\n}\n",
    );
    assert_eq!(found, leaf());
}

#[test]
fn a_method_call_through_deref_names_the_member() {
    let mid = "pub struct W(pub leaf::S);\nimpl std::ops::Deref for W {\n    type Target = leaf::S;\n    \
               fn deref(&self) -> &leaf::S {\n        &self.0\n    }\n}\n";
    let found = pairs(mid, "pub fn f(w: &mid::W) -> u8 {\n    w.m()\n}\n");
    assert_eq!(found, leaf());
}

#[test]
fn a_method_call_on_a_generic_parameter_names_the_member() {
    // `mid` hands a value of `leaf::S` to a generic caller; the call is an inherent call on it.
    let mid = "pub fn with<R>(f: impl Fn(leaf::S) -> R) -> R {\n    f(leaf::S)\n}\n";
    let found = pairs(mid, "pub fn f() -> u8 {\n    mid::with(|s| s.m())\n}\n");
    assert_eq!(found, leaf());
}

/// A trait method of a trait `impl` (`impl Trait` return, `Box<dyn Trait>`) is the open class
/// #1004: the scan lists no trait `impl` member as a candidate, with or without a direct
/// dependency. The test pins the limit that `docs/known-limits.md` names.
#[test]
fn a_trait_method_through_impl_trait_or_dyn_is_the_named_open_class_1004() {
    let impl_trait = pairs(
        "pub fn get() -> impl leaf::Tr {\n    leaf::S\n}\n",
        "pub fn f() -> u8 {\n    mid::get().t()\n}\n",
    );
    assert_eq!(impl_trait, vec![]);
    let boxed = pairs(
        "pub fn get() -> Box<dyn leaf::Tr> {\n    Box::new(leaf::S)\n}\n",
        "pub fn f() -> u8 {\n    mid::get().t()\n}\n",
    );
    assert_eq!(boxed, vec![]);
}

/// A member of a block in the file of its type is no candidate: the scan takes the edge to the
/// type for it. A value that `mid` returns carries no such edge, so the call gives no edge and no
/// gap. This is an open false-PASS class of the edge model, as #1004; `docs/known-limits.md` names
/// it, and the self-check test guards the one row of `native/` that a value can reach this way.
#[test]
fn a_method_in_the_file_of_its_type_on_a_value_of_a_dependency_is_a_named_open_class() {
    let found = pairs(
        "pub fn get() -> leaf::S {\n    leaf::S\n}\n",
        "pub fn f() -> u8 {\n    mid::get().own()\n}\n",
    );
    assert_eq!(found, vec![]);
}
