// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::path::Path;

use super::{request_schema, request_text, schema, text, PATH, REQUEST_PATH};

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
    // A `macro_rules!` definition is not a function: the report shows it as a macro (AD-351).
    assert!(kinds.contains(&"macro"));
    assert!(!kinds.contains(&"SyntaxError"));
}

#[test]
#[ignore = "writes the schema file; run it only for a new protocol"]
fn write_the_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(PATH);
    std::fs::write(path, text().expect("the schema is JSON")).expect("the schema is written");
}

#[test]
fn the_committed_request_schema_equals_the_generated_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(REQUEST_PATH);
    let committed = std::fs::read_to_string(path).unwrap_or_default();
    assert!(
        committed == request_text().expect("the schema is JSON"),
        "the generated request schema differs from {REQUEST_PATH}. A request change needs a new \
         protocol version. Write it with `cargo test -p archkeel-facts -- --ignored \
         write_the_request_schema`"
    );
}

#[test]
fn the_request_schema_lists_the_versions_of_the_one_list() {
    let value = request_schema();
    let versions: Vec<&str> = value["$defs"]["Version"]["enum"]
        .as_array()
        .expect("the list of versions")
        .iter()
        .filter_map(|version| version.as_str())
        .collect();
    let listed: Vec<&str> = crate::protocol::Version::ALL
        .iter()
        .map(|version| version.as_str())
        .collect();
    assert_eq!(versions, listed);
}

#[test]
fn every_version_with_a_compressed_reply_names_a_reply_version_of_the_envelope() {
    use crate::envelope::ProtocolVersion;
    use crate::protocol::{reply_version, Version};
    for version in Version::ALL {
        let reply = reply_version(*version);
        let compressed = reply.compressed().map(ProtocolVersion::as_str);
        assert_eq!(compressed, Some(reply.as_str()), "{version:?}");
    }
    assert_eq!(Version::V3.compressed(), None);
}

#[test]
#[ignore = "writes the request schema file; run it only for a new request"]
fn write_the_request_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(REQUEST_PATH);
    std::fs::write(path, request_text().expect("the schema is JSON")).expect("written");
}
