// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the explanation of a system run keeps the budget of one part for the gaps that hold a
// rule, because the shell refuses a longer list (found on a system of three parts).

use serde_json::{json, Map, Value};

use super::explain;

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
