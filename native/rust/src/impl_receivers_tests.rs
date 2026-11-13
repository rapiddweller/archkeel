// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host reads the edges and the pair gaps of a call on `self` (AD-383). Each fixture
// is a crate with `mod a; .. mod e;`: `c` defines `S`, `d` defines `T`, `b` holds an `impl` of `S`,
// `e` holds an `impl` of `T` with a member `m`, and `a` holds the call.

use archkeel_facts::GapFact;

use crate::collect::tests::run;

const FILES: [(&str, &str); 5] = [
    (
        "crates/app/Cargo.toml",
        "[package]\nname = \"app\"\nedition = \"2021\"\n",
    ),
    (
        "crates/app/src/lib.rs",
        "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\n",
    ),
    ("crates/app/src/c.rs", "pub struct S;\n"),
    ("crates/app/src/d.rs", "pub struct T;\n"),
    (
        "crates/app/src/e.rs",
        "impl crate::d::T {\n    pub fn m(&self) {}\n}\n",
    ),
];

/// The edges of `a` to `b` and `e`, and the pair gaps of `a`, as module names without `ns.app.`.
type Outcome = (Vec<String>, Vec<String>);

fn outcome(b: &str, a: &str, more: &[(&str, &str)]) -> Outcome {
    // A later file of the same path replaces an earlier one.
    let mut files: Vec<(&str, &str)> = FILES.to_vec();
    files.extend([("crates/app/src/b.rs", b), ("crates/app/src/a.rs", a)]);
    files.extend(more);
    let mut all: Vec<(&str, &str)> = Vec::new();
    for (rel, text) in files {
        all.retain(|(seen, _)| *seen != rel);
        all.push((rel, text));
    }
    let facts = run(&all, false);
    let short = |name: &str| name.trim_start_matches("ns.app.").to_owned();
    let mut edges: Vec<String> = (facts.imports.iter().map(|record| record.data.data()))
        .filter(|data| data.source_module.as_str() == "ns.app.a")
        .map(|data| short(data.target_module.as_str()))
        .filter(|target| target == "b" || target == "e")
        .collect();
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
    (edges, gaps)
}

