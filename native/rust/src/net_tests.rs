// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `collect.rs`. Each text is a place where a crate name can hide.

use super::*;

fn names(text: &str) -> Vec<String> {
    let mut found = BTreeSet::new();
    walk(text.parse::<TokenStream>().unwrap(), &mut found);
    found.into_iter().collect()
}

fn has(found: &[String], name: &str) -> bool {
    found.iter().any(|found| found == name)
}

#[test]
fn an_identifier_counts_in_a_macro_body_an_attribute_stream_and_as_a_raw_identifier() {
    assert!(has(&names("other::call!(base_crate)"), "base_crate"));
    assert!(has(&names("other::attr(base_crate)"), "base_crate"));
    assert!(has(&names("r#base_crate::make()"), "base_crate"));
}

#[test]
fn the_name_of_an_attribute_is_a_helper_and_no_crate_unless_it_is_a_path() {
    // `#[serde(...)]` in a macro body names the helper of a derive.
    assert!(!has(&names("#[serde(default)] x: u8"), "serde"));
    assert!(!has(&names("#![serde(default)]"), "serde"));
    // A crate in the arguments, or at the start of a path, counts.
    assert!(has(&names("#[other(serde)] x: u8"), "serde"));
    assert!(has(&names("#[serde::attr] x: u8"), "serde"));
    assert!(has(&names("x = serde"), "serde"));
}

#[test]
fn a_string_counts_when_it_is_a_name_or_starts_with_one() {
    assert!(has(&names("\"base_crate\""), "base_crate"));
    assert!(has(&names("\"base_crate::make\""), "base_crate"));
    assert!(has(&names("r#\"base_crate::make\"#"), "base_crate"));
    assert!(!has(&names("\"see base_crate for more\""), "base_crate"));
}

#[test]
fn a_message_key_does_not_count() {
    let found = names("note = \"base_crate\", since = \"base_crate::x\", doc = \"base_crate\"");
    assert!(!has(&found, "base_crate"), "{found:?}");
    assert!(has(&found, "note"));
}

#[test]
fn brackets_nested_deep_cost_no_stack() {
    let deep = format!("{}base_crate{}", "(".repeat(100_000), ")".repeat(100_000));
    let mut found = BTreeSet::new();
    if let Ok(stream) = deep.parse::<TokenStream>() {
        walk(stream, &mut found);
        assert!(found.contains("base_crate"));
    }
}
