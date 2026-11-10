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
            "d::Z".to_owned(),
            "text".to_owned()
        ])
    );
    assert_eq!(
        string_chains("a = \"no path here\", b = 1"),
        Some(Vec::new())
    );
    // A text that is one name is a path of one segment: `with = "humantime_serde"`.
    assert_eq!(
        string_chains("with = \"humantime_serde\""),
        Some(vec!["humantime_serde".to_owned()])
    );
    assert_eq!(
        string_chains("note = \"humantime_serde\""),
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

#[test]
fn a_string_under_any_other_key_is_read_as_a_path() {
    for key in [
        "getter",
        "as",
        "schema_with",
        "custom",
        "function",
        "format_with",
        "method",
        "with",
        "bound",
        "unknown_key_of_a_new_crate",
    ] {
        let text = format!("{key} = \"dep::X\"");
        assert_eq!(
            string_chains(&text),
            Some(vec!["dep::X".to_owned()]),
            "{key}"
        );
    }
    for key in [
        "note",
        "since",
        "reason",
        "message",
        "expecting",
        "expected",
        "rename",
        "alias",
        "doc",
    ] {
        let text = format!("{key} = \"dep::X\"");
        assert_eq!(string_chains(&text), Some(Vec::new()), "{key}");
    }
    // A text that does not read under such a key is not dropped.
    assert_eq!(string_chains("getter = \"(dep::X\""), None);
}

#[test]
fn a_raw_identifier_is_the_name_without_its_prefix() {
    assert_eq!(plain(&"r#base_crate"), "base_crate");
    assert_eq!(plain(&"base_crate"), "base_crate");
    let found = chains(stream("r#base_crate::make(); x::r#y")).unwrap();
    let names: Vec<_> = found.iter().map(|c| c.names.join("::")).collect();
    assert_eq!(names, ["base_crate::make", "x::y"]);
}
