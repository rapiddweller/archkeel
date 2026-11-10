// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The protocol 9 wire of one import record, byte for byte, its read-set and the decode errors.

use crate::data::ImportData;
use crate::ids::{EvidenceId, FactId, ModuleName, PackageName};
use crate::nullable::Nullable;
use crate::vocab::{Area, EvidenceClass};
use crate::{readset, ImportFact, Record, Section};
use serde_json::Value;

/// The import record as the native TypeScript collector writes it before this crate (`imports.rs`).
const WIRE: &str = concat!(
    r#"{"id":"IMP-0123456789abcdef","evidence_class":"FACT","area":"source","kind":"import","#,
    r#""title":"app.a_x2e_ts imports ./b","subjects":["app.a_x2e_ts","app.b_x2e_ts"],"#,
    r#""evidence_ids":["EVD-0123456789abcdef"],"rule_ids":[],"fact_ids":[],"provenance":[],"#,
    r#""data":{"source_module":"app.a_x2e_ts","source_package":"app","#,
    r#""target_module":"app.b_x2e_ts","target_package":"app","symbol":null,"binding":null,"#,
    r#""symbols_known":false,"specifier":"./b","type_only":false,"relative_level":0,"#,
    r#""under_type_checking":false,"reexport":false,"module_level_import":true}}"#
);

fn import() -> Record<ImportFact> {
    Record {
        id: FactId::new("IMP-0123456789abcdef"),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: "app.a_x2e_ts imports ./b".to_owned(),
        subjects: vec!["app.a_x2e_ts".to_owned(), "app.b_x2e_ts".to_owned()],
        evidence_ids: vec![EvidenceId::new("EVD-0123456789abcdef")],
        fact_ids: Vec::new(),
        data: ImportFact::Import(ImportData {
            source_module: ModuleName::new("app.a_x2e_ts"),
            source_package: PackageName::new("app"),
            target_module: ModuleName::new("app.b_x2e_ts"),
            target_package: PackageName::new("app"),
            symbol: None,
            binding: None,
            symbols_known: false,
            specifier: Some("./b".to_owned()),
            type_only: Some(false),
            relative_level: 0,
            under_type_checking: false,
            reexport: false,
            module_level_import: true,
            ..ImportData::statement()
        }),
    }
}

#[test]
fn the_wire_of_an_import_is_byte_equal_to_the_native_reply() {
    assert_eq!(
        serde_json::to_string(&import()).expect("JSON"),
        WIRE.to_owned()
    );
    let back: Record<ImportFact> = serde_json::from_str(WIRE).expect("an import record");
    assert_eq!(back, import());
}

#[test]
fn the_read_set_holds_only_the_read_fields() {
    let read: Value =
        serde_json::from_slice(&readset::to_vec(&import()).expect("JSON")).expect("JSON");
    let keys: Vec<&str> = read
        .as_object()
        .expect("an object")
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        ["id", "kind", "area", "subjects", "evidence_ids", "data"]
    );
    let data = read["data"].as_object().expect("an object");
    for unread in ["specifier", "type_only"] {
        assert!(!data.contains_key(unread), "{unread} is not read by a rule");
    }
    // AD-346: `interface_boundary` reads it (`check/evaluation/rules.py`); WP1 traced no demo of it.
    assert_eq!(data["symbols_known"], Value::Bool(false));
    assert_eq!(data["symbol"], Value::Null);
    assert_eq!(data["source_module"], "app.a_x2e_ts");
    assert!(!data.contains_key("origin_definition"));
}

fn with(key: &str, value: Value) -> String {
    let mut record: Value = serde_json::from_str(WIRE).expect("JSON");
    record[key] = value;
    record.to_string()
}

#[test]
fn a_record_outside_the_protocol_is_a_decode_error() {
    let cases = [
        with("kind", "symbol".into()),
        with("area", "Source".into()),
        with("rule_ids", serde_json::json!(["RULE-1"])),
        with("provenance", serde_json::json!(["x"])),
        with("extra", true.into()),
        with("data", serde_json::json!({"source_module": "a"})),
        WIRE.replace("\"relative_level\":0", "\"relative_level\":0,\"line\":1"),
        // A field that the wire always writes, also as `null`, must be present.
        WIRE.replace("\"symbol\":null,", ""),
    ];
    for case in cases {
        assert!(
            serde_json::from_str::<Record<ImportFact>>(&case).is_err(),
            "decoded: {case}"
        );
    }
}

#[test]
fn a_kind_of_another_section_is_a_decode_error() {
    let section = format!(r#"{{"name":"calls","records":[{WIRE}]}}"#);
    assert!(serde_json::from_str::<Section>(&section).is_err());
    let section = format!(r#"{{"name":"imports","records":[{WIRE}]}}"#);
    assert!(serde_json::from_str::<Section>(&section).is_ok());
}

#[test]
fn a_null_and_an_absent_field_stay_different() {
    let mut data = ImportData::statement();
    data.script_member = Nullable::Null;
    let text = serde_json::to_string(&data).expect("JSON");
    assert!(text.contains("\"script_member\":null"));
    data.script_member = Nullable::Absent;
    let text = serde_json::to_string(&data).expect("JSON");
    assert!(!text.contains("script_member"));
}
