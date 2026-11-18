// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the frame of a system run keeps the premise of each part (AD-540, AD-616), so the
// shell accepts a system with a Python part.

use archkeel_collect::{System, SystemPart};
use serde_json::{json, Value};

use super::join;

fn system(ids: &[&str]) -> System {
    let parts = ids.iter().map(|id| SystemPart {
        id: (*id).to_owned(),
        title: (*id).to_owned(),
        config: format!("{id}.toml"),
        responsibilities: Vec::new(),
        forbidden_responsibilities: Vec::new(),
        provides: Vec::new(),
    });
    System {
        title: "Fixture".to_owned(),
        document: ("system.json".to_owned(), b"{}".to_vec()),
        parts: parts.collect(),
        interfaces: Vec::new(),
    }
}

fn part(status: &str, premise: Option<&str>) -> Vec<u8> {
    let mut frame = json!({"engine": "e", "protocol": "p", "status": status, "scope": "complete"});
    if let Some(text) = premise {
        frame["premise"] = json!(text);
    }
    serde_json::to_vec(&frame).unwrap()
}

fn joined(parts: &[Vec<u8>]) -> Value {
    let ids: Vec<String> = (0..parts.len()).map(|n| format!("p{n}")).collect();
    let ids: Vec<&str> = ids.iter().map(String::as_str).collect();
    serde_json::from_slice(&join(&system(&ids), parts, (false, false)).unwrap()).unwrap()
}

#[test]
fn the_system_frame_keeps_the_premise_of_each_part_once() {
    let shell = "Code outside the scan roots, including test code, hands in no module object of the scan and writes no binding of a module or class of the scan.";
    let frame = joined(&[part("PASS", Some(shell)), part("PASS", None)]);
    assert_eq!(frame["premise"], json!(shell));
    let frame = joined(&[part("PASS", Some(shell)), part("PASS", Some(shell))]);
    assert_eq!(frame["premise"], json!(shell));
    let frame = joined(&[part("PASS", Some("a.")), part("FAIL", Some("b"))]);
    assert_eq!(
        (frame["premise"].clone(), frame["status"].clone()),
        (json!("a; b"), json!("FAIL"))
    );
    assert_eq!(joined(&[part("PASS", None)]).get("premise"), None);
}

fn part_with_scope(status: &str, scope: &Value) -> Vec<u8> {
    let frame = json!({"engine": "e", "protocol": "p", "status": status, "scope": scope});
    serde_json::to_vec(&frame).unwrap()
}

#[test]
fn the_scope_of_the_system_is_complete_or_the_reason_of_the_first_open_part() {
    let all = joined(&[part("PASS", None), part("PASS", None)]);
    assert_eq!(all["scope"], json!("complete"));
    let open = |text: &str| part_with_scope("UNKNOWN", &json!(text));
    let first = joined(&[part("PASS", None), open("one"), open("two")]);
    assert_eq!(first["scope"], json!("one"));
    // A frame without a scope is complete; a scope that is no text is open and kept as it is.
    let bare = serde_json::to_vec(&json!({"engine": "e", "protocol": "p", "status": "PASS"}));
    assert_eq!(joined(&[bare.unwrap()])["scope"], json!("complete"));
    let odd = joined(&[part_with_scope("UNKNOWN", &json!(7))]);
    assert_eq!(odd["scope"], json!(7));
}

/// A part that is UNKNOWN for a rule: the frame states the rule row that explains it.
fn unknown_part(rule: &str, why: &str) -> Vec<u8> {
    let frame = json!({
        "engine": "e", "protocol": "p", "status": "UNKNOWN", "scope": "complete",
        "explained": {rule: why},
    });
    serde_json::to_vec(&frame).unwrap()
}

#[test]
fn an_unknown_system_never_says_that_its_scope_is_complete() {
    let why = "incomplete scope: the profile cannot decide R1";
    let frame = joined(&[part("PASS", None), unknown_part("R1", why)]);
    assert_eq!(frame["status"], json!("UNKNOWN"));
    assert_eq!(frame["scope"], json!(why));
    // A PASS system keeps the word complete.
    assert_eq!(joined(&[part("PASS", None)])["scope"], json!("complete"));
    // The scope of an open part still wins: it is the first reason.
    let open = part_with_scope("UNKNOWN", &json!("one"));
    assert_eq!(
        joined(&[open, unknown_part("R1", why)])["scope"],
        json!("one")
    );
}

