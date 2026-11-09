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

fn string_chains(text: &str) -> Option<Vec<String>> {
    let mut found = Vec::new();
    string_paths(stream(text), 0, &mut found)?;
    Some(found.iter().map(|chain| chain.names.join("::")).collect())
}

#[test]
fn a_string_with_a_path_or_a_bound_gives_its_paths() {
    assert_eq!(
        string_chains(
            "with = \"crate::codec\", bound = \"T: b::X + c::Y<d::Z>\", other = \"text\""
        ),
        Some(vec![
            "crate::codec".to_owned(),
            "b::X".to_owned(),
            "c::Y".to_owned(),
            "d::Z".to_owned()
        ])
    );
    assert_eq!(
        string_chains("a = \"no path here\", b = 1"),
        Some(Vec::new())
    );
}

#[test]
fn a_string_with_a_path_that_does_not_read_is_never_dropped_silently() {
    // An unbalanced bracket is not a token stream.
    assert_eq!(string_chains("bound = \"T: (a::B\""), None);
    let deep = format!(
        "{}a::b{}",
        "(".repeat(MAX_DEPTH + 2),
        ")".repeat(MAX_DEPTH + 2)
    );
    assert_eq!(string_chains(&format!("bound = \"{deep}\"")), None);
}

#[test]
fn splits_only_at_the_top_level() {
    let parts = split_commas(stream("feature = \"x\", allow(a, b), doc"));
    assert_eq!(parts.len(), 3);
    assert_eq!(first_name(&parts[1]).as_deref(), Some("allow"));
    assert_eq!(first_name(&parts[0]).as_deref(), Some("feature"));
}
