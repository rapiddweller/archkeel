// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use serde_json::json;

use crate::validate::tests::{compressed, golden};

#[test]
fn new_construct_variants_keep_the_existing_owner_and_evidence_checks() -> Result<(), String> {
    for kind in ["assert_statement", "placeholder_body", "dunder_dict"] {
        let mut reply = golden("h-typescript");
        let module = reply["facts"]["files"][0]["module"].clone();
        let evidence = reply["facts"]["files"][0]["evidence_id"].clone();
        // Use the registered capability to isolate the shared validation from the profile refusal.
        let mut data = json!({"construct": "string_literal_compare", "owner": module});
        if kind == "placeholder_body" {
            data["form"] = json!("empty");
        }
        let record = json!({"id": "CONSTRUCT-new", "evidence_class": "FACT", "area": "constructs",
            "kind": kind, "title": "new", "subjects": [], "evidence_ids": [evidence],
            "fact_ids": [], "rule_ids": [], "provenance": [], "data": data});
        let section = reply["facts"]["sections"]
            .as_array_mut()
            .ok_or("no sections")?
            .iter_mut()
            .find(|s| s["name"] == "constructs")
            .ok_or("no constructs")?;
        section["records"] = json!([record]);
        crate::ingest_reply(&compressed(&reply), 1 << 30)?;
        for (field, value, expected) in [
            (
                "owner",
                json!("outside.f"),
                "source record owner disagrees with its module",
            ),
            (
                "evidence_ids",
                json!(["EVD-missing"]),
                "dangling source evidence reference",
            ),
        ] {
            let mut changed = reply.clone();
            let section = changed["facts"]["sections"]
                .as_array_mut()
                .ok_or("no sections")?
                .iter_mut()
                .find(|s| s["name"] == "constructs")
                .ok_or("no constructs")?;
            if field == "owner" {
                section["records"][0]["data"][field] = value;
            } else {
                section["records"][0][field] = value;
            }
            let error = crate::ingest_reply(&compressed(&changed), 1 << 30)
                .err()
                .ok_or("invalid record accepted")?;
            assert_eq!(error, expected, "{kind}/{field}");
        }
    }
    Ok(())
}
