// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a call of a macro whose expansion the scan does not read is a gap unless the
// identity proof names a macro of `std` or a reviewed registry `macro_rules!` (#1371, AD-662).

use crate::collect::tests::run;
use crate::reply::Collected;

const MANIFEST: &str = "[package]\nname = \"app\"\nversion = \"0.0.0\"\nedition = \"2021\"\n[dependencies]\nserde_json = \"1.0\"\nschemars = \"=1.2.3\"\n";

fn lock(json: &str) -> String {
    let package = |name: &str, version: &str, sum: char| {
        let checksum: String = std::iter::repeat_n(sum, 64).collect();
        format!(
            "[[package]]\nname = \"{name}\"\nversion = \"{version}\"\nsource = \"registry+https://github.com/rust-lang/crates.io-index\"\nchecksum = \"{checksum}\"\n\n"
        )
    };
    format!(
        "version = 4\n\n[[package]]\nname = \"app\"\nversion = \"0.0.0\"\ndependencies = [\"serde_json\", \"schemars\"]\n\n{}{}",
        package("serde_json", json, 'a'),
        package("schemars", "1.2.3", 'b')
    )
}

fn unread(source: &str, json: &str) -> Vec<String> {
    let found: Collected = run(
        &[
            ("crates/Cargo.toml", MANIFEST),
            ("crates/Cargo.lock", &lock(json)),
            ("crates/src/lib.rs", "mod a;\nmod b;\n"),
            ("crates/src/a.rs", source),
            ("crates/src/b.rs", "pub fn f() {}\n"),
        ],
        false,
    );
    (found.gaps.iter())
        .filter(|gap| gap.title.contains("is no macro_rules! of the workspace"))
        .map(|gap| gap.title.clone())
        .collect()
}

#[test]
fn a_std_macro_and_a_reviewed_registry_macro_are_read_through_their_tokens() {
    for source in [
        "pub fn f() -> String {\n    format!(\"{}\", 1)\n}\n",
        "pub fn f() {\n    core::assert!(true);\n}\n",
        // A function of the name is in the value namespace: it cannot bind the macro.
        "fn matches() {}\npub fn f() -> bool {\n    matches!(1, 1)\n}\n",
        "use serde_json::json;\npub fn f() -> serde_json::Value {\n    json!({\"a\": 1})\n}\n",
        "pub fn f() -> serde_json::Value {\n    serde_json::json!(1)\n}\n",
        "pub fn f() -> schemars::Schema {\n    schemars::json_schema!({})\n}\n",
    ] {
        assert_eq!(unread(source, "1.0.154"), Vec::<String>::new(), "{source}");
    }
}

#[test]
fn an_unproved_identity_keeps_the_gap() {
    for (source, json) in [
        // Another locked version than the reviewed one.
        (
            "use serde_json::json;\npub fn f() {\n    json!(1);\n}\n",
            "1.0.153",
        ),
        // A `use` may bind the std name to a macro of another crate.
        (
            "use dep::format;\npub fn f() {\n    format!(1);\n}\n",
            "1.0.154",
        ),
        // An `impl` in the call tokens may be written as an item.
        (
            "pub fn f() {\n    format!(\"{}\", { impl Copy for crate::b::T {} 1 });\n}\n",
            "1.0.154",
        ),
        ("pub fn f() {\n    dep::make!();\n}\n", "1.0.154"),
    ] {
        assert_eq!(unread(source, json).len(), 1, "{source}");
    }
}

#[test]
fn a_macro_rules_of_the_name_elsewhere_in_the_crate_keeps_the_gap() {
    // The macro of `g` is out of the textual scope of the call in `f`, which `visible` reads.
    // The proof reads no textual scope: a `macro_rules!` of the name in the crate withholds it.
    let source = "fn g() {\n    macro_rules! format {\n        ($($t:tt)*) => {};\n    }\n}\n\
                  pub fn f() -> String {\n    format!(\"{}\", 1)\n}\n";
    assert_eq!(unread(source, "1.0.154").len(), 1);
}
