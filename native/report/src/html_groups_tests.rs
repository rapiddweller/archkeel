// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The groups of the Explorer tree: no level holds more boxes than stay readable (AD-630).

use super::*;

/// The children of each scope of the Explorer data, by parent id (`None` for the top).
fn children_of(data: &Value) -> std::collections::BTreeMap<Option<String>, Vec<String>> {
    let mut found: std::collections::BTreeMap<Option<String>, Vec<String>> = Default::default();
    for c in data["atlas"]["components"].as_array().unwrap() {
        let parent = c["parent_id"].as_str().map(str::to_owned);
        found
            .entry(parent)
            .or_default()
            .push(c["id"].as_str().unwrap().to_owned());
    }
    found
}

// AD-630: no level of the Explorer holds more boxes than stay readable; a larger set is split into
// groups that the user opens, and a gap inside a group shows on it.
#[test]
fn no_level_of_the_explorer_holds_more_boxes_than_stay_readable() {
    for size in [6, 7, 80, 226] {
        let mut topology = components(size, &[(0, 1)]);
        for (i, c) in topology["components"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .enumerate()
        {
            c["name"] = json!(format!("svc{:02}_part{}", i / 10, i % 10));
        }
        let frame = json!({"status": "UNKNOWN", "topology": topology,
            "collection_gaps": [{"kind": "collection_gap", "subjects": ["m0"], "reason": "macro"}]});
        let data = payload(&document(&frame));
        for (parent, kids) in children_of(&data) {
            assert!(
                kids.len() <= 6,
                "{size}: {parent:?} holds {} boxes",
                kids.len()
            );
        }
        // One id names one box: a repeated id makes a loop in the tree.
        let ids: std::collections::BTreeSet<&str> = data["atlas"]["components"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| c["id"].as_str().unwrap())
            .collect();
        assert_eq!(
            ids.len(),
            data["atlas"]["components"].as_array().unwrap().len()
        );
        // A group names its first and last leaf, so its title stays short at any depth.
        for c in data["atlas"]["components"].as_array().unwrap() {
            assert!(
                c["label"].as_str().unwrap().len() <= 40,
                "{size}: {}",
                c["label"]
            );
        }
        // Every real component is still in the tree, and the gap shows on its group.
        let all = data["atlas"]["components"].as_array().unwrap();
        let real = all
            .iter()
            .filter(|c| !c["id"].as_str().unwrap().starts_with("GROUP:"))
            .count();
        assert_eq!(real, size);
        let top: Vec<&Value> = all.iter().filter(|c| c["parent_id"].is_null()).collect();
        assert!(
            top.iter().any(|c| c["status"] == "UNKNOWN"),
            "{size}: no box shows the gap"
        );
    }
}
