// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// B1: a prelude attribute macro can be replaced through the macro namespace.

use super::*;

fn shadowed_attribute(name: &str, source: &str, root_import: &str) {
    let root = attribute_repository(name);
    let macros = ["test", "global_allocator", "derive"]
        .map(|name| format!("#[proc_macro_attribute] pub fn {name}(_: proc_macro::TokenStream, _: proc_macro::TokenStream) -> proc_macro::TokenStream {{ \"pub fn y() {{ crate::a::x(); }}\".parse().unwrap() }}"))
        .join("\n");
    fs::write(
        root.join("crates/mac/src/lib.rs"),
        format!("extern crate proc_macro; {macros}"),
    )
    .unwrap();
    fs::write(
        root.join("crates/example/src/lib.rs"),
        format!("{root_import} pub mod a; pub mod b;"),
    )
    .unwrap();
    fs::write(root.join("crates/example/src/b.rs"), source).unwrap();
    let checked = std::process::Command::new(env!("CARGO"))
        .args(["check", "--offline", "--quiet"])
        .env("PATH", env!("PATH"))
        .current_dir(root.join("crates"))
        .output()
        .unwrap();
    if source.starts_with("use mac::*;") {
        assert!(!checked.status.success());
        assert!(String::from_utf8_lossy(&checked.stderr).contains("ambiguous"));
    } else {
        assert!(
            checked.status.success(),
            "{}",
            String::from_utf8_lossy(&checked.stderr)
        );
    }
    let (found, _) = frame(&request(&root));
    assert_eq!(found["rules"]["NO-HIDDEN"][1], "UNKNOWN", "{found}");
    assert_eq!(found["status"], "UNKNOWN", "{found}");
}

#[test]
fn an_imported_test_attribute_cannot_hide_a_call() {
    shadowed_attribute(
        "shadow-test",
        "use mac::test; #[test] pub fn y() {} pub fn w() { y() }",
        "",
    );
}

#[test]
fn an_imported_global_allocator_attribute_cannot_hide_a_call() {
    shadowed_attribute(
        "shadow-allocator",
        "use mac::global_allocator; #[global_allocator] pub fn y() {}",
        "",
    );
}

#[test]
fn an_imported_derive_attribute_cannot_hide_a_call() {
    shadowed_attribute(
        "shadow-derive",
        "use mac::derive; #[derive(Debug)] pub fn y() {} pub fn w() { y() }",
        "",
    );
}

#[test]
fn a_glob_can_replace_a_prelude_attribute_macro() {
    shadowed_attribute(
        "shadow-glob",
        "use mac::*; #[test] pub fn y() {} pub fn w() { y() }",
        "",
    );
}

#[test]
fn a_macro_use_extern_crate_can_replace_a_childs_prelude_attribute_macro() {
    shadowed_attribute(
        "shadow-extern",
        "#[test] pub fn y() {} pub fn w() { y() }",
        "#[macro_use] extern crate mac;",
    );
}
