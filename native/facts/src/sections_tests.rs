// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The types hold every record kind of the Python, Dart and TypeScript collectors.
//
// `testdata` holds the widest and the narrowest record of each kind of each producer, taken from
// the WP1 replies of issue #880. The same check passed on all 156 853 records of those replies and
// on the 21 980 import records of the x35 tree (see the pull request).

use std::path::Path;

use crate::{GapFact, Record, Section};
use serde_json::Value;

fn reply(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("testdata")
        .join(name);
    let text = std::fs::read_to_string(path).expect("the sample reply is readable");
    serde_json::from_str(&text).expect("the sample reply is JSON")
}

/// Decode each section and each coverage gap, encode it again, and give the count of records.
fn round_trip(name: &str) -> usize {
    let reply = reply(name);
    let mut count = 0;
    for section in reply["facts"]["sections"].as_array().expect("a list") {
        let typed: Result<Section, _> = serde_json::from_value(section.clone());
        let typed = typed.expect(name);
        assert_eq!(&serde_json::to_value(&typed).expect("JSON"), section);
        count += section["records"].as_array().map_or(0, Vec::len);
    }
    for gap in reply["facts"]["coverage"]["gaps"]
        .as_array()
        .expect("a list")
    {
        let typed: Record<GapFact> = serde_json::from_value(gap.clone()).expect("a gap");
        assert_eq!(&serde_json::to_value(&typed).expect("JSON"), gap);
        count += 1;
    }
    count
}

#[test]
fn each_python_record_kind_decodes_and_encodes_equal() {
    assert!(round_trip("python.json") == 39);
}

#[test]
fn each_dart_record_kind_decodes_and_encodes_equal() {
    assert!(round_trip("dart.json") == 13);
}

#[test]
fn each_typescript_record_kind_decodes_and_encodes_equal() {
    assert!(round_trip("typescript.json") == 27);
}

#[test]
fn the_python_exception_gap_has_a_closed_kind_and_keeps_its_wire_kind() {
    let reply = reply("python.json");
    let gap = reply["facts"]["coverage"]["gaps"]
        .as_array()
        .and_then(|gaps| gaps.iter().find(|gap| gap["kind"] == "SyntaxError"))
        .expect("a SyntaxError gap")
        .clone();
    let typed: Record<GapFact> = serde_json::from_value(gap).expect("a gap");
    assert_eq!(typed.kind(), crate::vocab::Kind::ExceptionGap);
    assert!(
        matches!(&typed.data, GapFact::ExceptionGap { exception, .. } if exception == "SyntaxError")
    );
    let wire = serde_json::to_value(&typed).expect("JSON");
    assert_eq!(wire["kind"], "SyntaxError");
    let read: Value =
        serde_json::from_slice(&crate::readset::to_vec(&typed).expect("JSON")).expect("JSON");
    assert_eq!(read["kind"], "exception_gap");
    assert_eq!(read["data"]["exception"], "SyntaxError");
}
