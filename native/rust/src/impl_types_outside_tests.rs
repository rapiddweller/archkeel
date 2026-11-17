// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the pair gaps of a method call on a type of a crate from a registry or
// git (#1571, AD-804). Such a crate cannot depend on a crate of the workspace, so the call reaches
// no inherent member of the workspace (E0116). The fixture of `impl_types_tests.rs`: `b` holds an
// `impl` of `S` with `m` and `len`, `e` one of `T`.

use super::tests::{edge, gaps, outcome};

const REGISTRY: (&str, &str) = (
    "crates/app/Cargo.toml",
    "[package]\nname = \"app\"\nedition = \"2021\"\n\n[dependencies]\next = \"1\"\nlocal = { path = \"../local\" }\n",
);

#[test]
fn a_receiver_of_a_registry_type_reaches_no_member_of_the_workspace() {
    for a in [
        "pub fn f(x: &ext::Thing) -> usize { x.len() }",
        "use ext::Thing;\npub fn f(x: Thing) -> usize { x.len() }",
        "use ext::nested;\npub fn f(x: Box<nested::Thing<String>>) -> usize { x.len() }",
    ] {
        assert_eq!(outcome(a, &[REGISTRY]), gaps(&[]), "{a}");
    }
}

#[test]
fn a_path_dependency_a_workspace_argument_or_a_local_name_keeps_the_gaps() {
    for a in [
        // A path dependency can depend on a crate of the workspace.
        "pub fn f(x: &local::Thing) -> usize { x.len() }",
        // An outside type may deref to its type argument.
        "pub fn f(x: &ext::Wrapper<crate::c::S>) -> usize { x.len() }",
        "pub fn f<X>(x: &ext::Wrapper<X>) -> usize { x.len() }",
        // A crate that the manifest does not name.
        "pub fn f(x: &other::Thing) -> usize { x.len() }",
    ] {
        assert_eq!(outcome(a, &[REGISTRY]), gaps(&["b", "e"]), "{a}");
    }
}

#[test]
fn a_module_of_the_file_with_the_name_of_a_dependency_is_own() {
    let a =
        "pub mod ext {\n    pub struct Thing;\n}\npub fn f(x: &ext::Thing) -> usize { x.len() }";
    let b = "impl crate::a::ext::Thing {\n    pub fn len(&self) -> usize {\n        0\n    }\n}\n";
    assert_eq!(
        outcome(a, &[REGISTRY, ("crates/app/src/b.rs", b)]),
        edge("b")
    );
}
