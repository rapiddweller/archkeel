// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_contract::{ParsedContract, Rule};
use archkeel_eval::ConstructViolation;
use serde_json::Value;

fn strings(value: &Value) -> Result<Vec<String>, String> {
    value
        .as_array()
        .ok_or("no string array")?
        .iter()
        .map(|s| {
            s.as_str()
                .map(str::to_owned)
                .ok_or("not a string".to_owned())
        })
        .collect()
}

#[test]
#[ignore = "the Python test supplies the frozen facts and reference rows"]
fn replay_frozen_construct_rows() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::var("ARCHKEEL_CONSTRUCT_REPLAY")?;
    let cases: Vec<Value> = serde_json::from_slice(&std::fs::read(path)?)?;
    let mut count = 0;
    for case in cases {
        let contract = match archkeel_contract::parse(case["contract"].to_string().as_bytes())? {
            ParsedContract::Complete(c) => c,
            _ => return Err("partial replay contract".into()),
        };
        let rule = contract.rules().first().ok_or("no replay rule")?;
        let Rule::ForbiddenConstruct(rule) = rule else {
            return Err("wrong rule".into());
        };
        for expected in case["expected"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|r| r["evidence_class"] == "VIOLATION")
        {
            let row = row(rule, expected)?;
            assert_eq!(
                serde_json::to_vec(&crate::construct_row(&row))?,
                serde_json::to_vec(expected)?,
                "{}",
                case["name"]
            );
            count += 1;
        }
    }
    assert!(count >= 16);
    println!("frozen construct rows: {count} byte-equal to Python");
    Ok(())
}

fn row(
    rule: &archkeel_contract::ForbiddenConstruct,
    expected: &Value,
) -> Result<ConstructViolation, String> {
    let text = |key: &str| {
        expected[key]
            .as_str()
            .map(str::to_owned)
            .ok_or(format!("missing {key}"))
    };
    Ok(ConstructViolation {
        id: text("id")?,
        rule: rule.head().id().as_text().to_owned(),
        source: rule.source().as_text().to_owned(),
        owner: expected["subjects"][0]
            .as_str()
            .ok_or("no owner")?
            .to_owned(),
        construct: expected["data"]["construct"]
            .as_str()
            .unwrap_or_default()
            .to_owned(),
        facts: strings(&expected["fact_ids"])?,
        evidence: strings(&expected["evidence_ids"])?,
        provenance: if rule.selector().is_some() {
            rule.head().provenance().to_vec()
        } else {
            vec![]
        },
        selector: rule.selector().clone(),
    })
}
