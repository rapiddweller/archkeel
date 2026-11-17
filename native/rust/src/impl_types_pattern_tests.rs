// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and pair gaps of a call on a name that a pattern binds:
// `Some(x)`, `Ok(x)` and tuples, on a value with a written type (#1571, AD-804). The fixture of
// `impl_types_tests.rs`: `b` holds `S::m(&self)`, `e` holds `T::m(&self)`.

use super::tests::{edge, gaps, outcome, Outcome};

fn edges(items: &[&str]) -> Outcome {
    (
        items.iter().map(|item| (*item).to_owned()).collect(),
        Vec::new(),
    )
}

#[test]
fn a_variant_pattern_binds_the_payload() {
    let shared = "pub fn f(o: Option<&'static crate::d::T>) {";
    for body in [
        "if let Some(t) = o { t.m() } }",
        "match o { Some(t) => t.m(), None => {} } }",
        "let Some(t) = o else { return }; t.m(); }",
        "while let Some(t) = o { t.m(); break } }",
    ] {
        assert_eq!(
            outcome(&format!("{shared} {body}"), &[]),
            edge("e"),
            "{body}"
        );
    }
    // Through a reference, the default binding mode binds `&T`.
    let by_ref = "pub fn f(o: &Option<crate::d::T>) { if let Some(t) = o { t.m() } }";
    assert_eq!(outcome(by_ref, &[]), edge("e"));
    let ok = "pub fn f(r: Result<&'static crate::d::T, String>) { if let Ok(t) = r { t.m() } }";
    assert_eq!(outcome(ok, &[]), edge("e"));
    // A value: `T::m(&self)` is an autoref, so only the members of `T` stay.
    let value = "pub fn f(o: Option<crate::d::T>) { if let Some(t) = o { t.m() } }";
    assert_eq!(outcome(value, &[]), gaps(&["e"]));
}

#[test]
fn a_tuple_pattern_binds_its_elements() {
    let param = "pub fn f((t, s): (&crate::d::T, &crate::c::S)) { t.m(); s.m() }";
    assert_eq!(outcome(param, &[]), edges(&["b", "e"]));
    let local = "pub fn f(p: (&'static crate::d::T, u8)) { let (t, _) = p; t.m() }";
    assert_eq!(outcome(local, &[]), edge("e"));
    let map = "pub fn f(m: &std::collections::BTreeMap<crate::c::S, crate::d::T>) {";
    let closure = format!("{map} m.iter().for_each(|(s, t)| {{ s.m(); t.m() }}) }}");
    assert_eq!(outcome(&closure, &[]), edges(&["b", "e"]));
    let looped = format!("{map} for (s, t) in m {{ s.m(); t.m() }} }}");
    assert_eq!(outcome(&looped, &[]), edges(&["b", "e"]));
}

#[test]
fn a_pattern_that_the_scan_does_not_prove_keeps_every_gap() {
    let o = "pub fn f(o: &Option<crate::d::T>) {";
    for body in [
        // `mut` inside a pattern resets the binding mode.
        "if let Some(mut t) = o { t.m() } }",
        "match o { Some(t) | Some(t) => t.m(), None => {} } }",
        "if let Some(ref t) = o { t.m() } }",
    ] {
        assert_eq!(
            outcome(&format!("{o} {body}"), &[]),
            gaps(&["b", "e"]),
            "{body}"
        );
    }
    // A `Some` of the file is no variant of the prelude.
    let local = "pub enum E { Some(&'static crate::d::T) }\nuse E::Some;\n\
                 pub fn f(o: Option<&'static crate::d::T>) { if let Some(t) = o { t.m() } }";
    assert_eq!(outcome(local, &[]), gaps(&["b", "e"]));
}
