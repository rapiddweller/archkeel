// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and the pair gaps of a method call whose receiver type the
// written types prove (#1571, AD-804). Each fixture is a crate with `mod a; .. mod e;`: `c` defines
// `S`, `d` defines `T` with its own members, `b` holds an `impl` of `S` and `e` an `impl` of `T`,
// each with members `m` and `len`; `a` holds the call.

use archkeel_facts::GapFact;

use crate::collect::tests::run;

const LIB: &str = "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\n";
const C: &str = "pub struct S {\n    pub t: crate::d::T,\n    pub r: &'static crate::d::T,\n}\n";
const D: &str = "pub struct T;\n\nimpl T {\n    pub fn new() -> Self {\n        T\n    }\n    \
                 pub fn s(&self) -> &'static crate::c::S {\n        todo!()\n    }\n}\n";
const B: &str = "impl crate::c::S {\n    pub fn m(&self) {}\n    pub fn len(&self) -> usize {\n        0\n    }\n}\n";
const E: &str = "impl crate::d::T {\n    pub fn m(&self) {}\n    pub fn len(&self) -> usize {\n        0\n    }\n}\n";

/// The edges of `a` to `b` and `e`, and the pair gaps of `a`.
pub(super) type Outcome = (Vec<String>, Vec<String>);

pub(super) fn outcome(a: &str, more: &[(&str, &str)]) -> Outcome {
    let mut files: Vec<(&str, &str)> = vec![
        (
            "crates/app/Cargo.toml",
            "[package]\nname = \"app\"\nedition = \"2021\"\n",
        ),
        ("crates/app/src/lib.rs", LIB),
        ("crates/app/src/b.rs", B),
        ("crates/app/src/c.rs", C),
        ("crates/app/src/d.rs", D),
        ("crates/app/src/e.rs", E),
        ("crates/app/src/a.rs", a),
    ];
    for (rel, text) in more {
        files.retain(|(seen, _)| seen != rel);
        files.push((rel, text));
    }
    let facts = run(&files, false);
    let short = |name: &str| name.trim_start_matches("ns.app.").to_owned();
    let mut edges: Vec<String> = (facts.imports.iter().map(|record| record.data.data()))
        .filter(|data| data.source_module.as_str() == "ns.app.a")
        .map(|data| short(data.target_module.as_str()))
        .filter(|target| target == "b" || target == "e")
        .collect();
    edges.sort();
    edges.dedup();
    let mut gaps: Vec<String> = (facts.gaps.iter())
        .filter_map(|gap| match &gap.data {
            GapFact::CollectionGap(data) => Some(data),
            _ => None,
        })
        .filter(|data| data.source_module.as_ref().map(|m| m.as_str()) == Some("ns.app.a"))
        .filter_map(|data| Some(short(data.module.as_ref()?.as_str())))
        .collect();
    gaps.sort();
    gaps.dedup();
    (edges, gaps)
}

