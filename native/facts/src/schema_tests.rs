// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::path::Path;

use super::{schema, text, PATH};

fn committed() -> String {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(PATH);
    std::fs::read_to_string(&path).unwrap_or_default()
}

#[test]
fn the_committed_schema_equals_the_generated_schema() {
    let generated = text().expect("the schema is JSON");
    assert!(
        committed() == generated,
        "the generated schema differs from {PATH}: a published schema never changes (AD-345). \
         Write a first schema with `cargo test -p archkeel-facts -- --ignored write_the_schema`"
    );
}

#[test]
fn the_schema_defines_each_section_and_the_closed_vocabularies() {
    let value = schema();
    let definitions = value["$defs"].as_object().expect("a bundle of definitions");
    for name in [
        "Section",
        "Record_ImportFact",
        "Record_GapFact",
        "ImportData",
        "Kind",
        "ReasonCode",
        "Producer",
    ] {
        assert!(definitions.contains_key(name), "no definition {name}");
    }
    let kinds: Vec<&str> = definitions["Kind"]["enum"]
        .as_array()
        .expect("the list of kinds")
        .iter()
        .filter_map(|kind| kind.as_str())
        .collect();
    assert_eq!(kinds.len(), crate::vocab::Kind::ALL.len());
    assert!(kinds.contains(&"exception_gap"));
    // The edge of a macro template is its own kind, so no cycle or layer rule reads it (AD-349).
    assert!(kinds.contains(&"macro_body"));
    assert!(!kinds.contains(&"SyntaxError"));
}

#[test]
#[ignore = "writes the schema file; run it only for a new protocol"]
fn write_the_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(PATH);
    std::fs::write(path, text().expect("the schema is JSON")).expect("the schema is written");
}