fn names(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

/// An `impl S` in `a` whose method `f` has the `self` parameter `receiver` and calls `body`.
fn caller(receiver: &str, body: &str) -> String {
    format!("impl crate::c::S {{\n    pub fn f({receiver}) {{\n        {body}\n    }}\n}}\n")
}

/// A foreign `impl S` in `b` with the member `member`.
fn member(member: &str) -> String {
    format!("impl crate::c::S {{\n    {member}\n}}\n")
}

/// The answer before AD-383: a gap to each module with a visible foreign `m`.
fn kept() -> Outcome {
    (Vec::new(), names(&["b", "e"]))
}

/// The resolved answer: an edge to `b`, and no gap to `e`, whose `m` belongs to another type.
fn resolved() -> Outcome {
    (names(&["b"]), Vec::new())
}

#[test]
fn a_call_on_self_with_the_same_self_form_is_an_edge_to_the_member_and_no_gap() {
    for (receiver, form) in [
        ("&self", "pub fn m(&self) {}"),
        ("&'_ self", "pub fn m(&self) {}"),
        ("&mut self", "pub(crate) fn m(&mut self) {}"),
        ("self", "pub fn m(mut self) {}"),
    ] {
        let found = outcome(&member(form), &caller(receiver, "self.m();"), &[]);
        assert_eq!(found, resolved(), "{receiver} -> {form}");
    }
}

#[test]
fn a_member_in_the_file_of_the_type_or_in_the_caller_is_no_edge_and_no_gap() {
    let own = (
        "crates/app/src/c.rs",
        "pub struct S;\nimpl S {\n    pub fn m(&self) {}\n}\n",
    );
    let call = caller("&self", "self.m();");
    assert_eq!(outcome("", &call, &[own]), (Vec::new(), Vec::new()));
    let local = format!("{call}impl crate::c::S {{\n    fn m(&self) {{}}\n}}\n");
    assert_eq!(outcome("", &local, &[]), (Vec::new(), Vec::new()));
}

#[test]
fn a_call_on_self_in_a_trait_impl_or_a_closure_or_with_a_lifetime_resolves_too() {
    let m = member("pub fn m(&self) {}");
    let in_trait = "pub trait Tr {\n    fn f(&self);\n}\nimpl Tr for crate::c::S {\n    fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, in_trait, &[]), resolved());
    let closure = caller("&self", "let g = || self.m();\n        g();");
    assert_eq!(outcome(&m, &closure, &[]), resolved());
    let w = ("crates/app/src/c.rs", "pub struct S<'x>(&'x u8);\n");
    let m = "impl<'y> crate::c::S<'y> {\n    pub fn m(&self) {}\n}\n";
    let call = "impl<'a> crate::c::S<'a> {\n    pub fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(m, call, &[w]), resolved());
}

#[test]
fn a_cfg_attr_on_the_member_keeps_the_gaps() {
    // AD-383: a resolution must hold in every configuration; `cfg_attr` is never inert.
    let gated = member("#[cfg_attr(test, allow(dead_code), inline)]\n    pub fn m(&self) {}");
    let found = outcome(&gated, &caller("&self", "self.m();"), &[]);
    assert_eq!(found, kept());
}

#[test]
fn an_impl_in_a_method_body_keeps_the_gaps() {
    // A local item in a body can hide the type name, so a block in a body is never exact.
    let m = member("pub fn m(&self) {}");
    let body = "impl crate::d::T {\n            fn g(&self) {\n                self.m();\n            }\n        }";
    assert_eq!(outcome(&m, &caller("&self", body), &[]), kept());
}

#[test]
fn members_in_the_two_cases_of_a_cfg_keep_the_gaps() {
    let both = "#[cfg(unix)]\nimpl crate::c::S {\n    pub fn m(&self) {}\n}\n";
    let other = (
        "crates/app/src/d.rs",
        "pub struct T;\n#[cfg(not(unix))]\nimpl crate::c::S {\n    pub fn m(&self) {}\n}\n",
    );
    let found = outcome(both, &caller("&self", "self.m();"), &[other]);
    assert_eq!(found, (Vec::new(), names(&["b", "d", "e"])));
}

#[test]
fn another_self_form_keeps_the_gaps_because_a_trait_method_can_match_first() {
    for (receiver, form) in [
        ("&mut self", "pub fn m(&self) {}"),
        ("&self", "pub fn m(self) {}"),
        ("self", "pub fn m(&self) {}"),
        ("self: &Self", "pub fn m(&self) {}"),
        ("&self", "pub fn m(self: &Self) {}"),
    ] {
        let found = outcome(&member(form), &caller(receiver, "self.m();"), &[]);
        assert_eq!(found, kept(), "{receiver} -> {form}");
    }
}

#[test]
fn a_member_that_no_inherent_impl_of_the_type_has_keeps_the_gaps() {
    // A trait method or a deref target of `S` may be the member.
    let found = outcome(
        &member("pub fn n(&self) {}"),
        &caller("&self", "self.m();"),
        &[],
    );
    assert_eq!(found, (Vec::new(), names(&["e"])));
}

#[test]
fn a_generic_type_or_an_attribute_that_can_rewrite_the_item_keeps_the_gaps() {
    let m = member("pub fn m(&self) {}");
    let g = (
        "crates/app/src/c.rs",
        "pub struct S;\npub struct G<X>(X);\n",
    );
    let generic = "impl<X> crate::c::G<X> {\n    pub fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, generic, &[g]), kept());
    let argument = "impl crate::c::G<u8> {\n    pub fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, argument, &[g]), kept());
    let on_block = format!("#[rewrite]\n{m}");
    assert_eq!(
        outcome(&on_block, &caller("&self", "self.m();"), &[]),
        kept()
    );
    let on_member = member("#[rewrite]\n    pub fn m(&self) {}");
    assert_eq!(
        outcome(&on_member, &caller("&self", "self.m();"), &[]),
        kept()
    );
    let on_caller = format!("#[rewrite]\n{}", caller("&self", "self.m();"));
    assert_eq!(
        outcome(&m, &on_caller, &[]),
        (Vec::new(), names(&["", "b", "e"]))
    );
    let on_method =
        caller("&self", "self.m();").replace("    pub fn f", "    #[rewrite]\n    pub fn f");
    assert_eq!(
        outcome(&m, &on_method, &[]),
        (Vec::new(), names(&["", "b", "e"]))
    );
    let gates = [
        "#[cfg_attr(test, rewrite)]",
        "#[cfg_attr(test, allow::x)]",
        "#[cfg_attr(test)]",
    ];
    for gate in gates {
        let gated = member(&format!("{gate}\n    pub fn m(&self) {{}}"));
        assert_eq!(
            outcome(&gated, &caller("&self", "self.m();"), &[]),
            kept(),
            "{gate}"
        );
    }
}

#[test]
fn another_arity_or_a_member_that_is_not_certainly_visible_keeps_the_gaps() {
    let call = caller("&self", "self.m(1);");
    let other_arity = member("pub fn m(&self) {}");
    assert_eq!(outcome(&other_arity, &call, &[]).0, Vec::<String>::new());
    let restricted = member("pub(in crate::b) fn m(&self, x: u8) {}");
    let found = outcome(&restricted, &call, &[]);
    assert_eq!(found.0, Vec::<String>::new());
    // A private member of `b` is not visible in `a`: Rust skips it and looks further.
    let private = member("fn m(&self) {}");
    let found = outcome(&private, &caller("&self", "self.m();"), &[]);
    assert_eq!(found, (Vec::new(), names(&["e"])));
}

#[test]
fn a_block_whose_type_the_scan_cannot_place_keeps_the_gaps() {
    let m = member("pub fn m(&self) {}");
    let glob = (
        "crates/app/src/d.rs",
        "use crate::c::*;\npub struct T;\nimpl S {\n    pub fn m(&self) {}\n}\n",
    );
    let found = outcome(&m, &caller("&self", "self.m();"), &[glob]);
    assert_eq!(found, (Vec::new(), names(&["b", "d", "e"])));
}

#[test]
fn a_receiver_other_than_a_plain_self_or_a_self_that_does_not_reach_keeps_the_gaps() {
    let m = member("pub fn m(&self) {}");
    for body in [
        "(self).m();",
        "let s = self;\n        s.m();",
        "fn g(s: &crate::c::S) {\n            s.m();\n        }",
        "let _ = format!(\"{:?}\", self.m());",
    ] {
        assert_eq!(outcome(&m, &caller("&self", body), &[]), kept(), "{body}");
    }
    let default =
        "pub trait Tr {\n    fn m(&self) {}\n    fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, default, &[]), kept());
}

#[test]
fn a_type_alias_keeps_the_gaps() {
    let m = member("pub fn m(&self) {}");
    let alias =
        "type A = crate::c::S;\nimpl A {\n    pub fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, alias, &[]), kept());
}

#[test]
fn a_type_parameter_that_hides_a_type_name_keeps_the_gaps() {
    // `T` of the block is generic, though `use crate::d::T` binds a type of the same name.
    let m = member("pub fn m(&self) {}");
    let blanket = "use crate::d::T;\npub trait Tr {\n    fn f(&self);\n}\nimpl<T> Tr for T {\n    fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(&m, blanket, &[]), kept());
}

#[test]
fn a_member_of_the_same_type_with_other_type_arguments_keeps_the_gaps() {
    let g = (
        "crates/app/src/c.rs",
        "pub struct S;\npub struct G<X>(X);\n",
    );
    let m = "impl crate::c::G<u16> {\n    pub fn m(&self) {}\n}\n";
    let call = "impl crate::c::G<u8> {\n    pub fn f(&self) {\n        self.m();\n    }\n}\n";
    assert_eq!(outcome(m, call, &[g]), kept());
}

#[test]
fn a_member_whose_other_cfg_case_has_another_self_form_keeps_the_gaps() {
    let shared = "#[cfg(unix)]\nimpl crate::c::S {\n    pub fn m(&self) {}\n}\n";
    let unique = (
        "crates/app/src/d.rs",
        "pub struct T;\n#[cfg(not(unix))]\nimpl crate::c::S {\n    pub fn m(&mut self) {}\n}\n",
    );
    let found = outcome(shared, &caller("&self", "self.m();"), &[unique]);
    assert_eq!(found, (Vec::new(), names(&["b", "d", "e"])));
}

#[test]
fn a_trait_in_a_method_body_does_not_see_the_self_of_the_method() {
    let m = member("pub fn m(&self) {}");
    let body = "trait Tr {\n            fn f(&self) {\n                self.m();\n            }\n        }";
    assert_eq!(outcome(&m, &caller("&self", body), &[]), kept());
}

/// The kept cases of a `cfg` anywhere, the one-member rule and the path `Self::m` (AD-383).
#[path = "impl_receivers_cfg_tests.rs"]
mod cfg;