#[test]
fn a_part_that_is_unknown_without_an_explaining_row_refuses_the_system() {
    let bare = serde_json::to_vec(&json!({
        "engine": "e", "protocol": "p", "status": "UNKNOWN", "scope": "complete"
    }))
    .unwrap();
    let ids: Vec<&str> = vec!["p0"];
    let refused = join(&system(&ids), &[bare], (false, false)).unwrap_err();
    assert!(
        refused.contains("UNKNOWN without an explaining row"),
        "{refused}"
    );
    // An unreadable status is UNKNOWN too and needs the same row.
    let odd = serde_json::to_vec(&json!({"engine": "e", "protocol": "p", "status": "BOGUS"}));
    assert!(join(&system(&ids), &[odd.unwrap()], (false, false)).is_err());
}

fn topology_part(why: &str) -> Vec<u8> {
    let frame = json!({
        "engine": "e", "protocol": "p", "status": "UNKNOWN", "scope": "complete",
        "explained": {"R1": why},
        "topology": {"version": 1, "complete": true, "truncated": false, "gaps": [],
            "total": {}, "components": [{"id": "C", "parent": null}], "modules": [],
            "edges": [], "component_edges": [], "requires": [], "layers": []},
    });
    serde_json::to_vec(&frame).unwrap()
}

#[test]
fn the_topology_of_an_unknown_system_names_the_scope_reason_as_a_gap() {
    let why = "incomplete scope: the profile cannot decide R1";
    let ids = ["p0"];
    let frame = join(&system(&ids), &[topology_part(why)], (false, true)).unwrap();
    let frame: Value = serde_json::from_slice(&frame).unwrap();
    assert_eq!(frame["scope"], json!(why));
    assert_eq!(frame["topology"]["gaps"], json!([why]));
    assert_eq!(frame["topology"]["complete"], json!(false));
}

/// A part that names one gap row for a rule, and the frame of a part whose collect is refused.
fn rule_gap_part() -> Vec<u8> {
    let frame = json!({
        "engine": "e", "protocol": "p", "status": "FAIL", "scope": "complete",
        "gaps": [{"kind": "decision.open", "subject": "R1", "reason": "open"}],
        "unsupported": {"rules": {"R1": "open"}, "sections": {}, "report": null},
    });
    serde_json::to_vec(&frame).unwrap()
}

fn refused_part(why: &str) -> Vec<u8> {
    let frame = json!({
        "engine": "e", "protocol": "p", "status": "UNKNOWN", "scope": why,
        "gaps": [{"kind": "other", "subject": "the whole contract", "reason": why}],
        "self_test": {"contract": {"not_read": why}, "reply": {"absent": why},
            "collect": {"refused": why}},
        "unsupported": {"rules": why, "sections": {}, "report": null},
    });
    serde_json::to_vec(&frame).unwrap()
}

/// The pairs (subject, reason) that the shell compares with `unsupported.rules` (AD-546).
fn gap_pairs(frame: &Value) -> Vec<(String, String)> {
    let text = |value: &Value| value.as_str().unwrap().to_owned();
    let rows = frame["gaps"].as_array().unwrap();
    rows.iter()
        .map(|row| (text(&row["subject"]), text(&row["reason"])))
        .collect()
}

#[test]
fn a_system_that_names_its_whole_contract_lists_only_that_gap_row() {
    let why = "collect: unsupported: collector: refused";
    for parts in [
        vec![rule_gap_part(), refused_part(why)],
        vec![refused_part(why), rule_gap_part()],
        vec![refused_part(why), refused_part("other refusal")],
    ] {
        let frame = joined(&parts);
        assert_eq!(frame["unsupported"]["rules"], json!(why));
        assert_eq!(frame["self_test"]["collect"]["refused"], json!(why));
        let whole = ("the whole contract".to_owned(), why.to_owned());
        assert_eq!(gap_pairs(&frame), vec![whole]);
    }
    // Without a whole-contract part the rows of each part stay.
    let frame = joined(&[rule_gap_part()]);
    assert_eq!(
        gap_pairs(&frame),
        vec![("R1".to_owned(), "open".to_owned())]
    );
}
