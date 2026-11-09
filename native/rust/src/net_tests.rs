// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `collect.rs`. Each text is a place where a crate name can hide.

use super::*;

fn names(text: &str) -> Vec<String> {
    mentioned(text).unwrap().into_iter().collect()
}

#[test]
fn an_identifier_counts_in_code_in_a_macro_in_an_attribute_and_as_a_raw_identifier() {
    assert!(names("fn f() { let base_crate = 1; }").contains(&"base_crate".to_owned()));
    assert!(names("fn f() { other::call!(base_crate); }").contains(&"base_crate".to_owned()));
    assert!(names("#[other::attr(base_crate)]\nstruct S;").contains(&"base_crate".to_owned()));
    assert!(names("fn f() { r#base_crate::make(); }").contains(&"base_crate".to_owned()));
    assert!(names("#![doc = base_crate::readme!()]").contains(&"base_crate".to_owned()));
}

#[test]
fn a_string_counts_when_it_is_a_name_or_starts_with_one() {
    assert!(names("const A: &str = \"base_crate\";").contains(&"base_crate".to_owned()));
    assert!(names("const A: &str = \"base_crate::make\";").contains(&"base_crate".to_owned()));
    assert!(names("const A: &str = r#\"base_crate::make\"#;").contains(&"base_crate".to_owned()));
    let prose = names("const A: &str = \"see base_crate for more\";");
    assert!(!prose.contains(&"base_crate".to_owned()));
}

#[test]
fn a_comment_a_doc_comment_and_a_message_key_do_not_count() {
    let quiet = "// base_crate in a comment\n/* base_crate */\n/// base_crate in a doc comment\n\
                 //! base_crate in an inner doc comment\n#[doc = \"base_crate::x\"]\n\
                 #[deprecated(note = \"base_crate\")]\nfn f() {}";
    let found = names(quiet);
    assert!(!found.contains(&"base_crate".to_owned()), "{found:?}");
    // The key itself is a name; the string is not.
    assert!(found.contains(&"note".to_owned()));
}

#[test]
fn brackets_nested_deep_cost_no_stack_and_a_text_that_does_not_lex_is_none() {
    let deep = format!("{}base_crate{}", "(".repeat(100_000), ")".repeat(100_000));
    assert!(mentioned(&deep).is_none() || names(&deep).contains(&"base_crate".to_owned()));
    assert!(mentioned("fn f() { \"open").is_none());
}
