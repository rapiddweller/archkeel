// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Each `Fields` value of each record of the frozen replies equals the value of the same key in
//! the wire JSON of the record. A field that no `project!` list reads fails here.

use std::io::Write;

use archkeel_facts::fields::Fields;
use archkeel_facts::vocab::Status;
use archkeel_facts::{FactData, Record, Section};
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::Value;

use crate::decode;
use crate::stored::{visit, Visitor};
use crate::validate::tests::golden;

/// The golden replies have no `property_members`: give the first class one, as a changed reply.
fn with_property_members(mut reply: Value) -> Value {
    let sections = reply["facts"]["sections"].as_array_mut();
    let records = sections
        .into_iter()
        .flatten()
        .filter_map(|s| s["records"].as_array_mut());
    if let Some(class) = records.flatten().find(|record| record["kind"] == "class") {
        class["data"]["property_members"] = serde_json::json!(["x"]);
    }
    reply
}

#[derive(Default)]
struct Compare {
    records: usize,
}

fn lengths<T>(items: Option<&[T]>) -> Option<usize> {
    items.map(<[T]>::len)
}

fn first_difference(checks: &[(&'static str, bool)]) -> Result<(), String> {
    match checks.iter().find(|(_, equal)| !equal) {
        Some((name, _)) => Err(format!("the field {name} differs from the wire")),
        None => Ok(()),
    }
}

fn texts(fields: &Fields<'_>, data: &Value) -> Result<(), String> {
    let text = |key: &str| data.get(key).and_then(Value::as_str);
    let named = |key: &str| data.get(key).map(Value::as_str);
    let targets = data.get("targets").and_then(Value::as_array).map(|items| {
        let names: Vec<_> = items.iter().filter_map(Value::as_str).collect();
        names
    });
    first_difference(&[
        (
            "source_module",
            fields.source_module == named("source_module"),
        ),
        ("module", fields.module == named("module")),
        ("owner", fields.owner == text("owner")),
        ("source_scope", fields.source_scope == text("source_scope")),
        (
            "qualified_name",
            fields.qualified_name == text("qualified_name"),
        ),
        (
            "declaration_scope",
            fields.declaration_scope == text("declaration_scope"),
        ),
        (
            "source_package",
            fields.source_package == text("source_package"),
        ),
        (
            "target_module",
            fields.target_module == text("target_module"),
        ),
        (
            "target_package",
            fields.target_package == text("target_package"),
        ),
        ("construct", fields.construct == text("construct")),
        ("source_file", fields.source_file == text("source_file")),
        ("expression", fields.expression == text("expression")),
        (
            "status",
            fields.status == text("status").and_then(Status::parse),
        ),
        (
            "targets",
            fields
                .targets
                .map(|items| items.iter().map(String::as_str).collect())
                == targets,
        ),
        (
            "resolution_dimension",
            fields.resolution_dimension == text("resolution_dimension"),
        ),
        ("file", fields.file == text("file")),
        (
            "lexical_parent_id",
            fields.lexical_parent_id == text("lexical_parent_id"),
        ),
    ])
}

fn nested(fields: &Fields<'_>, data: &Value) -> Result<(), String> {
    let set = |key: &str| data.get(key).is_some_and(|value| !value.is_null());
    let count = |key: &str| data.get(key).and_then(Value::as_array).map(Vec::len);
    first_difference(&[
        (
            "base_declarations",
            lengths(fields.base_declarations) == count("base_declarations"),
        ),
        (
            "member_inventories",
            lengths(fields.member_inventories) == count("member_inventories"),
        ),
        (
            "attribute_declarations",
            lengths(fields.attribute_declarations) == count("attribute_declarations"),
        ),
        ("call_binding", fields.call_binding == set("call_binding")),
        (
            "call_arguments",
            fields.call_arguments == set("call_arguments"),
        ),
        (
            "guarded_effect",
            fields.guarded_effect == set("guarded_effect"),
        ),
        (
            "contextmanager_signature",
            fields.contextmanager_signature == set("contextmanager_signature"),
        ),
        (
            "guard_boolean_members",
            fields.guard_boolean_members == set("guard_boolean_members"),
        ),
        (
            "property_members",
            fields.property_members == set("property_members"),
        ),
        (
            "local_source_binding",
            fields.local_source_binding == set("local_source_binding"),
        ),
        (
            "declaration_definition_id",
            fields.declaration_definition_id == set("declaration_definition_id"),
        ),
        (
            "instance_member_scope_evidence_id",
            fields.instance_member_scope_evidence_id == set("instance_member_scope_evidence_id"),
        ),
        (
            "receiver_binding",
            fields.receiver_binding == set("receiver_binding"),
        ),
    ])
}

fn same(fields: &Fields<'_>, data: &Value) -> Result<(), String> {
    texts(fields, data).and_then(|()| nested(fields, data))
}

impl Visitor for Compare {
    fn record<D: FactData>(&mut self, _: &Section, record: &Record<D>) -> Result<(), String> {
        let wire = serde_json::to_value(record).map_err(|error| error.to_string())?;
        same(&record.data.fields(), &wire["data"])?;
        self.records += 1;
        Ok(())
    }
}

#[test]
fn each_field_of_each_golden_record_equals_the_wire_value_of_its_key() {
    let mut total = 0;
    for case in [
        "h-typescript",
        "h-uml-typescript",
        "f-typescript-story",
        "excalidraw-laser-pointer",
    ] {
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
        encoder
            .write_all(with_property_members(golden(case)).to_string().as_bytes())
            .unwrap();
        let payload = encoder.finish().unwrap();
        let reply = decode::reply(&payload, 1 << 30).unwrap();
        let mut compare = Compare::default();
        for section in &reply.facts.sections {
            let result = visit(section, 0, section.len(), &mut compare);
            assert_eq!(result, Ok(()), "{case}");
        }
        assert!(compare.records > 0, "{case}: no record");
        total += compare.records;
    }
    assert!(total > 100, "{total} records");
}
