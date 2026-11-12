// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and the pair gaps of a call on `self` (AD-383). A resolution
// must hold in every configuration: a `cfg` on the member, the block, a module, the file, the
// type or the caller keeps the gaps, and so do two read members of one type.

use super::*;

const CALL: &str = "self.m();";

fn shared() -> String {
    member("pub fn m(&self) {}")
}

#[test]
fn a_gated_member_keeps_the_gap_to_the_deref_target() {
    // Review of #1081: with the feature off, Rust calls the `m` of `T`, the deref target in `e`.
    let c = (
        "crates/app/src/c.rs",
        "pub struct S(pub T);\npub struct T;\n",
    );
    let gated = member("#[cfg(feature = \"optional\")]\n    pub fn m(&self) {}");
    assert_eq!(outcome(&gated, &caller("&self", CALL), &[c]), kept());
}

#[test]
fn a_cfg_on_the_block_or_on_an_inline_module_keeps_the_gaps() {
    let block = format!("#[cfg(feature = \"x\")]\n{}", shared());
    assert_eq!(outcome(&block, &caller("&self", CALL), &[]), kept());
    let inline = format!("#[cfg(feature = \"x\")]\nmod inner {{\n{}}}\n", shared());
    assert_eq!(outcome(&inline, &caller("&self", CALL), &[]), kept());
}

#[test]
fn a_cfg_on_the_declaration_or_inside_the_file_keeps_the_gaps() {
    let lib = (
        "crates/app/src/lib.rs",
        "mod a;\n#[cfg(feature = \"x\")]\nmod b;\nmod c;\nmod d;\nmod e;\n",
    );
    assert_eq!(outcome(&shared(), &caller("&self", CALL), &[lib]), kept());
    let inner = format!("#![cfg(feature = \"x\")]\n{}", shared());
    assert_eq!(outcome(&inner, &caller("&self", CALL), &[]), kept());
}

#[test]
fn a_type_that_some_configuration_changes_keeps_the_gaps() {
    for c in [
        "#[cfg(feature = \"x\")]\npub struct S;\n",
        "#[rewrite]\npub struct S;\n",
        "pub struct S;\nmod inner {\n    pub struct S;\n}\n",
    ] {
        let c = ("crates/app/src/c.rs", c);
        assert_eq!(
            outcome(&shared(), &caller("&self", CALL), &[c]),
            kept(),
            "{}",
            c.1
        );
    }
    let derived = ("crates/app/src/c.rs", "#[derive(Clone)]\npub struct S;\n");
    let found = outcome(&shared(), &caller("&self", CALL), &[derived]);
    assert_eq!(found, resolved());
}

#[test]
fn a_caller_that_some_configuration_removes_keeps_the_gaps() {
    let inline = format!(
        "#[cfg(feature = \"x\")]\nmod inner {{\n{}}}\n",
        caller("&self", CALL)
    );
    assert_eq!(outcome(&shared(), &inline, &[]), kept());
    let lib = (
        "crates/app/src/lib.rs",
        "#[cfg(feature = \"x\")]\nmod a;\nmod b;\nmod c;\nmod d;\nmod e;\n",
    );
    assert_eq!(outcome(&shared(), &caller("&self", CALL), &[lib]), kept());
}

#[test]
fn two_read_members_of_one_type_keep_the_gaps() {
    let d = (
        "crates/app/src/d.rs",
        "pub struct T;\nimpl crate::c::S {\n    pub fn m(&self) {}\n}\n",
    );
    let found = outcome(&shared(), &caller("&self", CALL), &[d]);
    assert_eq!(found, (Vec::new(), names(&["b", "d", "e"])));
}

#[test]
fn a_path_self_m_is_an_edge_to_the_one_member_or_a_gap() {
    assert_eq!(
        outcome(&shared(), &caller("&self", "Self::m(self);"), &[]),
        resolved()
    );
    let none = member("pub fn m() {}");
    assert_eq!(
        outcome(&none, &caller("&self", "Self::m();"), &[]),
        resolved()
    );
    let g = (
        "crates/app/src/c.rs",
        "pub struct S;\npub struct G<X>(X);\n",
    );
    let generic =
        "impl<X> crate::c::G<X> {\n    pub fn f(&self) {\n        Self::m(self);\n    }\n}\n";
    assert_eq!(outcome(&shared(), generic, &[g]), kept());
    let in_trait = "pub trait Tr {\n    fn f(&self) {\n        Self::m(self);\n    }\n}\n";
    assert_eq!(outcome(&shared(), in_trait, &[]), kept());
}

#[test]
fn a_member_that_a_macro_may_expand_is_no_edge() {
    // The expansion itself is no gap yet (#1020): only the resolution is blocked.
    let made = "macro_rules! make {\n    () => {\n        impl crate::c::S {\n            pub fn m(&self) {}\n        }\n    };\n}\nmake!();\n";
    assert_eq!(
        outcome(made, &caller("&self", CALL), &[]),
        (Vec::new(), names(&["e"]))
    );
    // A read member `m` beside a macro that defines `fn m`: the scan cannot see which is real.
    let beside = "pub struct T;\npub struct U;\nmacro_rules! make {\n    () => {\n        impl crate::d::U {\n            pub fn m(&self) {}\n        }\n    };\n}\nmake!();\n";
    let d = ("crates/app/src/d.rs", beside);
    let found = outcome(&shared(), &caller("&self", CALL), &[d]);
    assert_eq!(found, kept());
}

#[test]
fn a_member_of_a_trait_impl_or_of_the_field_type_is_no_inherent_member() {
    // The trait of the impl in `a` is not in scope there: Rust skips it and looks further.
    let d = (
        "crates/app/src/d.rs",
        "pub struct T;\npub trait Tm {\n    fn m(&self);\n}\n",
    );
    let a = format!(
        "impl crate::d::Tm for crate::c::S {{\n    fn m(&self) {{}}\n}}\n{}",
        caller("&self", CALL)
    );
    assert_eq!(outcome("", &a, &[d]), (Vec::new(), names(&["e"])));
    // `self.0` has the type of the field, not `S`.
    let c = ("crates/app/src/c.rs", "pub struct S(pub crate::d::T);\n");
    let found = outcome(&shared(), &caller("&self", "self.0.m();"), &[c]);
    assert_eq!(found, kept());
}
