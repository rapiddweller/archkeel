// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_facts::data::{CallableData, ValueData};
use archkeel_facts::SymbolFact;

use crate::collect::tests::run;
use crate::reply::Collected;

/// `kind qualified visibility` of each symbol record, sorted. The crate `a` has the module `ns.a`.
fn rows(source: &str, exclude_tests: bool) -> Vec<String> {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", source),
    ];
    let facts = run(&files, exclude_tests);
    list(&facts)
}

fn value(kind: &str, data: &ValueData) -> String {
    let vis = &data.visibility_detail.kind;
    format!("{kind} {} {vis}", data.qualified_name)
}

fn callable(kind: &str, data: &CallableData) -> String {
    let vis = &data.visibility_detail.kind;
    format!("{kind} {} {vis}", data.qualified_name)
}

fn list(facts: &Collected) -> Vec<String> {
    let mut found: Vec<String> = facts
        .symbols
        .iter()
        .map(|record| match &record.data {
            SymbolFact::Class(data) => {
                let vis = &data.visibility_detail.kind;
                format!("class {} {vis}", data.qualified_name)
            }
            SymbolFact::Function(data) => callable("function", data),
            SymbolFact::Method(data) => callable("method", data),
            SymbolFact::Constant(data) => value("constant", data),
            SymbolFact::StaticConstant(data) => value("static", data),
            SymbolFact::TypeAlias(data) => value("alias", data),
            SymbolFact::Macro(data) => value("macro", data),
            other => format!("unexpected {other:?}"),
        })
        .collect();
    found.sort();
    found
}

#[test]
fn each_form_of_item_is_a_definition_with_its_visibility() {
    let source = "pub fn a() {}\nfn b() {}\npub(crate) struct C;\npub(super) enum D { X, Y }\n\
        pub(in crate::m) trait E {}\nconst F: u8 = 1;\npub static G: u8 = 2;\ntype H = u8;\n\
        pub union U { x: u8 }\npub(self) fn s() {}\n";
    assert_eq!(
        rows(source, false),
        [
            "alias ns.a.H private",
            "class ns.a.C package",
            "class ns.a.D package",
            "class ns.a.E package",
            "class ns.a.U public",
            "constant ns.a.F private",
            "function ns.a.a public",
            "function ns.a.b private",
            "function ns.a.s private",
            "static ns.a.G public",
        ]
    );
}

#[test]
fn the_spelling_of_a_restricted_visibility_is_kept() {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        (
            "crates/src/lib.rs",
            "pub(in crate::m) fn f() {}\npub(crate) fn g() {}",
        ),
    ];
    let facts = run(&files, false);
    let mut spellings: Vec<&str> = facts
        .symbols
        .iter()
        .filter_map(|record| match &record.data {
            SymbolFact::Function(data) => Some(data.visibility_detail.spelling.as_str()),
            _ => None,
        })
        .collect();
    spellings.sort_unstable();
    assert_eq!(spellings, ["pub(crate)", "pub(in crate::m)"]);
}

#[test]
fn an_inherent_impl_gives_methods_of_its_type_and_a_trait_impl_gives_none() {
    let source = "pub struct T;\nimpl T {\n pub fn make() -> T { T }\n fn get(&self) {}\n}\n\
        impl Clone for T { fn clone(&self) -> T { T } }\npub trait R { fn need(&self); fn all() {} }\n";
    assert_eq!(
        rows(source, false),
        [
            "class ns.a.R public",
            "class ns.a.T public",
            "method ns.a.R.all public",
            "method ns.a.R.need public",
            "method ns.a.T.get private",
            "method ns.a.T.make public",
        ]
    );
}

#[test]
fn a_method_has_its_type_as_parent_and_the_type_lists_it() {
    let source = "pub struct T;\nimpl T { pub fn make() {} pub fn get(&self) {} }\n";
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", source),
    ];
    let facts = run(&files, false);
    let ids: std::collections::BTreeMap<&str, &str> = facts
        .symbols
        .iter()
        .map(|record| (record.title.as_str(), record.id.as_str()))
        .collect();
    let holder = ids["ns.a.T declaration"];
    let mut kinds = Vec::new();
    for record in &facts.symbols {
        if let SymbolFact::Method(data) = &record.data {
            let parent = data.lexical_parent_id.as_ref().map(|id| id.as_str());
            assert_eq!(parent, Some(holder));
            assert_eq!(data.parent.as_deref(), Some("ns.a.T"));
            kinds.push(format!("{:?}", data.method_kind));
        }
        if let SymbolFact::Class(data) = &record.data {
            let methods = &data.member_inventories[1];
            assert_eq!(methods.definition_ids.len(), 2);
            assert_eq!(
                methods.status,
                archkeel_facts::vocab::InventoryStatus::Partial
            );
        }
    }
    kinds.sort();
    assert_eq!(kinds, ["Some(Instance)", "Some(Static)"]);
}

