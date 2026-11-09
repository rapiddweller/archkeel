// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the scan of macro bodies and attributes.

use super::*;

fn stream(text: &str) -> TokenStream {
    text.parse().unwrap()
}

fn written(text: &str) -> Vec<String> {
    chains(stream(text))
        .unwrap()
        .iter()
        .map(|chain| chain.names.join("::"))
        .collect()
}

#[test]
fn reads_each_chain_also_inside_groups() {
    assert_eq!(
        written("a::b, [c::d::e], f(g), ::h::i, j : k"),
        ["a::b", "c::d::e", "h::i"]
    );
}

#[test]
fn a_chain_needs_two_names_and_a_double_colon() {
    assert_eq!(written("a:: 1, b :c, d::<T>"), Vec::<String>::new());
}

#[test]
fn a_stream_nested_too_deep_is_cut_and_not_followed() {
    let deep = format!(
        "{}a::b{}",
        "(".repeat(MAX_DEPTH + 2),
        ")".repeat(MAX_DEPTH + 2)
    );
    assert!(chains(stream(&deep)).is_none());
}

#[test]
fn a_string_is_a_path_only_when_it_is_nothing_else() {
    assert_eq!(
        string_path("\"crate::codec\""),
        Some(vec!["crate".to_owned(), "codec".to_owned()])
    );
    for text in [
        "\"codec\"",
        "\"a::\"",
        "\"a b::c\"",
        "\"see a::b\"",
        "\"1a::b\"",
        "x",
    ] {
        assert_eq!(string_path(text), None, "{text}");
    }
    let mut found = Vec::new();
    string_paths(
        stream("with = \"serde_with::codec\", other = \"text\""),
        0,
        &mut found,
    );
    assert_eq!(found.len(), 1);
}

#[test]
fn splits_only_at_the_top_level() {
    let parts = split_commas(stream("feature = \"x\", allow(a, b), doc"));
    assert_eq!(parts.len(), 3);
    assert_eq!(first_name(&parts[1]).as_deref(), Some("allow"));
    assert_eq!(first_name(&parts[0]).as_deref(), Some("feature"));
}
