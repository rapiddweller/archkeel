// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::{Area, Kind, Status};

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
