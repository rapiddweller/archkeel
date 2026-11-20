// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The optional Explorer records retain the collector identity and evidence.

use super::*;

#[test]
fn explorer_projects_the_same_scan_without_changing_its_ruling() {
    let root = repository("explorer-facts");
    fs::write(
        root.join("src/invoice.ts"),
        "export class Invoice { amount: number = 3; static total(): number { return 3; } }",
    )
    .unwrap();
    let mut request = request(&root);
    let (expected, expected_gap) = frame(&request);
    assert!(expected.get("explorer").is_none());
    request["explorer"] = json!(true);
    let (mut detailed, actual_gap) = frame(&request);
    let parts = detailed
        .as_object_mut()
        .unwrap()
        .remove("explorer")
        .unwrap();
    assert_eq!((detailed.clone(), actual_gap), (expected, expected_gap));
    let part = &parts[0];
    assert_eq!(part["language"], "typescript");
    assert!(part["part"].is_null());
    let imports = part["imports"].as_array().unwrap();
    assert!(imports.iter().any(|row| row["resolution"] == "local"));
    for row in imports {
        for id in row["evidence_ids"].as_array().unwrap() {
            assert!(detailed["locations"][id.as_str().unwrap()]["path"].is_string());
        }
    }
    let symbols = part["symbols"].as_array().unwrap();
    let invoice = symbols
        .iter()
        .find(|row| {
            row["qualified_name"]
                .as_str()
                .is_some_and(|n| n.ends_with(".Invoice"))
        })
        .unwrap();
    let method = symbols
        .iter()
        .find(|row| row["lexical_parent_id"] == invoice["id"])
        .unwrap();
    assert_eq!(method["method_kind"], "static");
    let attr = &invoice["attributes"][0];
    assert_eq!(attr["name"], "amount");
    assert!(detailed["locations"][attr["evidence_ids"][0].as_str().unwrap()]["path"].is_string());
    assert!(invoice["member_inventories"]
        .as_array()
        .unwrap()
        .iter()
        .any(|i| i["kind"] == "attribute"
            && i["status"] == "complete"
            && i.get("reason") == Some(&Value::Null)
            && i["definition_ids"][0] == attr["definition_id"]));
    assert!(!part["files"].as_array().unwrap().is_empty());
}
