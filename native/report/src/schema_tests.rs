// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The types of this crate follow `schema/report-2.0.schema.json`: each code list equals its
//! `x-codes`, and each object writes its keys in the order of its `required` list.

use std::path::PathBuf;

use serde_json::Value;

use crate::codes::{
    CodeList, Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, Measure, MeasureState,
    Permission, Reason, Relation, UnknownReason, UnknownSource, Verdict, Vis,
};
use crate::corpus_tests::bytes;

fn schema() -> Value {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../schema/report-2.0.schema.json");
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

fn texts<L: CodeList>() -> (&'static str, Vec<String>) {
    (L::NAME, L::TEXTS.iter().map(|t| (*t).to_owned()).collect())
}

#[test]
fn each_code_list_equals_its_x_codes() {
    let schema = schema();
    let lists = [
        texts::<Level>(),
        texts::<Kind>(),
        texts::<Vis>(),
        texts::<MeasureState>(),
        texts::<Verdict>(),
        texts::<EdgeTarget>(),
        texts::<FindingKind>(),
        texts::<Disposition>(),
        texts::<Reason>(),
        texts::<Measure>(),
        texts::<Gap>(),
        texts::<Relation>(),
        texts::<Permission>(),
        texts::<UnknownSource>(),
        texts::<UnknownReason>(),
    ];
    let defs = schema["$defs"].as_object().unwrap();
    let in_schema = defs.values().filter(|d| d.get("x-codes").is_some()).count();
    assert_eq!(lists.len(), in_schema);
    for (name, values) in lists {
        let wanted: Vec<String> = serde_json::from_value(defs[name]["x-codes"].clone()).unwrap();
        assert_eq!(values, wanted, "{name}");
    }
}

fn required(node: &Value) -> Vec<String> {
    serde_json::from_value(node["required"].clone()).unwrap()
}

fn keys(value: &Value) -> Vec<String> {
    value.as_object().unwrap().keys().cloned().collect()
}

#[test]
fn each_object_writes_its_keys_in_the_order_of_required() {
    let schema = schema();
    let defs = &schema["$defs"];
    let props = &schema["properties"];
    let payload: Value =
        serde_json::from_slice(&bytes("variant-forbidden-dependency-pair")).unwrap();
    assert_eq!(keys(&payload), required(&schema));
    assert_eq!(keys(&payload["run"]), required(&defs["Run"]));
    assert_eq!(
        keys(&payload["run"]["source"]),
        required(&defs["Run"]["properties"]["source"])
    );
    assert_eq!(keys(&payload["summary"]), required(&defs["Summary"]));
    let counts = &defs["Summary"]["properties"]["counts"];
    assert_eq!(keys(&payload["summary"]["counts"]), required(counts));
    assert_eq!(keys(&payload["rules"][0]), required(&defs["RuleResult"]));
    assert_eq!(keys(&payload["gaps"][0]), required(&defs["GapRow"]));
    assert_eq!(
        keys(&payload["components"][0]),
        required(&defs["Component"])
    );
    let tables = [
        "nodes",
        "measures",
        "units",
        "variants",
        "edges",
        "crossings",
        "permissions",
    ];
    let more = ["violations", "unknowns", "findings", "carriers"];
    for table in tables.into_iter().chain(more) {
        assert_eq!(keys(&payload[table]), required(&props[table]), "{table}");
    }
    let full = crate::Payload {
        fields: Some(crate::Fields::default()),
        params: Some(crate::Params::default()),
        ..crate::Payload::decode(&bytes("E-runtime")).unwrap()
    };
    let written: Value = serde_json::from_slice(&full.encode().unwrap()).unwrap();
    let mut wanted = required(&schema);
    wanted.extend(["fields".to_owned(), "params".to_owned()]);
    assert_eq!(keys(&written), wanted);
    assert_eq!(keys(&written["fields"]), required(&props["fields"]));
    assert_eq!(keys(&written["params"]), required(&props["params"]));
}
