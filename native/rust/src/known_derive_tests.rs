// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a registry model must preserve every written helper path and every unproved identity.

use crate::collect::tests::run;
use crate::reply::Collected;

const MANIFEST: &str = "[package]\nname = \"app\"\nversion = \"0.0.0\"\nedition = \"2021\"\n[dependencies]\nserde = \"1.0\"\nschemars = \"=1.2.3\"\n";
const LOCK: &str = "version = 4\n\
[[package]]\nname = \"app\"\nversion = \"0.0.0\"\ndependencies = [\"serde\", \"schemars\"]\n\
[[package]]\nname = \"serde\"\nversion = \"1.0.229\"\nsource = \"registry+https://github.com/rust-lang/crates.io-index\"\nchecksum = \"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"\ndependencies = [\"serde_derive\"]\n\
[[package]]\nname = \"serde_derive\"\nversion = \"1.0.229\"\nsource = \"registry+https://github.com/rust-lang/crates.io-index\"\nchecksum = \"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"\n\
[[package]]\nname = \"schemars\"\nversion = \"1.2.3\"\nsource = \"registry+https://github.com/rust-lang/crates.io-index\"\nchecksum = \"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"\ndependencies = [\"schemars_derive\"]\n\
[[package]]\nname = \"schemars_derive\"\nversion = \"1.2.3\"\nsource = \"registry+https://github.com/rust-lang/crates.io-index\"\nchecksum = \"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\"\n";

fn facts(manifest: &str, source: &str, lock: &str) -> Collected {
    run(
        &[
            ("crates/Cargo.toml", manifest),
            ("crates/Cargo.lock", lock),
            ("crates/src/lib.rs", "mod a; mod b;"),
            ("crates/src/a.rs", source),
            ("crates/src/b.rs", "pub mod helper {}"),
        ],
        false,
    )
}

fn derive_gaps(facts: &Collected) -> Vec<&str> {
    facts
        .gaps
        .iter()
        .filter(|g| g.title.contains("derive macro"))
        .map(|g| g.title.as_str())
        .collect()
}

#[test]
fn proven_registry_derives_keep_helper_paths_as_edges_without_an_expansion_gap() {
    for source in [
        "use serde::Serialize; #[derive(Serialize)] struct S { #[serde(with = \"crate::b::helper\")] x: u8 }",
        "use serde::Deserialize as De; #[derive(De)] struct S { #[serde(default)] x: u8 }",
        "#[derive(schemars::JsonSchema)] struct S { #[schemars(with = \"crate::b::T\")] x: u8 }",
    ] {
        let found = facts(MANIFEST, source, LOCK);
        assert!(derive_gaps(&found).is_empty(), "{:?}", derive_gaps(&found));
        if source.contains("crate::b") {
            assert!(found.imports.iter().any(|r| r.data.data().source_module.as_str() == "ns.app.a"
                && r.data.data().target_module.as_str() == "ns.app.b"));
        }
    }
}

#[test]
fn unproved_sources_globs_patches_and_helper_values_keep_the_gap() {
    for (manifest, source, lock) in [
        (
            MANIFEST.to_owned(),
            "use serde::*; #[derive(Serialize)] struct S;",
            LOCK.to_owned(),
        ),
        (
            MANIFEST.replace("serde = \"1.0\"", "serde = { path = \"../serde\" }"),
            "#[derive(serde::Serialize)] struct S;",
            LOCK.to_owned(),
        ),
        (
            MANIFEST.replace(
                "serde = \"1.0\"",
                "renamed = { package = \"serde\", path = \"../serde\" }",
            ),
            "#[derive(renamed::Serialize)] struct S;",
            LOCK.to_owned(),
        ),
        (
            format!("{MANIFEST}\n[patch.crates-io]\nserde_derive = {{ path = \"../mac\" }}"),
            "#[derive(serde::Serialize)] struct S;",
            LOCK.to_owned(),
        ),
        (
            MANIFEST.to_owned(),
            "#[derive(serde::Serialize)] #[serde(unknown_key)] struct S;",
            LOCK.to_owned(),
        ),
        (
            MANIFEST.to_owned(),
            "#[derive(serde::Serialize)] struct S { #[serde(with = \"not a path\")] x: u8 }",
            LOCK.to_owned(),
        ),
        (
            MANIFEST.to_owned(),
            "#[derive(serde::Serialize)] struct S;",
            String::new(),
        ),
        (MANIFEST.replace("version = \"0.0.0\"", "version = \"0.0.1\""), "#[derive(serde::Serialize)] struct S;", LOCK.to_owned()),
        (MANIFEST.replace("serde = \"1.0\"", "serde = \"2\""), "#[derive(serde::Serialize)] struct S;", LOCK.to_owned()),
        (MANIFEST.to_owned(), "#[derive(serde::Serialize)] #[cfg_attr(unix, serde(with = \"helper\"))] struct S;", LOCK.to_owned()),
        (MANIFEST.to_owned(), "#[derive(serde::Serialize)] struct S { #[serde(bound = \"T: Trait<{m!()}>\")] x: u8 }", LOCK.to_owned()),
        (
            MANIFEST.to_owned(),
            "#[derive(serde::Serialize)] struct S;",
            LOCK.replace(
                "registry+https://github.com/rust-lang/crates.io-index",
                "git+https://example.invalid/serde",
            ),
        ),
    ] {
        let found = facts(&manifest, source, &lock);
        assert!(!derive_gaps(&found).is_empty(), "{manifest}\n{source}");
    }
}

#[test]
fn a_bare_helper_module_is_an_edge_not_an_unplaced_name() {
    let found = run(&[
        ("crates/Cargo.toml", MANIFEST), ("crates/Cargo.lock", LOCK),
        ("crates/src/lib.rs", "mod a;"),
        ("crates/src/a.rs", "mod codec; #[derive(serde::Serialize)] struct S { #[serde(with = \"codec\")] x: u8 }"),
        ("crates/src/a/codec.rs", ""),
    ], false);
    assert!(derive_gaps(&found).is_empty());
    assert!(found.imports.iter().any(|r| r.data.data().source_module.as_str() == "ns.app.a"
        && r.data.data().target_module.as_str() == "ns.app.a.codec"));
}

#[test]
fn a_registry_dependency_can_be_renamed_but_a_workspace_macro_is_not_registry_code() {
    let found = facts(&MANIFEST.replace("serde = \"1.0\"", "renamed = { package = \"serde\", version = \"1.0\" }"), "#[derive(renamed::Serialize)] struct S;", LOCK);
    assert!(derive_gaps(&found).is_empty());
    let found = run(&[
        ("crates/Cargo.toml", "[workspace]\nmembers=[\"app\", \"mac\"]"),
        ("crates/Cargo.lock", LOCK),
        ("crates/app/Cargo.toml", "[package]\nname=\"app\"\nversion=\"0.0.0\"\nedition=\"2021\"\n[dependencies]\nserde={path=\"../mac\"}"),
        ("crates/app/src/lib.rs", "#[derive(serde::Serialize)] struct S;"),
        ("crates/mac/Cargo.toml", "[package]\nname=\"serde\"\nversion=\"1.0.229\"\nedition=\"2021\"\n[lib]\nproc-macro=true"),
        ("crates/mac/src/lib.rs", "extern crate proc_macro; #[proc_macro_derive(Serialize)] pub fn derive(_:proc_macro::TokenStream)->proc_macro::TokenStream { \"fn hidden() {}\".parse().unwrap() }"),
    ], false);
    assert!(!derive_gaps(&found).is_empty());
}

#[test]
fn enum_variant_globs_and_block_local_globs_cannot_shadow_module_derives() {
    for source in [
        "enum E { V } use E::*; #[derive(Clone, Debug)] struct S;",
        "#[derive(Clone, Debug)] struct S; fn f() { use external::*; }",
        "mod safe { pub struct T; } use safe::*; #[derive(Clone, Debug)] struct S;",
    ] {
        let found = facts(MANIFEST, source, LOCK);
        assert!(
            derive_gaps(&found).is_empty(),
            "{source}: {:?}",
            derive_gaps(&found)
        );
    }
}

#[test]
fn external_and_macro_reexporting_globs_still_withhold_builtin_identity() {
    for source in [
        "use external::*; #[derive(Clone)] struct S;",
        "mod mac { pub use external::Clone; } use mac::*; #[derive(Clone)] struct S;",
    ] {
        assert!(
            !derive_gaps(&facts(MANIFEST, source, LOCK)).is_empty(),
            "{source}"
        );
    }
}
