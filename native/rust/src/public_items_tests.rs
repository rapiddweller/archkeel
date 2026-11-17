// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `unused_public` judges each public module-level item that the collector states (#1450,
// AD-718). Each construct below either gives a record, a record whose name is not read (basis
// `macro_call`), or a gap with its place.

use archkeel_facts::nested::VisibilityDetail;
use archkeel_facts::SymbolFact;

use crate::collect::tests::run;
use crate::reply::Collected;

fn facts(source: &str) -> Collected {
    let files = [
        ("crates/Cargo.toml", "[package]\nname = \"a\"\n"),
        ("crates/src/lib.rs", source),
    ];
    run(&files, false)
}

/// `kind name visibility basis` of each public module-level record, sorted.
fn public(source: &str) -> Vec<String> {
    let row = |kind: &str, name: &str, parent: &Option<String>, v: &VisibilityDetail| {
        (parent.is_none() && v.kind == "public").then(|| format!("{kind} {name} {}", v.basis))
    };
    let mut found: Vec<String> = facts(source)
        .symbols
        .iter()
        .filter_map(|record| match &record.data {
            SymbolFact::Class(d) => row("class", &d.name, &d.parent, &d.visibility_detail),
            SymbolFact::Function(d) => row("function", &d.name, &d.parent, &d.visibility_detail),
            SymbolFact::Constant(d) => row("constant", &d.name, &d.parent, &d.visibility_detail),
            SymbolFact::StaticConstant(d) => {
                row("static", &d.name, &d.parent, &d.visibility_detail)
            }
            SymbolFact::TypeAlias(d) => row("alias", &d.name, &d.parent, &d.visibility_detail),
            SymbolFact::Macro(d) => row("macro", &d.name, &d.parent, &d.visibility_detail),
            SymbolFact::DynamicBinding(d) => row("any", &d.name, &d.parent, &d.visibility_detail),
            _ => None,
        })
        .collect();
    found.sort();
    found
}

#[test]
fn the_functions_and_statics_of_an_extern_block_are_items() {
    let source =
        "extern \"C\" {\n    pub fn ext();\n    pub static EXT: u8;\n    fn hidden();\n}\n";
    assert_eq!(
        public(source),
        ["function ext declared", "static EXT declared"]
    );
}

#[test]
fn a_macro_call_publishes_the_items_of_its_expansion() {
    let literal = "macro_rules! mk {\n    () => {\n        pub fn made() {}\n        pub const C: u8 = 1;\n    };\n}\nmk!();\n";
    assert_eq!(
        public(literal),
        ["constant C declared", "function made declared"]
    );
    // The call gives the name: the kind and the place are stated, the name is not read.
    let named =
        "macro_rules! mk {\n    ($n:ident) => {\n        pub fn $n() {}\n    };\n}\nmk!(made);\n";
    assert_eq!(public(named), ["function $n macro_call"]);
    // An inline module of the expansion holds items that are not read; an exported macro is one.
    let module = "macro_rules! mk {\n    () => {\n        pub mod inner {\n            pub fn f() {}\n        }\n        #[macro_export]\n        macro_rules! made {\n            () => {};\n        }\n    };\n}\nmk!();\n";
    assert_eq!(
        public(module),
        ["any inner macro_call", "macro made declared"]
    );
    let private = "macro_rules! mk {\n    () => {\n        mod inner {\n            pub fn f() {}\n        }\n    };\n}\nmk!();\n";
    assert_eq!(public(private), ["any inner macro_call"]);
}

#[test]
fn a_visibility_that_the_call_gives_is_public_only_with_a_bare_pub() {
    let rules = "macro_rules! mk {\n    ($v:vis) => {\n        $v fn made() {}\n    };\n}\n";
    assert_eq!(
        public(&format!("{rules}mk!(pub(crate));\n")),
        Vec::<String>::new()
    );
    assert_eq!(
        public(&format!("{rules}mk!(pub);\n")),
        ["function made macro_call"]
    );
}

#[test]
fn an_arm_that_the_call_cannot_match_publishes_nothing() {
    // The accessor arm is reached only from inside an `impl` body: its `pub fn` is a member.
    let source = "pub struct S;\nmacro_rules! mk {\n    (@accessor $f:ident) => {\n        pub fn $f(&self) {}\n    };\n    ($t:ident, $f:ident) => {\n        impl $t {\n            mk!(@accessor $f);\n        }\n    };\n}\nmk!(S, get);\n";
    assert_eq!(public(source), ["class S declared"]);
}

#[test]
fn an_item_that_the_scan_cannot_parse_is_a_gap_with_its_place() {
    let found = facts("pub macro made() {}\npub fn kept() {}\n");
    let gaps: Vec<&str> = found.gaps.iter().map(|gap| gap.title.as_str()).collect();
    assert_eq!(
        gaps,
        ["An item that the scan cannot parse may declare a public symbol"]
    );
}