fn names(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

pub(super) fn gaps(items: &[&str]) -> Outcome {
    (Vec::new(), names(items))
}

pub(super) fn edge(item: &str) -> Outcome {
    (names(&[item]), Vec::new())
}

#[test]
fn a_receiver_of_a_std_type_reaches_no_member_of_the_workspace() {
    let calls = [
        "pub fn f(x: &String) -> usize { x.len() }",
        "pub fn f(x: &Vec<crate::d::T>) -> usize { x.len() }",
        "pub fn f(x: &[crate::d::T]) -> usize { x.len() }",
        "pub fn f(x: &std::collections::BTreeMap<u8, crate::d::T>) -> usize { x.len() }",
        "use std::collections::BTreeSet;\npub fn f(x: BTreeSet<u8>) -> usize { x.len() }",
        "pub fn f() -> usize { \"x\".len() }",
        "pub fn f(x: &crate::c::S) -> usize { x.r.s().r.s().len() }",
    ];
    for call in &calls[..6] {
        assert_eq!(outcome(call, &[]), gaps(&[]), "{call}");
    }
    // `S::len` is the member that the last call reaches: the chain ends on `&S`.
    assert_eq!(outcome(calls[6], &[]), edge("b"));
}

#[test]
fn an_own_type_narrows_the_gaps_to_its_members_and_an_exact_form_gives_the_edge() {
    // The field `t` is a value: `T::m(&self)` is an autoref, a by-value trait method could win.
    assert_eq!(
        outcome("pub fn f(x: &crate::c::S) { x.t.m() }", &[]),
        gaps(&["e"])
    );
    // The field `r` is `&T`: the first step finds `T::m(&self)`.
    assert_eq!(
        outcome("pub fn f(x: &crate::c::S) { x.r.m() }", &[]),
        edge("e")
    );
    // The written return type `&S` of `T::s`.
    assert_eq!(
        outcome("pub fn f(x: &crate::d::T) { x.s().m() }", &[]),
        edge("b")
    );
    // `T::new() -> Self` through an untyped local, and `Option<T>::unwrap`.
    let local = "pub fn f() { let t = crate::d::T::new(); t.m() }";
    assert_eq!(outcome(local, &[]), gaps(&["e"]));
    let unwrap = "pub fn f(o: Option<crate::d::T>) { o.unwrap().m() }";
    assert_eq!(outcome(unwrap, &[]), gaps(&["e"]));
    let boxed = "pub fn f(o: Box<crate::d::T>) { o.m() }";
    assert_eq!(outcome(boxed, &[]), gaps(&["e"]));
}

#[test]
fn a_local_type_of_a_std_name_is_no_std_type() {
    let a = "pub struct String;\npub fn f(x: &String) -> usize { x.len() }";
    let b = "impl crate::a::String {\n    pub fn len(&self) -> usize {\n        0\n    }\n}\n";
    assert_eq!(outcome(a, &[("crates/app/src/b.rs", b)]), edge("b"));
}

#[test]
fn an_unproved_receiver_keeps_every_gap() {
    // A type parameter.
    assert_eq!(
        outcome("pub fn f<X>(x: &X) { x.m() }", &[]),
        gaps(&["b", "e"])
    );
    // A macro of the `fn` that is no `macro_rules!` of the workspace may bind `x` again; the macro
    // call has its own gap with no target.
    let foreign = "pub fn f(x: &crate::d::T) { unknown!(); x.s().m() }";
    assert_eq!(outcome(foreign, &[]), gaps(&["", "b", "e"]));
    // A return type that the scan does not read.
    let opaque = "pub fn f() { g().m() }\nfn g() -> impl Sized { 0 }";
    assert_eq!(outcome(opaque, &[]), gaps(&["b", "e"]));
    // A parenthesized receiver is the receiver.
    let paren = "pub fn f(x: &crate::d::T) { (x).s().m() }";
    assert_eq!(outcome(paren, &[]), edge("b"));
}

#[test]
fn a_type_with_a_deref_impl_keeps_every_gap() {
    let e = format!(
        "{E}\nimpl std::ops::Deref for crate::d::T {{\n    type Target = crate::c::S;\n    \
                     fn deref(&self) -> &crate::c::S {{\n        todo!()\n    }}\n}}\n"
    );
    let call = "pub fn f(o: Box<crate::d::T>) { o.m() }";
    assert_eq!(
        outcome(call, &[("crates/app/src/e.rs", &e)]),
        gaps(&["b", "e"])
    );
}

#[test]
fn a_closure_of_a_fixed_std_adapter_and_a_loop_variable_have_the_item_type() {
    let v = "pub fn f(v: &Vec<crate::d::T>) {";
    // `iter()` gives `&T`: the first step finds `T::m(&self)`.
    for body in [
        "v.iter().for_each(|t| t.m()) }",
        "v.iter().map(|t| t.m()); }",
        "for t in v { t.m() } }",
        "for t in v.iter().take_while(|_| true) { t.m() } }",
        "for t in &v[..] { t.m() } }",
    ] {
        let a = format!("{v} {body}");
        let expected = if body.contains("v[..]") {
            gaps(&["b", "e"])
        } else {
            edge("e")
        };
        assert_eq!(outcome(&a, &[]), expected, "{body}");
    }
    // A predicate sees `&&T`: only the members of `T`, and no edge.
    let filter = format!("{v} v.iter().filter(|t| t.len() > 0); }}");
    assert_eq!(outcome(&filter, &[]), gaps(&["e"]));
    // `Option<T>::map` gives `T`, a value: an autoref keeps the gap.
    let option = "pub fn f(o: Option<crate::d::T>) { o.map(|t| t.m()); }";
    assert_eq!(outcome(option, &[]), gaps(&["e"]));
    let map = "pub fn f(m: &std::collections::BTreeMap<crate::c::S, crate::d::T>) {";
    let keys = format!("{map} m.keys().for_each(|s| s.m()) }}");
    assert_eq!(outcome(&keys, &[]), edge("b"));
    let values = format!("{map} m.values().any(|t| {{ t.m(); true }}); }}");
    assert_eq!(outcome(&values, &[]), edge("e"));
}

#[test]
fn an_adapter_outside_the_fixed_set_or_an_unknown_item_keeps_every_gap() {
    for a in [
        "pub fn f(v: &Vec<crate::d::T>) { v.iter().inspect(|t| t.m()); }",
        "pub fn f(v: &Vec<crate::d::T>) { v.iter().enumerate().for_each(|t| t.m()) }",
        "pub fn f(v: &Vec<crate::d::T>) { v.iter().map(|t| t).for_each(|t| t.m()) }",
        "pub fn f<X>(v: &Vec<X>) { v.iter().for_each(|t| t.m()) }",
        "pub fn f(v: Box<dyn Iterator<Item = crate::d::T>>) { v.for_each(|t| t.m()) }",
        "pub fn f(v: &crate::d::T) { v.iter().for_each(|t| t.m()) }",
        "pub fn f(v: [crate::d::T; 2]) { for t in v { t.m() } }",
    ] {
        assert_eq!(outcome(a, &[]), gaps(&["b", "e"]), "{a}");
    }
}

#[test]
fn a_unique_field_behind_a_shared_reference_is_no_edge() {
    let c = "pub struct S {\n    pub t: crate::d::T,\n    pub r: &'static crate::d::T,\n    \
             pub u: &'static mut crate::d::T,\n}\n";
    let e = "impl crate::d::T {\n    pub fn m(&mut self) {}\n}\n";
    let more = [("crates/app/src/c.rs", c), ("crates/app/src/e.rs", e)];
    assert_eq!(
        outcome("pub fn f(x: &crate::c::S) { x.u.m() }", &more),
        gaps(&["e"])
    );
    assert_eq!(
        outcome("pub fn f(x: &mut crate::c::S) { x.u.m() }", &more),
        edge("e")
    );
}

#[test]
fn a_deref_target_or_autoref_method_needs_a_file_with_no_trait_of_a_dependency() {
    // `iter` and `first` are methods of `[T]`, a deref target of `Vec<T>`: a trait of a dependency
    // in scope could win on `Vec<T>` first.
    let outside = "use serde::Serialize;\n";
    let iter = "pub fn f(v: &Vec<crate::d::T>) { v.iter().for_each(|t| t.m()) }";
    assert_eq!(outcome(iter, &[]), edge("e"));
    assert_eq!(outcome(&format!("{outside}{iter}"), &[]), gaps(&["b", "e"]));
    let std_use = "use std::collections::BTreeMap;\n";
    assert_eq!(outcome(&format!("{std_use}{iter}"), &[]), edge("e"));
    let glob = "use crate::c::*;\n";
    assert_eq!(outcome(&format!("{glob}{iter}"), &[]), gaps(&["b", "e"]));
    // `Option::unwrap(self)` on an `Option` by value is found at the first step.
    let unwrap = "pub fn f(o: Option<&'static crate::d::T>) { o.unwrap().m() }";
    assert_eq!(outcome(&format!("{outside}{unwrap}"), &[]), edge("e"));
    // `Option::as_ref(&self)` on a value needs an autoref.
    let as_ref = "pub fn f(o: Option<crate::d::T>) { o.as_ref().unwrap().m() }";
    assert_eq!(outcome(as_ref, &[]), edge("e"));
    assert_eq!(
        outcome(&format!("{outside}{as_ref}"), &[]),
        gaps(&["b", "e"])
    );
    // A re-export of another crate makes its name a possible trait in each importing file.
    let reexport = (
        "crates/app/src/lib.rs",
        "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\npub use serde::Tr;\n",
    );
    let named = format!("use crate::Tr;\n{iter}");
    assert_eq!(outcome(&named, &[reexport]), gaps(&["b", "e"]));
}
