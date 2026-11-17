// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and pair gaps of a call on a `let` in a nested block or on a
// shadowed `let` (#1571, AD-804 step 3). The fixture of `impl_types_tests.rs`: `S` has the field
// `r: &'static T`, `b` holds `S::m(&self)`, `e` holds `T::m(&self)`.

use super::tests::{edge, gaps, outcome};

#[test]
fn a_let_in_a_nested_block_or_a_shadowed_let_has_its_chain() {
    for a in [
        "pub fn f(v: &Vec<crate::d::T>) { for t in v { let r = t; r.m() } }",
        "pub fn f(x: &crate::c::S) { let t = x.r; let t = t; t.m() }",
        "pub fn f(x: &crate::c::S) { let t = x.r; t.m(); let t = 1u8; let _ = t; }",
        "pub fn f(x: &crate::c::S) { if true { let t = x.r; (0..1).for_each(|_| t.m()) } }",
        "pub fn f(o: Option<&'static crate::d::T>) { if true { let Some(t) = o else { return }; t.m() } }",
    ] {
        assert_eq!(outcome(a, &[]), edge("e"), "{a}");
    }
}

#[test]
fn a_let_whose_name_its_scope_binds_again_keeps_every_gap() {
    for a in [
        // A match arm in its scope binds the name again.
        "pub fn f(x: &crate::c::S, y: u8) { if true { let t = x.r; match y { t => {} } t.m() } }",
        // A closure parameter of the name.
        "pub fn f(x: &crate::c::S) { if true { let t = x.r; let g = |t: u8| t; t.m(); g(1); } }",
        // A call before the `let`.
        "pub fn f(x: &crate::c::S, t: u8) { if true { t.m(); let t = x.r; let _ = t; } }",
    ] {
        assert_eq!(outcome(a, &[]), gaps(&["b", "e"]), "{a}");
    }
}
