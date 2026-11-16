// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::path::Path;

use super::{schema, text, PATH};

#[test]
fn the_committed_frame_schema_equals_the_generated_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(PATH);
    let committed = std::fs::read_to_string(path).unwrap_or_default();
    assert!(
        committed == text().expect("the schema is JSON"),
        "the generated frame schema differs from schema/archkeel-core-frame-1.schema.json. Write \
         it with `cargo test -p archkeel-core -- --ignored write_the_frame_schema`"
    );
}

#[test]
fn the_frame_schema_is_closed_and_names_the_ruling_and_the_parts() {
    let value = schema();
    assert_eq!(value["additionalProperties"], false);
    for key in [
        "protocol",
        "status",
        "rules",
        "engine",
        "self_test",
        "unsupported",
        "html",
    ] {
        assert!(value["properties"].get(key).is_some(), "{key}");
    }
    assert!(value["properties"]["unsupported"].get("$ref").is_some());
    assert!(value["$defs"]["UnsupportedParts"]["properties"]
        .get("rules")
        .is_some());
}

#[test]
#[ignore = "writes the frame schema file; run it after a change of the frame types"]
fn write_the_frame_schema() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(PATH);
    std::fs::write(path, text().expect("the schema is JSON")).expect("written");
}
