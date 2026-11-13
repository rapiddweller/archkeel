// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_model::{Model, Verdict};
use serde_json::{json, Value};

use crate::tests::{contract, reply_or_refusal, shop_settings};

const OWNER: &str = "shop.src.data.local_x2e_ts";

fn run(options: Value, records: bool, support: &str, gap: bool) -> Result<crate::Outcome, String> {
    let mut bytes = Vec::new();
    let parsed = contract(|c| {
        c["schema_version"] = json!("3.14.0");
        c["declarations"] = json!({});
        c["rules"] = json!([{"id": "CONSTRUCT", "kind": "forbidden_construct", "source": "shop",
            "constructs": ["string_literal_compare"], "rationale": "r", "provenance": ["p"], "decided_by": "architect"}]);
        if let Some(options) = options.as_object() {
            for (key, value) in options {
                c["rules"][0][key] = value.clone();
            }
        }
        bytes = c.to_string().into_bytes();
    });
    let contract = match parsed {
        Some(c) => c,
        None => {
            return Err(format!(
                "contract refused: {:?}",
                archkeel_contract::parse(&bytes)
            ))
        }
    };
    let reply = reply_or_refusal(|v| {
        assert_eq!(support, "partial");
        let evidence = v["facts"]["files"][0]["evidence_id"].clone();
        let record = json!({"id": "CONSTRUCT-site", "evidence_class": "FACT", "area": "constructs",
            "kind": "string_literal_compare", "title": "original", "subjects": [OWNER],
            "evidence_ids": [evidence], "fact_ids": [], "rule_ids": [], "provenance": [],
            "data": {"owner": OWNER, "construct": "string_literal_compare"}});
        let mut duplicate = record.clone();
        duplicate["id"] = json!("CONSTRUCT-neighbor");
        let records = if records {
            json!([record, duplicate])
        } else {
            json!([])
        };
        for section in v["facts"]["sections"].as_array_mut().into_iter().flatten() {
            if section["name"] == "constructs" {
                section["records"] = records.clone();
            }
        }
        if gap {
            let gap = json!({"id": "UNKNOWN-gap", "evidence_class": "UNKNOWN", "area": "source",
                "kind": "collection_gap", "title": "unread file", "subjects": [OWNER],
                "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
                "data": {"reason": "unread file", "module": OWNER}});
            v["facts"]["coverage"]["gaps"] = json!([gap.clone()]);
            v["facts"]["coverage"]["full_scope"] = json!(false);
            v["facts"]["sections"][1]["records"] = json!([gap]);
        }
    })?;
    let model = Model::derive(&contract, &reply, shop_settings()).map_err(|r| r.to_string())?;
    crate::evaluate(&model)
        .into_iter()
        .next()
        .ok_or("no outcome".to_owned())
}

#[test]
fn construct_absence_needs_the_receipt_and_a_complete_scope() -> Result<(), String> {
    let pass = run(json!({}), false, "partial", false)?;
    assert!(
        matches!(pass.decision().map(|d| d.verdict()), Some(Verdict::Unknown)),
        "{pass:?}"
    );
    let gap = run(json!({}), false, "partial", true)?;
    assert!(
        matches!(gap.decision().map(|d| d.verdict()), Some(Verdict::Unknown)),
        "{gap:?}"
    );
    let empty = run(json!({"source": "missing"}), false, "partial", false)?;
    assert!(
        matches!(
            empty.decision().map(|d| d.verdict()),
            Some(Verdict::Unknown)
        ),
        "{empty:?}"
    );
    Ok(())
}

#[test]
fn construct_fail_comes_before_a_gap_and_exemptions_do_not_drop_neighbors() -> Result<(), String> {
    for gap in [false, true] {
        let fail = run(json!({}), true, "partial", gap)?;
        assert!(
            matches!(fail.decision().map(|d| d.verdict()), Some(Verdict::Fail)),
            "{fail:?}"
        );
        assert_eq!(fail.violations().len(), 1);
        let Some(crate::Violation::Construct(row)) = fail.violations().first() else {
            return Err("no construct row".to_owned());
        };
        let expected = archkeel_facts::identity::stable_id(
            "VIO",
            &[
                archkeel_facts::identity::Part::Text("CONSTRUCT"),
                archkeel_facts::identity::Part::Text("CONSTRUCT-site"),
            ],
        );
        assert_eq!(row.id, expected);
        assert_eq!(row.facts, ["CONSTRUCT-neighbor", "CONSTRUCT-site"]);
        assert_eq!(row.evidence.len(), 1);
    }
    for key in ["allowed_sources", "exact_sources"] {
        let pass = run(json!({key: [OWNER]}), true, "partial", false)?;
        assert!(
            matches!(pass.decision().map(|d| d.verdict()), Some(Verdict::Unknown)),
            "{pass:?}"
        );
        let fail = run(
            json!({key: [format!("{OWNER}.neighbor")]}),
            true,
            "partial",
            false,
        )?;
        assert!(
            matches!(fail.decision().map(|d| d.verdict()), Some(Verdict::Fail)),
            "{fail:?}"
        );
        let unknown = run(json!({key: [OWNER]}), true, "partial", true)?;
        assert!(
            matches!(
                unknown.decision().map(|d| d.verdict()),
                Some(Verdict::Unknown)
            ),
            "{unknown:?}"
        );
    }
    Ok(())
}

#[test]
fn a_partial_or_unsupported_inventory_never_proves_absence() -> Result<(), String> {
    for constructs in [json!(["string_literal_compare"]), json!(["eval"])] {
        let result = run(json!({"constructs": constructs}), false, "partial", false)?;
        assert!(
            matches!(
                result.decision().map(|d| d.verdict()),
                Some(Verdict::Unknown)
            ),
            "{result:?}"
        );
        assert!(result.decision().and_then(|d| d.reason()).is_some());
    }
    Ok(())
}
