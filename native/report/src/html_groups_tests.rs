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
    for size in [12, 13, 80, 226] {
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
                kids.len() <= 12,
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

/// The status of each component of the Explorer data, by its id.
fn statuses(data: &Value) -> Vec<(String, String)> {
    data["atlas"]["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            (
                c["id"].as_str().unwrap().to_owned(),
                c["status"].as_str().unwrap().to_owned(),
            )
        })
        .collect()
}

// AD-606: a gap that no component owns may hold any component, so none shows PASS beside it.
#[test]
fn a_gap_that_names_no_owned_module_holds_every_component() {
    for subjects in [json!([]), json!(["outside.module"])] {
        let mut frame = json!({"status": "UNKNOWN", "topology": components(3, &[(0, 1)]),
            "collection_gaps": [{"kind": "collection_gap", "subjects": subjects, "reason": "macro"}]});
        let found = statuses(&payload(&document(&frame)));
        assert_eq!(found.len(), 3);
        assert!(
            found.iter().all(|(_, status)| status == "UNKNOWN"),
            "{found:?}"
        );
        // A gap inside one component holds that component only.
        frame["collection_gaps"][0]["subjects"] = json!(["m1"]);
        let found = statuses(&payload(&document(&frame)));
        assert_eq!(found[0].1, "PASS", "{found:?}");
        assert_eq!(found[1].1, "UNKNOWN", "{found:?}");
    }
}
