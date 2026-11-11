// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::{Area, ExceptionName, Kind, Status};

#[test]
fn each_kind_text_parses_to_its_kind() {
    for kind in Kind::ALL {
        assert_eq!(Kind::parse(kind.as_str()), Some(*kind));
        let json = serde_json::to_string(kind).expect("a kind is JSON");
        assert_eq!(json, format!("\"{}\"", kind.as_str()));
    }
}

#[test]
fn a_value_outside_a_vocabulary_is_an_error() {
    assert!(serde_json::from_str::<Status>("\"maybe\"").is_err());
    assert!(serde_json::from_str::<Area>("\"Source\"").is_err());
    assert_eq!(Kind::parse("SyntaxError"), None);
}

#[test]
fn the_shadowed_module_name_is_read_but_not_in_the_9_schema() {
    assert_eq!(
        ExceptionName::parse("ShadowedModule"),
        Some(ExceptionName::ShadowedModule)
    );
    assert!(!ExceptionName::ShadowedModule.in_v9());
    let text = crate::schema::text().expect("the schema");
    assert!(!text.contains("ShadowedModule"));
}
