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

// AD-630, AD-794: no level of the Explorer holds more boxes than one screen shows when its names
// share a prefix; a larger set is split into groups that the user opens, and a gap inside a group
// shows on it.
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
                kids.len() <= super::super::atlas_node::ON_SCREEN,
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
        // A group names the prefix that its members share, so its title stays short.
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

// AD-794: names that share no prefix are never cut into ranges of sorted names: the level is shown
// whole, and no group names a range.
#[test]
fn a_level_whose_names_share_no_prefix_is_shown_whole() {
    let data = payload(&document(
        &json!({"status": "PASS", "topology": components(40, &[(0, 1)])}),
    ));
    let all = data["atlas"]["components"].as_array().unwrap();
    assert_eq!(all.len(), 40);
    assert!(all
        .iter()
        .all(|c| c["parent_id"].is_null() && !c["label"].as_str().unwrap().contains(" to ")));
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
        // A gap inside one component holds that component only. The run is UNKNOWN, so the other
        // components show no PASS either; their reason says that no gap of their own holds them
        // (AD-730).
        frame["collection_gaps"][0]["subjects"] = json!(["m1"]);
        let data = payload(&document(&frame));
        let found = statuses(&data);
        assert_eq!(found[0].1, "UNKNOWN", "{found:?}");
        assert_eq!(found[1].1, "UNKNOWN", "{found:?}");
        let reason = |i: usize| {
            let at = data["atlas"]["components"][i]["reason_ref"]
                .as_u64()
                .unwrap() as usize;
            data["atlas"]["reference_ids"][at]
                .as_str()
                .unwrap()
                .to_owned()
        };
        assert!(reason(0).contains("no gap inside, but the run is not decided"));
        assert!(reason(1).contains("1 gaps name a module inside"));
    }
}

// AD-710: the sheet of a layer aggregates its members; it says that the box groups N components,
// and fills no field that no member fills.
#[test]
fn a_layer_sheet_aggregates_its_member_components() {
    let comp = |id: &str, layer: &str, about: &str, public: &[&str], forbidden: &[&str]| {
        json!({"id": id, "name": id, "parent": null, "layer": layer, "responsibilities": [about],
            "public": public, "forbidden_responsibilities": forbidden})
    };
    let frame = json!({"status": "PASS", "topology": {
        "components": [
            comp("A", "L1", "Reads the files. It also hashes.", &["a:read", "a:hash"], &["Parsing"]),
            comp("B", "L1", "Keeps the replies.", &["b:keep"], &["Parsing", "Output"]),
            comp("C", "L2", "TODO", &[], &[])],
        "modules": [], "layers": [{"rule": "R", "layers": ["L1", "L2"]}]}});
    let data = payload(&document(&frame));
    let by_id = |id: &str| {
        data["atlas"]["components"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["id"] == id)
            .unwrap()
            .clone()
    };
    let layer = by_id("LAYER:L1");
    let said: Vec<&str> = layer["responsibilities"]
        .as_array()
        .unwrap()
        .iter()
        .map(|t| t.as_str().unwrap())
        .collect();
    assert_eq!(
        said[0],
        "This box groups 2 components of layer L1 (layer 1 of 2)."
    );
    assert_eq!(said[1..], ["A: Reads the files", "B: Keeps the replies"]);
    assert_eq!(
        layer["not_responsible_for"].as_array().unwrap().len(),
        2,
        "the union, once each"
    );
    assert_eq!(layer["public"].as_array().unwrap().len(), 3);
    // A layer that holds one component is that component: it shows that component's own text.
    let single = by_id("LAYER:L2");
    assert_eq!(
        single["responsibilities"],
        json!(["Responsibility not written yet."])
    );
    assert_eq!(single["not_responsible_for"].as_array().unwrap().len(), 0);
}

// AD-710: each rule says what it finds in plain words, for one finding and for many.
#[test]
fn a_rule_has_plain_words_for_its_findings() {
    let frame = json!({"status": "FAIL", "topology": components(2, &[]),
        "rules": {"NATIVE-PUBLIC-HAS-A-USER": ["unused_public", "FAIL"], "X": ["other_kind", "PASS"]}});
    let data = payload(&document(&frame));
    let rules = data["atlas"]["rule_assessments"].as_array().unwrap();
    let rule = rules
        .iter()
        .find(|r| r["plain_many"].as_str().unwrap().starts_with("public"))
        .unwrap();
    assert_eq!(rule["plain_one"], "public name without a user");
    assert_eq!(rule["plain_many"], "public names without a user");
    let other = rules
        .iter()
        .find(|r| r["plain_one"].as_str().unwrap().contains("other kind"))
        .unwrap();
    assert_eq!(other["plain_many"], "findings of other kind");
}

// #1441: a component that is also a layer shows its own contract facts; the box of a layer that
// holds one component is that component, and the sheet says `Component`.
#[test]
fn a_layer_that_holds_one_component_shows_the_facts_of_that_component() {
    let frame = json!({"status": "PASS", "topology": {
        "components": [{"id": "F", "name": "frame", "parent": null, "layer": "frame",
            "responsibilities": ["Read one frame."], "forbidden_responsibilities": ["Print."],
            "public": ["f:read"], "provenance": ["docs/shell.md"]}],
        "modules": [], "layers": [{"rule": "R", "layers": ["frame"]}]}});
    let data = payload(&document(&frame));
    let layer = data["atlas"]["components"]
        .as_array()
        .unwrap()
        .iter()
        .find(|c| c["id"] == "LAYER:frame")
        .unwrap()
        .clone();
    assert_eq!(layer["responsibilities"], json!(["Read one frame."]));
    assert_eq!(layer["not_responsible_for"], json!(["Print."]));
    assert_eq!(layer["public"].as_array().unwrap().len(), 1);
    // Texts are by index in the payload, as the names of the public surface are.
    assert_eq!(layer["provenance"].as_array().unwrap().len(), 1);
    assert!(layer["provenance"][0].is_u64());
    assert_eq!(layer["groups"], json!(1));
}
