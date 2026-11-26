// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the explanation of a system run keeps the budget of one part for the gaps that hold a
// rule, because the shell refuses a longer list (found on a system of three parts).

use serde_json::{json, Map, Value};

use archkeel_collect::SystemPart;

use super::{explain, topology};

fn frame(gaps: &[&str]) -> Map<String, Value> {
    let found = json!({"explain": {
        "budgets": {"gaps": 2},
        "rules": {}, "cycles": {},
        "holds": {
            "rules": {},
            "gaps": gaps.iter().map(|g| json!({"id": g})).collect::<Vec<_>>(),
            "gaps_total": gaps.len(),
            "gaps_holding": gaps.len(),
            "gaps_truncated": false,
        },
    }});
    found.as_object().cloned().unwrap_or_default()
}

#[test]
fn the_joined_gap_list_keeps_the_budget_and_states_the_cut() {
    let joined = explain(&[frame(&["a", "b"]), frame(&["c", "d"])]).unwrap_or_default();
    let holds = &joined["holds"];
    assert_eq!(holds["gaps"].as_array().map(Vec::len), Some(2));
    assert_eq!(holds["gaps_holding"], 4);
    assert_eq!(holds["gaps_truncated"], true);
}

#[test]
fn a_joined_list_within_the_budget_is_not_cut() {
    let joined = explain(&[frame(&["a"]), frame(&[])]).unwrap_or_default();
    assert_eq!(joined["holds"]["gaps"].as_array().map(Vec::len), Some(1));
    assert_eq!(joined["holds"]["gaps_truncated"], false);
}

fn part(id: &str) -> SystemPart {
    SystemPart {
        id: id.to_owned(),
        title: id.to_owned(),
        config: format!("{id}.toml"),
        responsibilities: Vec::new(),
        forbidden_responsibilities: Vec::new(),
        provides: Vec::new(),
    }
}

fn edge(source: &str, target: &str, resolution: &str, count: u64, line: u64, file: &str) -> Value {
    json!({"id": format!("EDGE-{source}-{target}-{resolution}"), "source": source,
        "target": target, "resolution": resolution, "count": count,
        "evidence": [{"path": file, "line": line}], "evidence_total": 1, "rules": []})
}

fn part_frame(module: &str, edges: &[Value]) -> Map<String, Value> {
    let found = json!({"topology": {
        "version": 1, "complete": true, "truncated": false, "gaps": [], "budgets": {},
        "total": {"components": 1, "modules": 1, "edges": 0, "component_edges": edges.len()},
        "components": [{"id": format!("COMP-{module}"), "name": module, "parent": null}],
        "modules": [{"name": module}], "edges": [], "component_edges": edges,
        "requires": [], "layers": [],
    }});
    found.as_object().cloned().unwrap_or_default()
}

#[test]
fn a_label_edge_of_two_parts_is_one_row_with_the_sum_of_both() {
    let (a, b) = (part("a"), part("b"));
    let first = part_frame(
        "a",
        &[edge("unowned", "external", "external", 3, 1, "a.py")],
    );
    let second = part_frame(
        "b",
        &[edge("unowned", "external", "external", 4, 2, "b.py")],
    );
    let joined = topology(&[(&a, &first), (&b, &second)], None)
        .unwrap()
        .unwrap();
    let rows = joined["component_edges"].as_array().unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["count"], 7);
    assert_eq!(rows[0]["evidence_total"], 2);
    assert_eq!(rows[0]["evidence"].as_array().map(Vec::len), Some(2));
    assert_eq!(joined["total"]["component_edges"], 1);
}

#[test]
fn two_parts_that_name_one_module_stay_refused() {
    let (a, b) = (part("a"), part("b"));
    let first = part_frame("m", &[]);
    let mut second = part_frame("m", &[]);
    second["topology"]["components"][0]["id"] = json!("COMP-other");
    assert!(topology(&[(&a, &first), (&b, &second)], None).is_err());
}

#[test]
fn a_merged_edge_over_the_evidence_budget_is_truncated_and_not_complete() {
    let (a, b) = (part("a"), part("b"));
    let many = |file: &str| {
        let mut row = edge("unowned", "external", "external", 3, 1, file);
        row["evidence"] = json!((1..=3)
            .map(|line| json!({"path": file, "line": line}))
            .collect::<Vec<_>>());
        row["evidence_total"] = json!(3);
        row
    };
    let first = part_frame("a", &[many("a.py")]);
    let second = part_frame("b", &[many("b.py")]);
    let joined = topology(&[(&a, &first), (&b, &second)], None)
        .unwrap()
        .unwrap();
    assert_eq!(
        joined["component_edges"][0]["evidence"]
            .as_array()
            .map(Vec::len),
        Some(5)
    );
    assert_eq!(joined["component_edges"][0]["evidence_total"], 6);
    assert_eq!(
        (joined["truncated"].clone(), joined["complete"].clone()),
        (json!(true), json!(false))
    );
}

#[test]
fn a_location_that_two_parts_share_counts_once() {
    let (a, b) = (part("a"), part("b"));
    let first = part_frame(
        "a",
        &[edge("unowned", "external", "external", 1, 7, "x.py")],
    );
    let second = part_frame(
        "b",
        &[edge("unowned", "external", "external", 1, 7, "x.py")],
    );
    let joined = topology(&[(&a, &first), (&b, &second)], None)
        .unwrap()
        .unwrap();
    let row = &joined["component_edges"][0];
    assert_eq!(row["count"], 2);
    assert_eq!(row["evidence"].as_array().map(Vec::len), Some(1));
    assert_eq!(row["evidence_total"], 1);
}
