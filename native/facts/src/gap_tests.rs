// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the source collectors. The wire of a built gap is the wire that the collectors wrote
// with an untyped record before AD-345: the same keys, in the same order.

use serde_json::json;

use super::*;

fn gap(fact: GapFact, evidence: Option<&str>, module: &str) -> serde_json::Value {
    let record = Record::unknown(FactId::new("UNKNOWN-1"), "why", evidence, module, fact);
    serde_json::to_value(&record).unwrap()
}

#[test]
fn a_collection_gap_has_the_reason_and_the_module() {
    let fact = GapFact::collection("why", "ns.mod");
    assert_eq!(
        gap(fact, Some("EVD-1"), "ns.mod"),
        json!({
            "id": "UNKNOWN-1", "evidence_class": "UNKNOWN", "area": "source",
            "kind": "collection_gap", "title": "why", "subjects": ["ns.mod"],
            "evidence_ids": ["EVD-1"], "rule_ids": [], "fact_ids": [], "provenance": [],
            "data": {"reason": "why", "module": "ns.mod"},
        })
    );
}

#[test]
fn a_resolution_gap_names_the_dimension_and_an_empty_module_is_no_subject() {
    let fact = GapFact::resolution("why", "");
    let value = gap(fact, None, "");
    assert_eq!(value["kind"], "source_resolution_gap");
    assert_eq!(value["subjects"], json!([]));
    assert_eq!(value["evidence_ids"], json!([]));
    assert_eq!(
        value["data"],
        json!({"reason": "why", "module": "", "resolution_dimension": "imports"})
    );
}

#[test]
fn the_keys_of_the_data_keep_the_order_of_the_untyped_record() {
    let text = serde_json::to_string(&Record::unknown(
        FactId::new("U"),
        "why",
        None,
        "m",
        GapFact::resolution("why", "m"),
    ))
    .unwrap();
    assert!(
        text.ends_with(r#""data":{"reason":"why","module":"m","resolution_dimension":"imports"}}"#)
    );
}