#[test]
fn an_impl_of_a_type_that_the_module_does_not_define_gives_no_member() {
    let source = "impl Vec<u8> { fn a(&self) {} }\nimpl other::Type { fn b() {} }\n\
        impl<T> Missing<T> { fn c() {} }\nimpl &str { fn d() {} }\n";
    assert_eq!(rows(source, false), Vec::<String>::new());
}

#[test]
fn an_item_in_a_block_is_no_definition_of_the_module() {
    let source = "pub fn run() {\n fn inner() {}\n struct Local;\n impl Local { fn m() {} }\n}\n";
    assert_eq!(rows(source, false), ["function ns.a.run public"]);
}

#[test]
fn an_item_that_a_macro_generates_is_not_invented() {
    let source = "make! { pub struct Generated; }\nmacro_rules! make { ($t:item) => { $t }; }\n\
        #[macro_export]\nmacro_rules! shown { () => {}; }\npub struct Real;\n\
        impl Real { make_method!(); pub fn plain() {} }\n";
    assert_eq!(
        rows(source, false),
        [
            "class ns.a.Real public",
            "macro ns.a.make package",
            "macro ns.a.shown public",
            "method ns.a.Real.plain public",
        ]
    );
}

#[test]
fn a_test_item_is_a_definition_only_when_the_request_keeps_tests() {
    let source = "pub fn real() {}\n#[cfg(test)]\nfn only_test() {}\n#[test]\nfn a_test() {}\n\
        #[cfg(test)]\nmod tests { pub fn helper() {} }\n";
    assert_eq!(
        rows(source, true),
        ["function ns.a.real public"],
        "the request excludes tests"
    );
    let kept = rows(source, false);
    assert!(kept.contains(&"function ns.a.only_test private".to_owned()));
    assert!(kept.contains(&"function ns.a.a_test private".to_owned()));
}

#[test]
fn an_inline_module_names_its_items_and_scopes_the_impls() {
    let source = "pub mod m {\n pub struct S;\n impl S { pub fn f(&self) {} }\n}\n\
        pub struct S;\nimpl S { fn g() {} }\n";
    assert_eq!(
        rows(source, false),
        [
            "class ns.a.S public",
            "class ns.a.m.S public",
            "method ns.a.S.g private",
            "method ns.a.m.S.f public",
        ]
    );
}

#[test]
fn a_name_that_two_items_share_is_not_unique() {
    let source = "#[cfg(unix)]\nfn f() {}\n#[cfg(not(unix))]\nfn f() {}\nfn g() {}\n";
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", source),
    ];
    let facts = run(&files, false);
    let unique: Vec<(String, bool)> = facts
        .symbols
        .iter()
        .filter_map(|record| match &record.data {
            SymbolFact::Function(data) => Some((
                data.name.clone(),
                data.source_binding_unique.unwrap_or(false),
            )),
            _ => None,
        })
        .collect();
    assert!(unique.contains(&("g".to_owned(), true)));
    assert_eq!(
        unique
            .iter()
            .filter(|(name, one)| name == "f" && !one)
            .count(),
        2
    );
}

#[test]
fn a_definition_gives_no_gap_and_cites_its_name() {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", "m! {}\npub fn named() {}\n"),
    ];
    let facts = run(&files, false);
    assert!(
        facts.gaps.is_empty(),
        "an unread item is no gap: {:?}",
        facts.gaps
    );
    let record = &facts.symbols[0];
    let cited = facts
        .evidence
        .iter()
        .find(|e| e.id.as_str() == record.evidence_ids[0].as_str());
    assert_eq!(
        cited.map(|e| (e.line, e.excerpt.as_str())),
        Some((2, "pub fn named() {}"))
    );
}
